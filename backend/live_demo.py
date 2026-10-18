"""Current-time simulation using the seed temperatures; never connected hardware."""
from datetime import datetime, timezone
import time
import uuid

import httpx
from backend.replay import normalize
from starter_kit.alert_utils import load_readings


def frames(source, customer):
    devices = {truck["id"]: truck["device_id"] for truck in customer["trucks"]}
    rows, _ = normalize(load_readings(source), devices, assume_utc=True)
    timestamps = sorted({row["timestamp"] for row in rows})
    result = [[row for row in rows if row["timestamp"] == stamp] for stamp in timestamps]
    # Additional normal observations prove recovery under the explicit 20-second demo rule.
    return result + [result[-1]] * 4


def current_readings(frame, observed_at, run_id, tick):
    return [{**row, "timestamp": observed_at.isoformat(), "event_id": f"live-demo:{run_id}:{tick}:{row['truck_id']}"} for row in frame]


def stream(url, source, customer, credentials, stop):
    sequence = frames(source, customer)
    keys = {identity["device_id"]: key for key, identity in credentials.items()
            if identity["role"] == "device" and identity["tenant"] == customer["id"]}
    run_id, tick = uuid.uuid4().hex, 0
    with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
        while not stop.is_set():
            try:
                if client.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            stop.wait(.25)
        deadline = time.monotonic()
        print("LIVE SIMULATION: seed temperatures, current UTC timestamps, 10-second samples; 30-second trigger / 20-second recovery.", flush=True)
        while not stop.is_set():
            frame = sequence[tick % len(sequence)]
            rows = current_readings(frame, datetime.now(timezone.utc), run_id, tick)
            for row in rows:
                if stop.is_set():
                    return
                try:
                    response = client.post("/api/v1/readings", json={"readings": [row]}, headers={"X-API-Key": keys[row["device_id"]]})
                    response.raise_for_status()
                    outcome = response.json()["results"][0]
                    print(f"[simulation] {row['truck_id']} {row['temperature_c']} C: {outcome['status']}", flush=True)
                    if outcome["status"] not in ("accepted", "duplicate"):
                        raise RuntimeError(f"Simulation stopped: {outcome}")
                except httpx.HTTPError as exc:
                    print(f"[simulation] Delivery failed; observation not backfilled: {type(exc).__name__}", flush=True)
            tick += 1
            deadline += 10
            # Never catch up with a burst of fabricated historical timestamps after a delay.
            if deadline < time.monotonic():
                deadline = time.monotonic() + 10
            stop.wait(max(0, deadline - time.monotonic()))
