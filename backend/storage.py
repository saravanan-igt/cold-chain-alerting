"""Persistence and transactional application service (schema v2).

SQLite is the default single-node store. PostgreSQL is supported through
``COLDCHAIN_DATABASE_URL`` for multi-instance deployments: every write that reads
detector state first takes a row lock (``SELECT ... FOR UPDATE``); SQLite gets the
same serialisation from ``BEGIN IMMEDIATE``.
"""
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import (JSON, Column, Float, ForeignKeyConstraint, Index, Integer, MetaData, String, Table,
                        UniqueConstraint, create_engine, event, func, inspect, select, text)
from sqlalchemy.engine import make_url

from backend.domain import Reading, Rule, advance, seconds, utc
from backend.configuration import Customers
from backend.observability import metrics

SCHEMA_VERSION = 2

metadata = MetaData()
tenants = Table("tenants", metadata, Column("id", String, primary_key=True), Column("config", JSON, nullable=False))
trucks = Table("trucks", metadata,
    Column("tenant", String, primary_key=True), Column("id", String, primary_key=True),
    Column("device_id", String, nullable=False), Column("rule", JSON, nullable=False),
    Column("state", JSON, nullable=False), Column("late_count", Integer, nullable=False, default=0),
    ForeignKeyConstraint(["tenant"], ["tenants.id"]), UniqueConstraint("tenant", "device_id"))
readings = Table("readings", metadata,
    Column("id", Integer, primary_key=True), Column("tenant", String, nullable=False),
    Column("truck_id", String, nullable=False), Column("device_id", String, nullable=False),
    Column("identity", String, nullable=False), Column("fingerprint", String, nullable=False),
    Column("event_at", String, nullable=False), Column("ingested_at", String, nullable=False),
    Column("status", String, nullable=False), Column("payload", JSON, nullable=False),
    ForeignKeyConstraint(["tenant", "truck_id"], ["trucks.tenant", "trucks.id"]),
    UniqueConstraint("tenant", "device_id", "identity"), UniqueConstraint("tenant", "truck_id", "event_at"))
incidents = Table("incidents", metadata,
    Column("tenant", String, primary_key=True), Column("id", String, primary_key=True),
    Column("truck_id", String, nullable=False), Column("qualified_at", String, nullable=False),
    Column("lifecycle", String, nullable=False), Column("data", JSON, nullable=False),
    ForeignKeyConstraint(["tenant", "truck_id"], ["trucks.tenant", "trucks.id"]))
alerts = Table("opening_alerts", metadata,
    Column("tenant", String, primary_key=True), Column("incident_id", String, primary_key=True),
    Column("processed_at", String, nullable=False),
    ForeignKeyConstraint(["tenant", "incident_id"], ["incidents.tenant", "incidents.id"]))
# ---- schema v2 ----
schema_meta = Table("schema_meta", metadata, Column("key", String, primary_key=True), Column("value", String, nullable=False))
incident_events = Table("incident_events", metadata,
    Column("id", Integer, primary_key=True), Column("tenant", String, nullable=False),
    Column("incident_id", String, nullable=False), Column("kind", String, nullable=False),
    Column("actor", String, nullable=False), Column("at", String, nullable=False),
    Column("details", JSON, nullable=False),
    ForeignKeyConstraint(["tenant", "incident_id"], ["incidents.tenant", "incidents.id"]))
acknowledgements = Table("incident_acknowledgements", metadata,
    Column("tenant", String, primary_key=True), Column("incident_id", String, primary_key=True),
    Column("acknowledged_by", String, nullable=False), Column("acknowledged_at", String, nullable=False),
    Column("note", String, nullable=True),
    ForeignKeyConstraint(["tenant", "incident_id"], ["incidents.tenant", "incidents.id"]))
