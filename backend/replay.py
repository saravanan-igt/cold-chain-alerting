"""Explicit offline normalization; production API never assumes a timezone."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.domain import Reading, utc
from starter_kit.alert_utils import load_readings


def normalize(raw, devices, assume_utc=False):
    identities, timestamps = {}, {}
    duplicates = 0
    rows = []
    for source in raw:
        row = dict(source)
        parsed = datetime.fromisoformat(row["timestamp"])
        if parsed.tzinfo is None:
            if not assume_utc:
                raise ValueError("Dataset timestamps lack timezone; explicitly pass --assume-utc")
            row["timestamp"] = utc(parsed.replace(tzinfo=timezone.utc))
        if "device_id" not in row:
            row["device_id"] = devices[row["truck_id"]]
        validated = Reading.model_validate(row)
        row = validated.canonical()
        canonical = json.dumps(row, sort_keys=True)
        identity = (row["device_id"], row["event_id"] or canonical)
        timestamp = (row["truck_id"], row["timestamp"])
        if identity in identities:
            if identities[identity] != canonical:
                raise ValueError("Conflicting event identity in replay")
            duplicates += 1
            continue
        if timestamp in timestamps:
            raise ValueError("Conflicting stream timestamp in replay")
        identities[identity], timestamps[timestamp] = canonical, canonical
        rows.append(row)
    return sorted(rows, key=lambda row: (row["truck_id"], row["timestamp"])), duplicates


def replay(store, config, source, tenant="nimbus", assume_utc=False):
    customer = next(item for item in config["tenants"] if item["id"] == tenant)
    devices = {truck["id"]: truck["device_id"] for truck in customer["trucks"]}
    rows, duplicates = normalize(load_readings(source), devices, assume_utc)
    store.provision(config)
    counts = Counter({"duplicate_in_file": duplicates})
    for row in rows:
        outcome = store.ingest(tenant, row, live=False)
        counts[outcome["status"]] += 1
        if outcome["status"] not in ("accepted", "duplicate"):
            raise ValueError(f"Replay requires a clean or identical replay database: {outcome}")
    incidents = store.list_incidents(tenant, limit=100000)
    reference = max((row["timestamp"] for row in rows), default=None)
    return {"mode": "historical replay", "source": str(source), "timezone_assumption": "UTC" if assume_utc else "source offsets",
        "reference_time": reference, "counts": dict(counts), "incidents": incidents,
        "fleet": store.fleet(tenant, datetime.fromisoformat(reference)) if reference else None}


def print_report(report):
    print(f"Historical replay | reference: {report['reference_time']} | {report['counts']}")
    print("Truck  Start (UTC)  Qualified  Lifecycle  Peak C  Evidence  Recovery")
    for incident in sorted(report["incidents"], key=lambda i: (i["truck_id"], i["qualified_at"])):
        print(f"{incident['truck_id']:6} {incident['excursion_started_at'][11:16]:12} {incident['qualified_at'][11:16]:10} {incident['lifecycle']:10} {incident['observed_max_c']:6.1f} {incident['evidence_count']:9} {(incident['recovery_confirmed_at'] or '')[11:16]}")
        print("  " + incident["explanation"])
