"""Current-time simulation using the seed temperatures; never connected hardware.

The simulator is an ordinary API client: it sends telemetry with per-device keys
through ``/api/v1/readings`` and polls operator-requested demo scenarios through
``/api/v1/demo/scenarios``. The detector decides every outcome; scenarios only
shape the simulated temperatures.
"""
from datetime import datetime, timezone
import time
import uuid

import httpx
from backend.replay import normalize
from backend.scenarios import NORMAL_C
from starter_kit.alert_utils import load_readings


def frames(source, customer):
    devices = {truck["id"]: truck["device_id"] for truck in customer["trucks"]}
    rows, _ = normalize(load_readings(source), devices, assume_utc=True)
    timestamps = sorted({row["timestamp"] for row in rows})
    result = [[row for row in rows if row["timestamp"] == stamp] for stamp in timestamps]
    # Additional normal observations prove recovery under the explicit 20-second demo rule.
    return result + [result[-1]] * 4


def steady_frame(customer, tick):
    """All trucks inside range, so injected scenarios are the only excursions on screen."""
    return [{"truck_id": truck["id"], "device_id": truck["device_id"],
             "temperature_c": round(NORMAL_C + ((tick + index) % 3) * 0.1, 1)}
            for index, truck in enumerate(customer["trucks"])]


def current_readings(frame, observed_at, run_id, tick):
    return [{**row, "timestamp": observed_at.isoformat(), "event_id": f"live-demo:{run_id}:{tick}:{row['truck_id']}"} for row in frame]


class ScenarioPlayer:
    """Plays queued scenario steps, one per sample, overriding the baseline for that truck."""

    def __init__(self, client, operator_key):
        self.client, self.headers = client, {"X-API-Key": operator_key} if operator_key else None
        self.progress, self.finished = {}, []

    def _patch(self, run_id, status):
        try:
            self.client.patch(f"/api/v1/demo/scenarios/{run_id}", json={"status": status}, headers=self.headers)
        except httpx.HTTPError:
            pass

    def overrides(self):
        if not self.headers:
            return {}
        try:
            response = self.client.get("/api/v1/demo/scenarios", params={"active": "true"}, headers=self.headers)
            runs = response.json()["runs"] if response.status_code == 200 else []
        except (httpx.HTTPError, ValueError, KeyError):
            return {}
        result = {}
        active = {run["id"] for run in runs}
        self.progress = {key: value for key, value in self.progress.items() if key in active}
        for run in sorted(runs, key=lambda item: item["id"]):
            if run["status"] == "queued":
                self._patch(run["id"], "running")
            step = self.progress.setdefault(run["id"], 0)
            steps = run["steps"]
            if step >= len(steps):
                self.finished.append(run["id"])
                continue
            result[run["truck_id"]] = steps[step]
            shown = "no sample (telemetry gap)" if steps[step] is None else f"{steps[step]} C"
            print(f"[scenario] {run['truck_id']} {run['scenario']} step {step + 1}/{len(steps)}: {shown}", flush=True)
            self.progress[run["id"]] = step + 1
            if step + 1 >= len(steps):
                self.finished.append(run["id"])
        return result

    def complete(self):
        for run_id in self.finished:
            self._patch(run_id, "completed")
            self.progress.pop(run_id, None)
        self.finished = []


def stream(url, source, customer, credentials, stop, baseline="seed"):
    sequence = frames(source, customer) if baseline == "seed" else None
    keys = {identity["device_id"]: key for key, identity in credentials.items()
            if identity["role"] == "device" and identity["tenant"] == customer["id"]}
    operator_key = next((key for key, identity in credentials.items()
                         if identity["role"] == "operator" and identity["tenant"] == customer["id"]), None)
    run_id, tick = uuid.uuid4().hex, 0
    with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
        while not stop.is_set():
            try:
                if client.get("/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            stop.wait(.25)
        player = ScenarioPlayer(client, operator_key)
        deadline = time.monotonic()
        print(f"LIVE SIMULATION ({baseline} baseline): current UTC timestamps, 10-second samples; 30-second trigger / 20-second recovery. "
              "Inject genuine/non-genuine scenarios from the dashboard.", flush=True)
        while not stop.is_set():
            frame = sequence[tick % len(sequence)] if sequence else steady_frame(customer, tick)
            overrides = player.overrides()
            frame = [{**row, "temperature_c": overrides[row["truck_id"]]} if row["truck_id"] in overrides else row
                     for row in frame if not (row["truck_id"] in overrides and overrides[row["truck_id"]] is None)]
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
            player.complete()
            tick += 1
            deadline += 10
            # Never catch up with a burst of fabricated historical timestamps after a delay.
            if deadline < time.monotonic():
                deadline = time.monotonic() + 10
            stop.wait(max(0, deadline - time.monotonic()))