outbox = Table("notification_outbox", metadata,
    Column("id", Integer, primary_key=True), Column("tenant", String, nullable=False),
    Column("incident_id", String, nullable=False), Column("event", String, nullable=False),
    Column("event_key", String, nullable=False), Column("channel_id", String, nullable=False),
    Column("channel_type", String, nullable=False), Column("status", String, nullable=False),
    Column("attempts", Integer, nullable=False, default=0), Column("next_attempt_at", String, nullable=False),
    Column("lease_until", String, nullable=True), Column("created_at", String, nullable=False),
    Column("delivered_at", String, nullable=True), Column("last_error", String, nullable=True),
    Column("payload", JSON, nullable=False),
    ForeignKeyConstraint(["tenant", "incident_id"], ["incidents.tenant", "incidents.id"]),
    UniqueConstraint("tenant", "incident_id", "event_key", "channel_id"))
sessions = Table("operator_sessions", metadata,
    Column("token_hash", String, primary_key=True), Column("username", String, nullable=False),
    Column("tenant", String, nullable=False), Column("role", String, nullable=False),
    Column("expires_at", Float, nullable=False), Column("created_at", String, nullable=False))
demo_runs = Table("demo_scenarios", metadata,
    Column("id", Integer, primary_key=True), Column("tenant", String, nullable=False),
    Column("truck_id", String, nullable=False), Column("scenario", String, nullable=False),
    Column("status", String, nullable=False), Column("requested_by", String, nullable=False),
    Column("requested_at", String, nullable=False), Column("started_at", String, nullable=True),
    Column("completed_at", String, nullable=True),
    ForeignKeyConstraint(["tenant", "truck_id"], ["trucks.tenant", "trucks.id"]))
Index("ix_incidents_tenant_lifecycle_time", incidents.c.tenant, incidents.c.lifecycle, incidents.c.qualified_at)
Index("ix_readings_evidence", readings.c.tenant, readings.c.truck_id, readings.c.status, readings.c.event_at)
Index("ix_incident_events_incident", incident_events.c.tenant, incident_events.c.incident_id, incident_events.c.id)
Index("ix_outbox_due", outbox.c.status, outbox.c.next_attempt_at)
Index("ix_outbox_incident", outbox.c.tenant, outbox.c.incident_id)
Index("ix_sessions_expiry", sessions.c.expires_at)
Index("ix_demo_runs_tenant", demo_runs.c.tenant, demo_runs.c.status)

ACTIVE_DEMO = ("queued", "running")
MAX_DELIVERY_ATTEMPTS = 8


def _now():
    return datetime.now(timezone.utc)


def azure_token_provider(scope="https://ossrdbms-aad.database.windows.net/.default"):
    """Workload (managed) identity for Azure Database for PostgreSQL; tokens are cached until near expiry."""
    from azure.identity import DefaultAzureCredential  # optional dependency, imported only when enabled
    credential, cache, lock = DefaultAzureCredential(), {}, threading.Lock()

    def token():
        with lock:
            if cache.get("expires_on", 0) - 300 < time.time():
                issued = credential.get_token(scope)
                cache.update(token=issued.token, expires_on=issued.expires_on)
            return cache["token"]
    return token


