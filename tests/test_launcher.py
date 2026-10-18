"""Launcher lifecycle checks; the integration check requires installed frontend deps."""
import socket
import sys
import time

import httpx
import pytest

import run as launcher


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_occupied_port_fails_before_starting_services(monkeypatch, capsys):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        monkeypatch.setattr(sys, "argv", ["run.py", "--backend-port", str(listener.getsockname()[1])])
        assert launcher.main() == 1
        assert "unavailable" in capsys.readouterr().err


def test_both_services_start_and_keyboard_interrupt_cleans_up(monkeypatch, tmp_path):
    if not (launcher.ROOT / "frontend/node_modules/next/dist/bin/next").is_file():
        pytest.skip("Install frontend dependencies to exercise the full launcher")
    try:
        launcher.find_node()
    except RuntimeError:
        pytest.skip("Node 24+ is required for the launcher integration check")
    backend_port, frontend_port = free_port(), free_port()
    while frontend_port == backend_port:
        frontend_port = free_port()
    monkeypatch.setattr(sys, "argv", ["run.py", "--backend-port", str(backend_port),
                                      "--frontend-port", str(frontend_port), "--db", str(tmp_path / "demo.db")])
    monkeypatch.setenv("COLDLINE_NEXT_DIST_DIR", ".next-launcher-test")
    started = []
    original_start, original_sleep = launcher.start, time.sleep

    def track(*args):
        process = original_start(*args)
        started.append(process)
        return process

    def interrupt_when_ready(delay):
        if delay == 0.3:
            with httpx.Client(trust_env=False) as client:
                assert client.get(f"http://127.0.0.1:{backend_port}/health").status_code == 200
                assert "Username" in client.get(f"http://127.0.0.1:{frontend_port}").text
                assert client.get(f"http://127.0.0.1:{frontend_port}/api/v1/trucks").status_code == 401
            raise KeyboardInterrupt
        original_sleep(delay)

    monkeypatch.setattr(launcher, "start", track)
    monkeypatch.setattr(launcher.time, "sleep", interrupt_when_ready)
    assert launcher.main() == 0
    assert len(started) == 2
    assert all(process.poll() is not None for process in started)
    for port in (backend_port, frontend_port):
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", port)) != 0
