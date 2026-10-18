"""Deterministic HTTP scenario. Uses an existing device credential via env var."""
import argparse
import os
from datetime import datetime, timedelta, timezone
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--key-env", default="DEVICE_KEY")
    parser.add_argument("--truck", default="T-01")
    parser.add_argument("--device", default="sensor-T-01")
    args = parser.parse_args()
    key = os.environ[args.key_env]
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=95)
    # Spike, sustained excursion, recovery attempt interrupted by a gap, then recovery.
    scenario = [(0, 6), (5, 9), (10, 6), (15, 9), (20, 9), (25, 9), (30, 9), (35, 7), (50, 7), (55, 7)]
    with httpx.Client(base_url=args.url, headers={"X-API-Key": key}, timeout=30) as client:
        rows = [{"truck_id": args.truck, "device_id": args.device,
                 "timestamp": (start + timedelta(minutes=minute)).isoformat(), "temperature_c": temp} for minute, temp in scenario]
        rows += [rows[-1], {**rows[0], "timestamp": (start + timedelta(minutes=32)).isoformat()}]
        for row in rows:
            response = client.post("/api/v1/readings", json={"readings": [row]})
            response.raise_for_status()
            print(row["timestamp"], row["temperature_c"], response.json()["results"][0])


if __name__ == "__main__":
    main()
