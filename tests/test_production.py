"""Production capabilities: outbox, delivery, escalation, acknowledgement, shared sessions,
observability, OIDC, backup/restore, schema migration and demo scenarios."""
import copy
import hashlib
import hmac
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from backend import backup
from backend.api import create_app
from backend.auth import COOKIE, hash_password
from backend.identity import OidcVerifier
from backend.live_demo import ScenarioPlayer, current_readings, steady_frame
from backend.notifications import NotificationWorker
from backend.scenarios import SAMPLE_SECONDS, catalogue
from backend.storage import SCHEMA_VERSION, Store, incidents, load_config, outbox
from tests.test_domain import sample

BROWSER = {"X-Coldline-Request": "browser"}


def webhook_config(url="https://hooks.example.test/coldline", secret_env="TEST_WEBHOOK_SECRET", fmt="coldline"):
    config = copy.deepcopy(load_config())
    config["tenants"][0]["notifications"] = {
        "channels": [
            {"id": "ops", "type": "webhook", "url": url, "secret_env": secret_env, "format": fmt,
             "events": ["incident.opened", "incident.recovered", "incident.acknowledged"]},
            {"id": "manager", "type": "log", "events": []},
        ],
        "escalation": [{"after_minutes": 15, "channels": ["manager"]}, {"after_minutes": 30, "channels": ["manager", "ops"]}],
    }
    return config


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "prod.db")
    value.provision(webhook_config())
    yield value
    value.engine.dispose()


def open_incident(store):
    for minute in (0, 5, 10):
        result = store.ingest("nimbus", sample(minute).canonical())
    return result["incident_id"]


def recording_worker(store, statuses=(200,)):
    calls, queue = [], list(statuses)

    def handler(request):
        calls.append(request)
        return httpx.Response(queue.pop(0) if len(queue) > 1 else queue[0])
    return NotificationWorker(store, client=httpx.Client(transport=httpx.MockTransport(handler))), calls


def outbox_rows(store):
    with store.engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(outbox).order_by(outbox.c.id)).mappings()]


def test_outbox_written_atomically_with_transitions(store):
    incident_id = open_incident(store)
    rows = outbox_rows(store)
    assert [(r["event"], r["channel_id"], r["status"]) for r in rows] == [("incident.opened", "ops", "pending")]
    for minute in (15, 20):
        store.ingest("nimbus", sample(minute, 5).canonical())
    assert [r["event"] for r in outbox_rows(store)] == ["incident.opened", "incident.recovered"]
    detail = store.detail("nimbus", incident_id)
    assert [e["kind"] for e in detail["timeline"]] == ["opened", "recovered"]
    assert detail["acknowledgement"] is None and len(detail["notifications"]) == 2


