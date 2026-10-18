"""Actual TCP smoke test: built frontend, API and the HTTP simulator."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import json

import httpx


def test_server_and_simulator(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    device_key, operator_key = secrets.token_urlsafe(), secrets.token_urlsafe()
    env = {**os.environ, "COLDCHAIN_DB": str(tmp_path / "http.db"), "DEVICE_KEY": device_key,
           "COLDCHAIN_CONFIG": str(Path("config/customers.json").resolve()),
           "COLDCHAIN_CREDENTIALS": json.dumps({device_key: {"tenant": "nimbus", "role": "device", "truck_id": "T-01", "device_id": "sensor-T-01"},
                                               operator_key: {"tenant": "nimbus", "role": "operator"}})}
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.api:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base, timeout=2) as client:
            for _ in range(100):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.05)
            else:
                raise AssertionError("Local server did not start")
            if Path("frontend/out/index.html").exists():
                page = client.get("/")
                assert page.status_code == 200 and "Coldline" in page.text
                export_root = Path("frontend/out")
                for asset in (export_root / "_next/static").rglob("*"):
                    if asset.is_file():
                        assert client.get("/" + asset.relative_to(export_root).as_posix()).status_code == 200
            result = subprocess.run([sys.executable, "-m", "backend.simulator", "--url", base], env=env, capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stderr
            assert result.stdout.count("'status': 'accepted'") == 10
            assert result.stdout.count("'status': 'duplicate'") == 1
            assert result.stdout.count("'status': 'late'") == 1
            incidents = client.get("/api/v1/incidents", headers={"X-API-Key": operator_key}).json()["items"]
            assert len(incidents) == 1 and incidents[0]["lifecycle"] == "recovered"
            assert incidents[0]["telemetry_gap_count"] == 1
    finally:
        process.terminate()
        process.wait(timeout=10)
