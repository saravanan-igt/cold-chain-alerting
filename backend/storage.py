"""SQLite schema v1 and serialized transactional application service."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import (JSON, Column, ForeignKeyConstraint, Index, Integer, MetaData,
                        String, Table, UniqueConstraint, create_engine, event, select)

from backend.domain import Reading, Rule, advance, seconds, utc
from backend.configuration import Customers

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
Index("ix_incidents_tenant_lifecycle_time", incidents.c.tenant, incidents.c.lifecycle, incidents.c.qualified_at)
Index("ix_readings_evidence", readings.c.tenant, readings.c.truck_id, readings.c.status, readings.c.event_at)


class Store:
    def __init__(self, path):
        self.engine = create_engine(f"sqlite:///{Path(path).as_posix()}", connect_args={"timeout": 30, "check_same_thread": False})
        @event.listens_for(self.engine, "connect")
        def pragmas(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
        with self.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        with self.write() as conn:
            version = conn.exec_driver_sql("PRAGMA user_version").scalar()
            if version not in (0, 1):
                raise RuntimeError(f"Unsupported schema version {version}")
            if version == 0:
                metadata.create_all(conn)
                conn.exec_driver_sql("PRAGMA user_version=1")

    @contextmanager
    def write(self):
        # Acquire the SQLite writer reservation BEFORE reading detector state.
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def provision(self, config):
        config = Customers.model_validate(config).model_dump(exclude_none=True)
        with self.write() as conn:
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

    def ingest(self, tenant, raw, binding=None, live=True):
        try:
            reading = Reading.model_validate(raw)
        except ValidationError as exc:
            return {"status": "invalid", "reason": str(exc)}
        now = datetime.now(timezone.utc)
        if live and reading.timestamp > now + timedelta(minutes=5):
            return {"status": "invalid", "reason": "event time exceeds allowed 5-minute clock skew"}
        if binding and (reading.truck_id != binding["truck_id"] or reading.device_id != binding["device_id"]):
            return {"status": "unauthorized", "reason": "credential does not authorize this stream"}
        payload = reading.canonical()
        fingerprint = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        identity = "event:" + reading.event_id if reading.event_id else "hash:" + fingerprint
        condition = (trucks.c.tenant == tenant) & (trucks.c.id == reading.truck_id)
        with self.write() as conn:
            truck = conn.execute(select(trucks).where(condition)).mappings().first()
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
            previous = truck["state"]
            late = bool(previous.get("last_at") and payload["timestamp"] < previous["last_at"])
            status = "late" if late else "accepted"
            result = conn.execute(readings.insert().values(tenant=tenant, truck_id=reading.truck_id, device_id=reading.device_id,
                identity=identity, fingerprint=fingerprint, event_at=payload["timestamp"], ingested_at=utc(now), status=status, payload=payload))
            incident_id = None
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
                    else:
                        conn.execute(incidents.update().where(incidents.c.tenant == tenant, incidents.c.id == incident_id).values(**values))
            return {"status": status, "reading_id": result.inserted_primary_key[0], "incident_id": incident_id}

    def fleet(self, tenant, at=None):
        at = at or datetime.now(timezone.utc)
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

    def list_incidents(self, tenant, limit=50, offset=0, lifecycle=None, truck_id=None):
        query = select(incidents.c.data).where(incidents.c.tenant == tenant)
        if lifecycle:
            query = query.where(incidents.c.lifecycle == lifecycle)
        if truck_id:
            query = query.where(incidents.c.truck_id == truck_id)
        with self.engine.connect() as conn:
            return list(conn.execute(query.order_by(incidents.c.qualified_at.desc(), incidents.c.id).limit(limit).offset(offset)).scalars())

    def detail(self, tenant, incident_id, limit=100, offset=0):
        with self.engine.connect() as conn:
            incident = conn.execute(select(incidents.c.data).where(incidents.c.tenant == tenant, incidents.c.id == incident_id)).scalar_one_or_none()
            if not incident:
                return None
            evidence = conn.execute(select(readings.c.payload).where(readings.c.tenant == tenant,
                readings.c.truck_id == incident["truck_id"], readings.c.status == "accepted",
                readings.c.event_at >= incident["excursion_started_at"], readings.c.event_at <= incident["last_observation_at"])
                .order_by(readings.c.event_at).limit(limit).offset(offset)).scalars().all()
            return {**incident, "evidence": evidence, "evidence_limit": limit, "evidence_offset": offset}

    def get_truck_readings(self, tenant, truck_id, limit=100):
        with self.engine.connect() as conn:
            return list(conn.execute(
                select(readings.c.payload).where(
                    readings.c.tenant == tenant,
                    readings.c.truck_id == truck_id,
                    readings.c.status == "accepted"
                ).order_by(readings.c.event_at.asc()).limit(limit)
            ).scalars())

    def get_readings_by_truck(self, tenant, limit_per_truck=50):
        with self.engine.connect() as conn:
            truck_ids = list(conn.execute(select(trucks.c.id).where(trucks.c.tenant == tenant)).scalars())
            result = {}
            for tid in truck_ids:
                rows = list(conn.execute(
                    select(readings.c.payload).where(
                        readings.c.tenant == tenant,
                        readings.c.truck_id == tid,
                        readings.c.status == "accepted"
                    ).order_by(readings.c.event_at.asc()).limit(limit_per_truck)
                ).scalars())
                result[tid] = rows
            return result


def load_config(path="config/customers.json"):
    return Customers.model_validate_json(Path(path).read_text(encoding="utf-8")).model_dump(exclude_none=True)