def test_outbox_failure_rolls_back_incident(store):
    store.ingest("nimbus", sample(0).canonical())
    store.ingest("nimbus", sample(5).canonical())

    def fail(conn, cursor, statement, *args):
        if statement.startswith("INSERT INTO notification_outbox"):
            raise RuntimeError("simulated outbox failure")
    event.listen(store.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            store.ingest("nimbus", sample(10).canonical())
        assert store.list_incidents("nimbus") == [] and outbox_rows(store) == []
    finally:
        event.remove(store.engine, "before_cursor_execute", fail)
    assert store.ingest("nimbus", sample(10).canonical())["incident_id"]
    assert len(outbox_rows(store)) == 1


def test_signed_webhook_delivery(store, monkeypatch):
    monkeypatch.setenv("TEST_WEBHOOK_SECRET", "s3cret")
    open_incident(store)
    worker, calls = recording_worker(store)
    assert worker.run_once()["delivered"] == 1
    request = calls[0]
    body = request.content
    expected = "v1=" + hmac.new(b"s3cret", request.headers["X-Coldline-Timestamp"].encode() + b"." + body, hashlib.sha256).hexdigest()
    assert request.headers["X-Coldline-Signature"] == expected
    assert request.headers["X-Coldline-Event"] == "incident.opened"
    assert request.headers["X-Coldline-Delivery"].startswith("nimbus:")
    assert json.loads(body)["incident"]["truck_id"] == "T-01"
    assert outbox_rows(store)[0]["status"] == "delivered"
    assert worker.run_once()["delivered"] == 0


def test_retry_backoff_then_dead_letter_and_manual_retry(store, monkeypatch):
    monkeypatch.setenv("TEST_WEBHOOK_SECRET", "s3cret")
    open_incident(store)
    worker, calls = recording_worker(store, (503, 200))
    now = datetime.now(timezone.utc)
    assert worker.run_once(now)["retry"] == 1
    row = outbox_rows(store)[0]
    assert row["status"] == "pending" and row["attempts"] == 1 and "HTTP 503" in row["last_error"]
    assert worker.run_once(now)["delivered"] == 0, "backoff must defer the retry"
    assert worker.run_once(now + timedelta(minutes=1))["delivered"] == 1
    # A permanent 4xx dead-letters immediately; operators can requeue it.
    store.acknowledge("nimbus", row["incident_id"], "op")
    worker, _ = recording_worker(store, (400,))
    assert worker.run_once(now + timedelta(minutes=1))["dead"] == 1
    dead = store.list_notifications("nimbus", status="dead")
    assert len(dead) == 1 and dead[0]["event"] == "incident.acknowledged"
    assert store.retry_notification("nimbus", dead[0]["id"]) and not store.retry_notification("alpine", dead[0]["id"])


def test_missing_secret_is_retried_not_sent_unsigned(store, monkeypatch):
    monkeypatch.delenv("TEST_WEBHOOK_SECRET", raising=False)
    open_incident(store)
    worker, calls = recording_worker(store)
    assert worker.run_once()["retry"] == 1 and calls == []


def test_escalation_until_acknowledged(store):
    incident_id = open_incident(store)
    worker, _ = recording_worker(store)
    now = datetime.now(timezone.utc)
    assert worker.run_once(now + timedelta(minutes=5))["escalated"] == 0
    assert worker.run_once(now + timedelta(minutes=16))["escalated"] == 1
    assert worker.run_once(now + timedelta(minutes=17))["escalated"] == 0, "each level fires once"
    keys = [(r["event_key"], r["channel_id"]) for r in outbox_rows(store)]
    assert ("incident.escalated.1", "manager") in keys
    store.acknowledge("nimbus", incident_id, "dispatcher", "Driver contacted")
    assert worker.run_once(now + timedelta(minutes=45))["escalated"] == 0
    kinds = [e["kind"] for e in store.detail("nimbus", incident_id)["timeline"]]
    assert kinds == ["opened", "escalated", "acknowledged"]


def test_acknowledgement_api_and_shared_sessions(tmp_path):
    path = tmp_path / "shared.db"
    users = {"op": {"tenant": "nimbus", "password_hash": hash_password("pw")}}
    keys = {"other": {"tenant": "alpine", "role": "operator"}}
    first, second = Store(path), Store(path)
    first.provision(load_config())
    incident_id = open_incident(first)
    with TestClient(create_app(first, keys, users, worker=False)) as a, TestClient(create_app(second, keys, users, worker=False)) as b:
        assert a.post("/api/v1/session", headers=BROWSER, json={"username": "op", "password": "pw"}).status_code == 200
        token = a.cookies.get(COOKIE)
        b.cookies.set(COOKIE, token)
        assert b.get("/api/v1/trucks").status_code == 200, "replica B must accept a session issued by replica A"
        path_ = f"/api/v1/incidents/{incident_id}/acknowledge"
        assert b.post(path_, json={"note": "On it"}).status_code == 403, "cookie mutation requires the browser header"
        created = b.post(path_, headers=BROWSER, json={"note": "  On it  "}).json()
        assert created["created"] and created["acknowledgement"]["acknowledged_by"] == "op"
        assert created["acknowledgement"]["note"] == "On it"
        assert b.post(path_, headers=BROWSER).json()["created"] is False
        assert a.post(path_, headers={"X-API-Key": "other"}).status_code == 404
        listed = a.get("/api/v1/incidents").json()["items"][0]
        assert listed["acknowledgement"]["acknowledged_by"] == "op"
        assert a.delete("/api/v1/session", headers=BROWSER).status_code == 200
        assert b.get("/api/v1/trucks").status_code == 401, "revocation is visible to every replica"
    first.engine.dispose()
    second.engine.dispose()


def test_readiness_metrics_and_request_ids(store, monkeypatch):
    keys = {"device": {"tenant": "nimbus", "role": "device", "truck_id": "T-01", "device_id": "sensor-T-01"}}
    with TestClient(create_app(store, keys, worker=False)) as client:
        assert client.get("/ready").json() == {"status": "ready", "checks": {"database": "ok"}}
        assert client.get("/health").json()["schema_version"] == SCHEMA_VERSION
        response = client.post("/api/v1/readings", headers={"X-API-Key": "device", "X-Request-ID": "trace-12345678"},
                               json={"readings": [sample(0).canonical()]})
        assert response.headers["X-Request-ID"] == "trace-12345678"
        assert len(client.get("/health", headers={"X-Request-ID": "bad id!"}).headers["X-Request-ID"]) == 32
        text = client.get("/metrics").text
        assert 'coldline_readings_total{outcome="accepted"}' in text
        assert 'route="/api/v1/readings"' in text and "coldline_outbox_dead 0" in text
        monkeypatch.setenv("COLDCHAIN_METRICS_TOKEN", "m-token")
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer m-token"}).status_code == 200


def test_oidc_bearer_tokens(store):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OidcVerifier("https://idp.example", "coldline-api", known_tenants={"nimbus", "alpine"},
                            key_resolver=lambda token: private.public_key())

    def token(**overrides):
        claims = {"iss": "https://idp.example", "aud": "coldline-api", "sub": "u1", "preferred_username": "dana",
                  "coldline_tenant": "nimbus", "roles": ["coldline.operator"], "exp": int(time.time()) + 300, **overrides}
        return jwt.encode(claims, private, algorithm="RS256")
    with TestClient(create_app(store, {}, {}, worker=False, oidc=verifier)) as client:
        def call(value):
            return client.get("/api/v1/trucks", headers={"Authorization": f"Bearer {value}"})
        assert call(token()).json()["tenant"] == "nimbus"
        incident_id = open_incident(store)
        ack = client.post(f"/api/v1/incidents/{incident_id}/acknowledge", headers={"Authorization": f"Bearer {token()}"})
        assert ack.json()["acknowledgement"]["acknowledged_by"] == "dana"
        for bad in (token(aud="other"), token(roles=["viewer"]), token(coldline_tenant="unknown"),
                    token(exp=int(time.time()) - 600), token(iss="https://evil.example"), "not-a-jwt"):
            assert call(bad).status_code == 401
        hs = jwt.encode({"iss": "https://idp.example", "aud": "coldline-api", "sub": "x", "coldline_tenant": "nimbus",
                         "roles": ["coldline.operator"], "exp": int(time.time()) + 300}, "k" * 32, algorithm="HS256")
        assert call(hs).status_code == 401, "symmetric algorithms must be rejected"


def test_backup_verify_restore(store, tmp_path):
    open_incident(store)
    manifest = backup.backup(store.engine.url.database, tmp_path / "backups" / "b.db")
    assert manifest["schema_version"] == SCHEMA_VERSION and manifest["row_counts"]["incidents"] == 1
    assert backup.verify(tmp_path / "backups" / "b.db")["row_counts"]["readings"] == 3
    target = tmp_path / "restored.db"
    assert backup.restore(tmp_path / "backups" / "b.db", target)["row_counts"]["notification_outbox"] == 1
    with pytest.raises(FileExistsError):
        backup.restore(tmp_path / "backups" / "b.db", target)
    restored = Store(target)
    assert restored.list_incidents("nimbus")[0]["lifecycle"] == "open"
    restored.engine.dispose()
    with open(tmp_path / "backups" / "b.db", "ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(RuntimeError):
        backup.verify(tmp_path / "backups" / "b.db")


def test_v1_database_migrates_to_v2(tmp_path):
    path = tmp_path / "v1.db"
    store = Store(path)
    store.provision(load_config())
    open_incident(store)
    store.engine.dispose()
    conn = sqlite3.connect(path)
    for table in ("schema_meta", "incident_events", "incident_acknowledgements", "notification_outbox", "operator_sessions", "demo_scenarios"):
        conn.execute(f"DROP TABLE {table}")
    conn.execute("PRAGMA user_version=1")
    conn.commit()
    conn.close()
    upgraded = Store(path)
    assert upgraded.schema_version() == 2
    incident_id = upgraded.list_incidents("nimbus")[0]["id"]
    assert upgraded.acknowledge("nimbus", incident_id, "op")["created"]
    upgraded.engine.dispose()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version=99")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError):
        Store(path)


@pytest.mark.parametrize("config_path", ["config/live-demo.json", "config/customers.json"])
def test_scenarios_follow_the_unchanged_rule(tmp_path, config_path):
    config = load_config(config_path)
    rule = config["tenants"][0]["rule"]
    scenarios = catalogue(rule)
    assert {key for key, value in scenarios.items() if value["genuine"]} == {"compressor_failure", "marginal_sustained"}
    for index, (name, definition) in enumerate(scenarios.items()):
        store = Store(tmp_path / f"{index}-{config_path.replace('/', '_')}.db")
        store.provision(config)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        for step, value in enumerate(definition["steps"]):
            if value is None:
                continue
            row = {"truck_id": "T-01", "device_id": "sensor-T-01", "temperature_c": value,
                   "timestamp": (start + timedelta(seconds=step * SAMPLE_SECONDS)).isoformat()}
            assert store.ingest("nimbus", row)["status"] == "accepted"
        opened = store.list_incidents("nimbus")
        assert bool(opened) == definition["expected_incident"], name
        if opened:
            assert opened[0]["lifecycle"] == "recovered", f"{name} should end recovered"
        store.engine.dispose()


def test_demo_scenario_api_and_player(tmp_path, monkeypatch):
    monkeypatch.setenv("COLDCHAIN_CONFIG", "config/live-demo.json")
    config = load_config("config/live-demo.json")
    store = Store(tmp_path / "demo.db")
    keys = {"op": {"tenant": "nimbus", "role": "operator"}, "alp": {"tenant": "alpine", "role": "operator"}}
    with TestClient(create_app(store, keys, worker=False)) as client:
        headers = {"X-API-Key": "op"}
        listing = client.get("/api/v1/demo/scenarios", headers=headers).json()
        assert {item["id"] for item in listing["catalogue"]} >= {"compressor_failure", "door_open_spike"}
        assert client.get("/api/v1/demo/scenarios", headers={"X-API-Key": "alp"}).status_code == 404
        assert client.post("/api/v1/demo/scenarios", headers=headers, json={"truck_id": "T-03", "scenario": "nope"}).status_code == 422
        genuine = client.post("/api/v1/demo/scenarios", headers=headers, json={"truck_id": "T-03", "scenario": "compressor_failure"})
        spike = client.post("/api/v1/demo/scenarios", headers=headers, json={"truck_id": "T-02", "scenario": "door_open_spike"})
        assert genuine.status_code == 201 and spike.status_code == 201
        assert client.post("/api/v1/demo/scenarios", headers=headers, json={"truck_id": "T-03", "scenario": "sensor_glitch"}).status_code == 409
        player = ScenarioPlayer(client, "op")
        customer = config["tenants"][0]
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        for tick in range(40):
            overrides = player.overrides()
            frame = [{**row, "temperature_c": overrides.get(row["truck_id"], row["temperature_c"])}
                     for row in steady_frame(customer, tick) if not (row["truck_id"] in overrides and overrides[row["truck_id"]] is None)]
            for row in current_readings(frame, start + timedelta(seconds=tick * 10), "test", tick):
                assert store.ingest("nimbus", row)["status"] == "accepted"
            player.complete()
        runs = {run["truck_id"]: run for run in client.get("/api/v1/demo/scenarios", headers=headers).json()["runs"]}
        assert runs["T-03"]["status"] == "completed" and runs["T-03"]["observed_incident_id"]
        assert runs["T-03"]["expected_incident"] is True and runs["T-03"]["genuine"] is True
        assert runs["T-02"]["status"] == "completed" and runs["T-02"]["observed_incident_id"] is None
        assert runs["T-02"]["expected_incident"] is False
        assert [i["truck_id"] for i in store.list_incidents("nimbus")] == ["T-03"]
        third = client.post("/api/v1/demo/scenarios", headers=headers, json={"truck_id": "T-01", "scenario": "sensor_glitch"}).json()
        assert client.patch(f"/api/v1/demo/scenarios/{third['id']}", headers=headers, json={"status": "cancelled"}).json()["status"] == "cancelled"
        assert client.patch(f"/api/v1/demo/scenarios/{third['id']}", headers=headers, json={"status": "running"}).status_code == 409
    with store.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(incidents)).scalar() == 1
    store.engine.dispose()