class Store:
    def __init__(self, target, token_provider=None):
        raw = str(target)
        url = make_url(raw if "://" in raw else f"sqlite:///{Path(raw).as_posix()}")
        self.dialect = url.get_backend_name()
        if self.dialect == "sqlite":
            self.engine = create_engine(url, connect_args={"timeout": 30, "check_same_thread": False})

            @event.listens_for(self.engine, "connect")
            def pragmas(conn, _):
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=30000")
            with self.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        else:
            self.engine = create_engine(url, pool_pre_ping=True, pool_size=int(os.getenv("COLDCHAIN_DB_POOL_SIZE", "5")))
            if token_provider is None and os.getenv("COLDCHAIN_DB_AUTH") == "azure-managed-identity":
                token_provider = azure_token_provider()
            if token_provider:
                # No database password in configuration: a short-lived identity token per new connection.
                @event.listens_for(self.engine, "do_connect")
                def identity_token(dialect, conn_rec, cargs, cparams):
                    cparams["password"] = token_provider()
        self._migrate()

    # ---------- schema ----------
    def _version(self, conn):
        if self.dialect == "sqlite":
            return conn.exec_driver_sql("PRAGMA user_version").scalar()
        if not inspect(conn).has_table("schema_meta"):
            return 1 if inspect(conn).has_table("trucks") else 0
        value = conn.execute(select(schema_meta.c.value).where(schema_meta.c.key == "version")).scalar()
        return int(value) if value else 1

    def _migrate(self):
        with self.write() as conn:
            if self.dialect == "postgresql":
                # Concurrent replicas starting together must not race on DDL.
                conn.execute(text("SELECT pg_advisory_xact_lock(4242001)"))
            version = self._version(conn)
            if version not in range(0, SCHEMA_VERSION + 1):
                raise RuntimeError(f"Unsupported schema version {version}")
            # v1 -> v2 is additive: create_all only creates the missing v2 tables and indexes.
            metadata.create_all(conn)
            if version != SCHEMA_VERSION:
                if self.dialect == "sqlite":
                    conn.exec_driver_sql(f"PRAGMA user_version={SCHEMA_VERSION}")
                conn.execute(schema_meta.delete().where(schema_meta.c.key == "version"))
                conn.execute(schema_meta.insert().values(key="version", value=str(SCHEMA_VERSION)))

    def schema_version(self):
        with self.engine.connect() as conn:
            return self._version(conn)

    def ping(self):
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return self.schema_version()

    @contextmanager
    def write(self):
        with self.engine.connect() as conn:
            if self.dialect == "sqlite":
                # Acquire the SQLite writer reservation BEFORE reading detector state.
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ---------- configuration ----------
    def provision(self, config):
        config = Customers.model_validate(config).model_dump(exclude_none=True)
        with self.write() as conn:
            if self.dialect == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(4242001)"))
            for tenant in config["tenants"]:
                tid = tenant["id"]
                rule = Rule.model_validate(tenant.get("rule", {}))
                existing_ids = set(conn.execute(select(trucks.c.id).where(trucks.c.tenant == tid)).scalars())
                if len(existing_ids | {truck["id"] for truck in tenant["trucks"]}) > 1000:
                    raise ValueError("MVP fleet limit is 1,000 persisted trucks per tenant")
                old = conn.execute(select(tenants).where(tenants.c.id == tid)).first()
                if old:
                    conn.execute(tenants.update().where(tenants.c.id == tid).values(config=tenant))
                else:
                    conn.execute(tenants.insert().values(id=tid, config=tenant))
                for truck in tenant["trucks"]:
                    selected_rule = Rule.model_validate(truck["rule"]) if "rule" in truck else rule
                    condition = (trucks.c.tenant == tid) & (trucks.c.id == truck["id"])
                    old = conn.execute(select(trucks).where(condition)).mappings().first()
                    if old and old["device_id"] != truck["device_id"]:
                        raise ValueError("Device reassignment requires an explicit migration")
                    if old:
                        conn.execute(trucks.update().where(condition).values(rule=selected_rule.model_dump()))
                    else:
                        conn.execute(trucks.insert().values(tenant=tid, id=truck["id"], device_id=truck["device_id"], rule=selected_rule.model_dump(), state={}, late_count=0))

    def tenant_config(self, tenant):
        with self.engine.connect() as conn:
            return conn.execute(select(tenants.c.config).where(tenants.c.id == tenant)).scalar_one_or_none()

    # ---------- ingestion ----------
    def ingest(self, tenant, raw, binding=None, live=True):
        try:
            reading = Reading.model_validate(raw)
        except ValidationError as exc:
            metrics.inc("coldline_readings_total", outcome="invalid")
            return {"status": "invalid", "reason": str(exc)}
        now = _now()
        if live and reading.timestamp > now + timedelta(minutes=5):
            metrics.inc("coldline_readings_total", outcome="invalid")
            return {"status": "invalid", "reason": "event time exceeds allowed 5-minute clock skew"}
        if binding and (reading.truck_id != binding["truck_id"] or reading.device_id != binding["device_id"]):
            metrics.inc("coldline_readings_total", outcome="unauthorized")
            return {"status": "unauthorized", "reason": "credential does not authorize this stream"}
        payload = reading.canonical()
        fingerprint = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        identity = "event:" + reading.event_id if reading.event_id else "hash:" + fingerprint
        condition = (trucks.c.tenant == tenant) & (trucks.c.id == reading.truck_id)
        transition = None
        with self.write() as conn:
            # Row lock on PostgreSQL; SQLite is already serialised by BEGIN IMMEDIATE.
            truck = conn.execute(select(trucks).where(condition).with_for_update()).mappings().first()
            outcome = self._ingest_locked(conn, tenant, truck, reading, payload, fingerprint, identity, now)
            transition = outcome.pop("_transition", None)
        metrics.inc("coldline_readings_total", outcome=outcome["status"])
        if transition:
            metrics.inc("coldline_incidents_total", transition=transition)
        return outcome

    def _ingest_locked(self, conn, tenant, truck, reading, payload, fingerprint, identity, now):
        if not truck or truck["device_id"] != reading.device_id:
            return {"status": "unauthorized", "reason": "unknown or unregistered device/truck"}
        existing = conn.execute(select(readings).where(readings.c.tenant == tenant, readings.c.device_id == reading.device_id, readings.c.identity == identity)).mappings().first()
        if existing:
            if existing["fingerprint"] != fingerprint:
                return {"status": "conflict", "reason": "identity reused with a different payload"}
            return {"status": "duplicate", "reading_id": existing["id"]}
        # One authoritative sample per stream timestamp; never silently pick a temperature.
        existing = conn.execute(select(readings.c.id).where(readings.c.tenant == tenant, readings.c.truck_id == reading.truck_id, readings.c.event_at == payload["timestamp"])).first()
        if existing:
            return {"status": "conflict", "reason": "stream timestamp already occupied"}
        condition = (trucks.c.tenant == tenant) & (trucks.c.id == reading.truck_id)
        previous = truck["state"]
        late = bool(previous.get("last_at") and payload["timestamp"] < previous["last_at"])
        status = "late" if late else "accepted"
        result = conn.execute(readings.insert().values(tenant=tenant, truck_id=reading.truck_id, device_id=reading.device_id,
            identity=identity, fingerprint=fingerprint, event_at=payload["timestamp"], ingested_at=utc(now), status=status, payload=payload))
        incident_id, transition = None, None
        if late:
            conn.execute(trucks.update().where(condition).values(late_count=truck["late_count"] + 1))
        else:
            state, incident, opened = advance(previous, reading, Rule.model_validate(truck["rule"]), tenant, utc(now))
            conn.execute(trucks.update().where(condition).values(state=state))
            if incident:
                incident_id = incident["id"]
                values = dict(truck_id=reading.truck_id, qualified_at=incident["qualified_at"], lifecycle=incident["lifecycle"], data=incident)
                if opened:
                    conn.execute(incidents.insert().values(tenant=tenant, id=incident_id, **values))
                    conn.execute(alerts.insert().values(tenant=tenant, incident_id=incident_id, processed_at=utc(now)))
                    transition = "opened"
                else:
                    conn.execute(incidents.update().where(incidents.c.tenant == tenant, incidents.c.id == incident_id).values(**values))
                    if incident["lifecycle"] == "recovered":
                        transition = "recovered"
                if transition:
                    # Audit record and notification intents commit atomically with the transition.
                    self._event(conn, tenant, incident_id, transition, "detector", now, {"rule_version": incident["rule"].get("version")})
                    self._enqueue(conn, tenant, incident, f"incident.{transition}", now)
        return {"status": status, "reading_id": result.inserted_primary_key[0], "incident_id": incident_id, "_transition": transition}

    # ---------- audit and notification outbox ----------
    @staticmethod
    def _event(conn, tenant, incident_id, kind, actor, now, details=None):
        conn.execute(incident_events.insert().values(tenant=tenant, incident_id=incident_id, kind=kind, actor=actor,
                                                     at=utc(now), details=details or {}))

    @staticmethod
    def _payload(tenant, incident, event_name, event_key, now, acknowledgement=None, escalation_level=None):
        keys = ("id", "truck_id", "lifecycle", "excursion_started_at", "qualified_at", "recovery_confirmed_at",
                "last_observation_at", "observed_max_c", "evidence_count", "telemetry_gap_count", "explanation")
        return {"event": event_name, "event_key": event_key, "tenant": tenant, "occurred_at": utc(now),
                "incident": {key: incident.get(key) for key in keys},
                "rule": {key: incident["rule"].get(key) for key in ("threshold_c", "sustained_minutes", "max_gap_minutes", "recovery_minutes", "version")},
                "acknowledgement": acknowledgement, "escalation_level": escalation_level}

    def _enqueue(self, conn, tenant, incident, event_name, now, channel_ids=None, event_key=None, **extra):
        config = conn.execute(select(tenants.c.config).where(tenants.c.id == tenant)).scalar_one()
        channels = (config.get("notifications") or {}).get("channels", [])
        event_key = event_key or event_name
        payload = self._payload(tenant, incident, event_name, event_key, now, **extra)
        for channel in channels:
            selected = channel["id"] in channel_ids if channel_ids is not None else event_name in channel.get("events", [])
            if not selected:
                continue
            duplicate = conn.execute(select(outbox.c.id).where(outbox.c.tenant == tenant, outbox.c.incident_id == incident["id"],
                outbox.c.event_key == event_key, outbox.c.channel_id == channel["id"])).first()
            if duplicate:
                continue
            conn.execute(outbox.insert().values(tenant=tenant, incident_id=incident["id"], event=event_name, event_key=event_key,
                channel_id=channel["id"], channel_type=channel["type"], status="pending", attempts=0,
                next_attempt_at=utc(now), created_at=utc(now), payload=payload))

    def acknowledge(self, tenant, incident_id, actor, note=None):
        now = _now()
        with self.write() as conn:
            incident = conn.execute(select(incidents.c.data).where(incidents.c.tenant == tenant, incidents.c.id == incident_id)
                                    .with_for_update()).scalar_one_or_none()
            if incident is None:
                return None
            existing = conn.execute(select(acknowledgements).where(acknowledgements.c.tenant == tenant,
                acknowledgements.c.incident_id == incident_id)).mappings().first()
            if existing:
                return {"created": False, "acknowledgement": self._ack(existing)}
            values = dict(acknowledged_by=actor, acknowledged_at=utc(now), note=note)
            conn.execute(acknowledgements.insert().values(tenant=tenant, incident_id=incident_id, **values))
            self._event(conn, tenant, incident_id, "acknowledged", actor, now, {"note": note} if note else {})
            self._enqueue(conn, tenant, incident, "incident.acknowledged", now, acknowledgement=values)
        metrics.inc("coldline_acknowledgements_total")
        return {"created": True, "acknowledgement": values}

    @staticmethod
    def _ack(row):
        return {"acknowledged_by": row["acknowledged_by"], "acknowledged_at": row["acknowledged_at"], "note": row["note"]}

    def due_escalations(self, now=None):
        """Read-only scan: (tenant, incident_id, level_index) for open, unacknowledged incidents past a level."""
        now = now or _now()
        due = []
        with self.engine.connect() as conn:
            for tid, config in conn.execute(select(tenants.c.id, tenants.c.config)):
                levels = (config.get("notifications") or {}).get("escalation", [])
                if not levels:
                    continue
                rows = conn.execute(select(incidents.c.id, incidents.c.data).select_from(
                    incidents.outerjoin(acknowledgements, (acknowledgements.c.tenant == incidents.c.tenant) & (acknowledgements.c.incident_id == incidents.c.id)))
                    .where(incidents.c.tenant == tid, incidents.c.lifecycle == "open", acknowledgements.c.incident_id.is_(None)))
                for incident_id, data in rows:
                    done = {details.get("level_index") for details in conn.execute(select(incident_events.c.details).where(
                        incident_events.c.tenant == tid, incident_events.c.incident_id == incident_id, incident_events.c.kind == "escalated")).scalars()}
                    elapsed = seconds(data.get("opened_processed_at") or data["qualified_at"], utc(now))
                    due += [(tid, incident_id, index) for index, level in enumerate(levels)
                            if elapsed >= level["after_minutes"] * 60 and index not in done]
        return due

    def escalate(self, tenant, incident_id, level_index, now=None):
        now = now or _now()
        with self.write() as conn:
            incident = conn.execute(select(incidents.c.data).where(incidents.c.tenant == tenant, incidents.c.id == incident_id)
                                    .with_for_update()).scalar_one_or_none()
            config = conn.execute(select(tenants.c.config).where(tenants.c.id == tenant)).scalar_one()
            levels = (config.get("notifications") or {}).get("escalation", [])
            acked = conn.execute(select(acknowledgements.c.incident_id).where(acknowledgements.c.tenant == tenant,
                acknowledgements.c.incident_id == incident_id)).first()
            if incident is None or incident["lifecycle"] != "open" or acked or level_index >= len(levels):
                return False
            done = {details.get("level_index") for details in conn.execute(select(incident_events.c.details).where(
                incident_events.c.tenant == tenant, incident_events.c.incident_id == incident_id, incident_events.c.kind == "escalated")).scalars()}
            if level_index in done:
                return False
            level = levels[level_index]
            self._event(conn, tenant, incident_id, "escalated", "escalation-policy", now,
                        {"level_index": level_index, "after_minutes": level["after_minutes"], "channels": level["channels"]})
            self._enqueue(conn, tenant, incident, "incident.escalated", now, channel_ids=level["channels"],
                          event_key=f"incident.escalated.{level_index + 1}", escalation_level=level_index + 1)
        metrics.inc("coldline_escalations_total")
        return True

    def claim_notifications(self, now=None, limit=20, lease_seconds=60):
        """Lease due deliveries. SKIP LOCKED lets several workers share the queue on PostgreSQL."""
        now = utc(now or _now())
        due = ((outbox.c.status == "pending") & (outbox.c.next_attempt_at <= now)) | \
              ((outbox.c.status == "sending") & (outbox.c.lease_until < now))
        with self.engine.connect() as conn:
            if not conn.execute(select(outbox.c.id).where(due).limit(1)).first():
                return []
        lease = utc(datetime.fromisoformat(now) + timedelta(seconds=lease_seconds))
        with self.write() as conn:
            rows = [dict(row) for row in conn.execute(select(outbox).where(due).order_by(outbox.c.id).limit(limit)
                                                      .with_for_update(skip_locked=True)).mappings()]
            for row in rows:
                row["attempts"] += 1
                row["status"] = "sending"
                conn.execute(outbox.update().where(outbox.c.id == row["id"]).values(status="sending", lease_until=lease, attempts=row["attempts"]))
        return rows

    def finish_notification(self, notification_id, ok, error=None, retry_at=None, now=None):
        now = utc(now or _now())
        if ok:
            values = dict(status="delivered", delivered_at=now, lease_until=None, last_error=None)
        elif retry_at:
            values = dict(status="pending", next_attempt_at=utc(retry_at), lease_until=None, last_error=(error or "")[:500])
        else:
            values = dict(status="dead", lease_until=None, last_error=(error or "")[:500])
        with self.write() as conn:
            conn.execute(outbox.update().where(outbox.c.id == notification_id, outbox.c.status == "sending").values(**values))

    @staticmethod
    def _notification(row):
        return {key: row[key] for key in ("id", "incident_id", "event", "event_key", "channel_id", "channel_type", "status",
                                          "attempts", "next_attempt_at", "created_at", "delivered_at", "last_error")}

    def list_notifications(self, tenant, status=None, limit=50, offset=0):
        query = select(outbox).where(outbox.c.tenant == tenant)
        if status:
            query = query.where(outbox.c.status == status)
        with self.engine.connect() as conn:
            return [self._notification(row) for row in conn.execute(query.order_by(outbox.c.id.desc()).limit(limit).offset(offset)).mappings()]

    def retry_notification(self, tenant, notification_id):
        with self.write() as conn:
            result = conn.execute(outbox.update().where(outbox.c.tenant == tenant, outbox.c.id == notification_id, outbox.c.status == "dead")
                                  .values(status="pending", attempts=0, next_attempt_at=utc(_now()), last_error=None))
            return result.rowcount == 1

    def outbox_counts(self):
        with self.engine.connect() as conn:
            counts = dict(conn.execute(select(outbox.c.status, func.count()).group_by(outbox.c.status)).all())
            counts["open_incidents"] = conn.execute(select(func.count()).select_from(incidents).where(incidents.c.lifecycle == "open")).scalar()
            return counts

    # ---------- operator sessions (shared by every API replica) ----------
    def create_session(self, token_hash, identity, expires_at):
        with self.write() as conn:
            conn.execute(sessions.delete().where(sessions.c.expires_at <= time.time()))
            conn.execute(sessions.insert().values(token_hash=token_hash, username=identity["username"], tenant=identity["tenant"],
                                                  role=identity["role"], expires_at=expires_at, created_at=utc(_now())))

    def resolve_session(self, token_hash):
        with self.engine.connect() as conn:
            row = conn.execute(select(sessions).where(sessions.c.token_hash == token_hash, sessions.c.expires_at > time.time())).mappings().first()
            return {"tenant": row["tenant"], "role": row["role"], "username": row["username"]} if row else None

    def revoke_session(self, token_hash):
        with self.write() as conn:
            conn.execute(sessions.delete().where(sessions.c.token_hash == token_hash))

    # ---------- read models ----------
    def fleet(self, tenant, at=None):
        at = at or _now()
        with self.engine.connect() as conn:
            customer = conn.execute(select(tenants.c.config).where(tenants.c.id == tenant)).scalar_one()
            rows = conn.execute(select(trucks).where(trucks.c.tenant == tenant).order_by(trucks.c.id)).mappings()
            items = []
            for row in rows:
                state = row["state"]
                snapshot = (state.get("active") or state.get("candidate") or {}).get("rule", row["rule"])
                age = seconds(state["last_at"], utc(at)) if state.get("last_at") else None
                items.append({"id": row["id"], "device_id": row["device_id"], "last_observation_at": state.get("last_at"),
                    "temperature_c": state.get("last_temperature_c"), "freshness": "never_seen" if age is None else "future" if age < 0 else "stale" if age > snapshot["max_gap_minutes"] * 60 else "fresh",
                    "status": "open" if state.get("active") else "pending" if state.get("candidate") else "normal" if state.get("last_at") else "unknown",
                    "incident_id": (state.get("active") or {}).get("id"), "late_count": row["late_count"], "rule": row["rule"]})
            return {"tenant": tenant, "name": customer["name"], "accent": customer.get("accent", "#17675e"), "demo_mode": customer.get("demo_mode"), "as_of": utc(at), "trucks": items}

    def _with_ack(self):
        return select(incidents.c.data, acknowledgements.c.acknowledged_by, acknowledgements.c.acknowledged_at, acknowledgements.c.note).select_from(
            incidents.outerjoin(acknowledgements, (acknowledgements.c.tenant == incidents.c.tenant) & (acknowledgements.c.incident_id == incidents.c.id)))

    def _merge_ack(self, row):
        ack = self._ack(row) if row["acknowledged_by"] else None
        return {**row["data"], "acknowledgement": ack}

    def list_incidents(self, tenant, limit=50, offset=0, lifecycle=None, truck_id=None):
        query = self._with_ack().where(incidents.c.tenant == tenant)
        if lifecycle:
            query = query.where(incidents.c.lifecycle == lifecycle)
        if truck_id:
            query = query.where(incidents.c.truck_id == truck_id)
        with self.engine.connect() as conn:
            return [self._merge_ack(row) for row in conn.execute(query.order_by(incidents.c.qualified_at.desc(), incidents.c.id).limit(limit).offset(offset)).mappings()]

    def detail(self, tenant, incident_id, limit=100, offset=0):
        with self.engine.connect() as conn:
            row = conn.execute(self._with_ack().where(incidents.c.tenant == tenant, incidents.c.id == incident_id)).mappings().first()
            if not row:
                return None
            incident = self._merge_ack(row)
            evidence = conn.execute(select(readings.c.payload).where(readings.c.tenant == tenant,
                readings.c.truck_id == incident["truck_id"], readings.c.status == "accepted",
                readings.c.event_at >= incident["excursion_started_at"], readings.c.event_at <= incident["last_observation_at"])
                .order_by(readings.c.event_at).limit(limit).offset(offset)).scalars().all()
            timeline = [{"kind": e["kind"], "actor": e["actor"], "at": e["at"], "details": e["details"]} for e in conn.execute(
                select(incident_events).where(incident_events.c.tenant == tenant, incident_events.c.incident_id == incident_id)
                .order_by(incident_events.c.id)).mappings()]
            deliveries = [self._notification(n) for n in conn.execute(select(outbox).where(outbox.c.tenant == tenant,
                outbox.c.incident_id == incident_id).order_by(outbox.c.id)).mappings()]
            return {**incident, "evidence": evidence, "evidence_limit": limit, "evidence_offset": offset,
                    "timeline": timeline, "notifications": deliveries}

    def get_truck_readings(self, tenant, truck_id, limit=100):
        with self.engine.connect() as conn:
            recent = select(
                readings.c.payload.label("payload"),
                readings.c.event_at.label("event_at"),
            ).where(
                    readings.c.tenant == tenant,
                    readings.c.truck_id == truck_id,
                    readings.c.status == "accepted"
                ).order_by(readings.c.event_at.desc()).limit(limit).subquery()
            return list(conn.execute(
                select(recent.c.payload).order_by(recent.c.event_at.asc())
            ).scalars())

    def get_readings_by_truck(self, tenant, limit_per_truck=50):
        with self.engine.connect() as conn:
            truck_ids = list(conn.execute(select(trucks.c.id).where(trucks.c.tenant == tenant)).scalars())
        return {tid: self.get_truck_readings(tenant, tid, limit_per_truck) for tid in truck_ids}

    # ---------- live-demo scenario runs ----------
    @staticmethod
    def _run(row):
        return {key: row[key] for key in ("id", "truck_id", "scenario", "status", "requested_by", "requested_at", "started_at", "completed_at")}

    def request_scenario(self, tenant, truck_id, scenario, actor):
        with self.write() as conn:
            truck = conn.execute(select(trucks.c.state).where(trucks.c.tenant == tenant, trucks.c.id == truck_id).with_for_update()).first()
            if truck is None:
                return None, "Truck not found"
            if (truck.state or {}).get("active"):
                return None, "Truck has an open incident; wait for recovery before starting a scenario"
            busy = conn.execute(select(demo_runs.c.id).where(demo_runs.c.tenant == tenant, demo_runs.c.truck_id == truck_id,
                                                             demo_runs.c.status.in_(ACTIVE_DEMO))).first()
            if busy:
                return None, "A scenario is already queued or running for this truck"
            result = conn.execute(demo_runs.insert().values(tenant=tenant, truck_id=truck_id, scenario=scenario, status="queued",
                                                            requested_by=actor, requested_at=utc(_now())))
            run_id = result.inserted_primary_key[0]
            return self._run(conn.execute(select(demo_runs).where(demo_runs.c.id == run_id)).mappings().one()), None

    def update_scenario(self, tenant, run_id, status):
        allowed = {"running": ("queued",), "completed": ("running",), "cancelled": ACTIVE_DEMO}[status]
        stamp = {"running": "started_at", "completed": "completed_at", "cancelled": "completed_at"}[status]
        with self.write() as conn:
            result = conn.execute(demo_runs.update().where(demo_runs.c.tenant == tenant, demo_runs.c.id == run_id, demo_runs.c.status.in_(allowed))
                                  .values(status=status, **{stamp: utc(_now())}))
            row = conn.execute(select(demo_runs).where(demo_runs.c.tenant == tenant, demo_runs.c.id == run_id)).mappings().first()
            return (self._run(row) if row else None), result.rowcount == 1

    def list_scenarios(self, tenant, active_only=False, limit=20):
        query = select(demo_runs).where(demo_runs.c.tenant == tenant)
        if active_only:
            query = query.where(demo_runs.c.status.in_(ACTIVE_DEMO))
        with self.engine.connect() as conn:
            runs = [self._run(row) for row in conn.execute(query.order_by(demo_runs.c.id.desc()).limit(limit)).mappings()]
            for run in runs:
                start = run["started_at"] or run["requested_at"]
                end = run["completed_at"] or utc(_now())
                opened = [data for data in conn.execute(select(incidents.c.data).where(incidents.c.tenant == tenant,
                          incidents.c.truck_id == run["truck_id"])).scalars()
                          if start <= data.get("opened_processed_at", "") <= end]
                run["observed_incident_id"] = opened[0]["id"] if opened else None
        return runs


def load_config(path="config/customers.json"):
    return Customers.model_validate_json(Path(path).read_text(encoding="utf-8")).model_dump(exclude_none=True)
