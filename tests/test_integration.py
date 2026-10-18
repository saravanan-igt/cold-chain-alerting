import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.api import create_app
from backend.replay import normalize, replay
from backend.storage import Store, alerts, load_config, readings
from tests.test_domain import sample


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "test.db")
    value.provision(load_config())
    yield value
    value.engine.dispose()


def ingest(store, minute, temp=9, **kw):
    return store.ingest("nimbus", sample(minute, temp, **kw).canonical())


def test_duplicate_conflict_late_and_restart(store):
    assert ingest(store, 0, event_id="a")["status"] == "accepted"
    assert ingest(store, 0, event_id="a")["status"] == "duplicate"
    assert ingest(store, 0, 10, event_id="a")["status"] == "conflict"
    assert ingest(store, 0, event_id="b")["status"] == "conflict"
    ingest(store, 5)
    restarted = Store(store.engine.url.database)
    assert ingest(restarted, 10)["incident_id"]
    assert ingest(restarted, 7)["status"] == "late"
    assert restarted.fleet("nimbus")["trucks"][0]["late_count"] == 1
    with store.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(alerts)).scalar() == 1
        assert conn.execute(select(func.count()).select_from(readings)).scalar() == 4
    restarted.engine.dispose()


def test_concurrent_duplicates(store):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: ingest(store, 0), range(20)))
    assert sum(item["status"] == "accepted" for item in results) == 1
    assert sum(item["status"] == "duplicate" for item in results) == 19


def test_api_isolation_and_outcomes(store):
    keys = {"operator-a": {"tenant": "nimbus", "role": "operator"}, "operator-b": {"tenant": "alpine", "role": "operator"},
            "device-a": {"tenant": "nimbus", "role": "device", "truck_id": "T-01", "device_id": "sensor-T-01"}}
    with TestClient(create_app(store, keys)) as client:
        assert client.get("/api/v1/trucks").status_code == 401
        assert client.get("/api/v1/trucks", headers={"X-API-Key": "device-a"}).status_code == 403
        body = {"readings": [sample(t).canonical() for t in (0, 5, 10)]}
        result = client.post("/api/v1/readings", json=body, headers={"X-API-Key": "device-a"})
        assert result.status_code == 200 and result.json()["counts"]["accepted"] == 3
        assert client.post("/api/v1/readings", json=body, headers={"X-API-Key": "device-a"}).json()["counts"]["duplicate"] == 3
        incident_id = store.list_incidents("nimbus")[0]["id"]
        assert client.get(f"/api/v1/incidents/{incident_id}", headers={"X-API-Key": "operator-b"}).status_code == 404
        assert client.get("/api/v1/incidents", headers={"X-API-Key": "operator-b"}).json()["items"] == []
        bad = sample(15).canonical()
        bad["device_id"] = "alpine-sensor-01"
        response = client.post("/api/v1/readings", json={"readings": [bad, {}]}, headers={"X-API-Key": "device-a"})
        assert response.json()["counts"]["unauthorized"] == 1
        assert response.json()["counts"]["invalid"] == 1
        assert store.fleet("alpine")["trucks"][0]["status"] == "unknown"
        assert client.post("/api/v1/readings", json=body, headers={"X-API-Key": "operator-a"}).status_code == 403
        assert client.get("/api/v1/incidents?limit=101", headers={"X-API-Key": "operator-a"}).status_code == 422
        assert client.post("/api/v1/readings", content=b"x" * 262145, headers={"X-API-Key": "device-a"}).status_code == 413


def test_dataset_and_shuffle(store, tmp_path):
    config = load_config()
    report = replay(store, config, "starter_kit/data/sensor_readings.json", assume_utc=True)
    assert report["counts"]["accepted"] == 54
    assert sorted(item["truck_id"] for item in report["incidents"]) == ["T-01", "T-05"]
    assert all(item["lifecycle"] == "recovered" for item in report["incidents"])
    assert replay(store, config, "starter_kit/data/sensor_readings.json", assume_utc=True)["counts"]["duplicate"] == 54
    rows = [sample(t).canonical() for t in (10, 0, 5)]
    assert normalize(rows, {}) == normalize(list(reversed(rows)), {})
    conflicting = copy.deepcopy(rows)
    conflicting.append({**rows[0], "temperature_c": 20})
    with pytest.raises(ValueError):
        normalize(conflicting, {})


def test_transaction_rolls_back_on_failure(store, monkeypatch):
    import backend.storage as storage
    def broken(*args):
        raise RuntimeError("simulated state transition failure")
    monkeypatch.setattr(storage, "advance", broken)
    with pytest.raises(RuntimeError):
        ingest(store, 0)
    with store.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(readings)).scalar() == 0


def test_trucks_tenants_and_custom_rules_are_independent(store):
    for minute in (0, 5, 10):
        ingest(store, minute)
        alpine = sample(minute, 7).canonical()
        alpine["device_id"] = "alpine-sensor-01"
        assert store.ingest("alpine", alpine)["status"] == "accepted"
        other = sample(minute, 7).canonical()
        other.update(truck_id="T-02", device_id="sensor-T-02")
        store.ingest("nimbus", other)
    assert len(store.list_incidents("nimbus")) == 1
    assert store.list_incidents("alpine") == []
    alpine = sample(15, 7).canonical()
    alpine["device_id"] = "alpine-sensor-01"
    store.ingest("alpine", alpine)
    assert store.list_incidents("alpine")[0]["rule"]["threshold_c"] == 6


def test_staleness_is_independent_from_open_lifecycle(store):
    from datetime import timedelta
    from tests.test_domain import BASE
    for minute in (0, 5, 10):
        ingest(store, minute)
    row = store.fleet("nimbus", BASE + timedelta(minutes=15))["trucks"][0]
    assert row["freshness"] == "fresh" and row["status"] == "open"
    row = store.fleet("nimbus", BASE + timedelta(minutes=16))["trucks"][0]
    assert row["freshness"] == "stale" and row["status"] == "open"


def test_unknown_device_future_and_missing_fields(store):
    from datetime import datetime, timedelta, timezone
    assert store.ingest("nimbus", {})["status"] == "invalid"
    row = sample(0).canonical()
    row["device_id"] = "unknown"
    assert store.ingest("nimbus", row)["status"] == "unauthorized"
    row = sample(0).canonical()
    row["timestamp"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert store.ingest("nimbus", row)["status"] == "invalid"


def test_opening_event_failure_rolls_back_entire_qualification(store):
    from sqlalchemy import event
    ingest(store, 0)
    ingest(store, 5)
    def fail_outbox(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO opening_alerts"):
            raise RuntimeError("simulated opening event failure")
    event.listen(store.engine, "before_cursor_execute", fail_outbox)
    try:
        with pytest.raises(RuntimeError):
            ingest(store, 10)
        assert store.list_incidents("nimbus") == []
        assert store.fleet("nimbus")["trucks"][0]["status"] == "pending"
    finally:
        event.remove(store.engine, "before_cursor_execute", fail_outbox)
    assert ingest(store, 10)["status"] == "accepted"
    assert len(store.list_incidents("nimbus")) == 1
