"""Start the local Coldline demo API and Next.js development server together."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent


def require_free_port(port: int) -> None:
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(
                f"Port {port} is unavailable. Stop the service using it or choose another port."
            ) from exc


def find_node() -> str:
    candidates = [
        ROOT / ".runtime/node/node.exe",
        ROOT / ".runtime/node/bin/node",
        ROOT / ".runtime/node/node_modules/node/bin/node.exe",
        ROOT / ".runtime/node/node_modules/node/bin/node",
    ]
    installed = shutil.which("node")
    if installed:
        candidates.append(Path(installed))
    for candidate in candidates:
        if candidate.is_file():
            result = subprocess.run([str(candidate), "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                version = tuple(int(part) for part in result.stdout.strip().lstrip("v").split(".")[:2])
                if version >= (24, 15):
                    return str(candidate)
    raise RuntimeError("Node.js 24.15+ is required. Install it or use the project-local .runtime Node installation.")


def start(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    # Keep logs in this terminal. Give each service its own process group so cleanup
    # includes Next's worker process without touching any existing user services.
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen(command, cwd=cwd, env=env, **options)


def wait_ready(process: subprocess.Popen, url: str, label: str, timeout: float) -> None:
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited with code {process.returncode}; see its output above.")
        try:
            with opener.open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"{label} did not become ready within {timeout:g} seconds.")


def stop(process: subprocess.Popen) -> None:
    if os.name == "nt":
        # Only terminate trees launched by this script, and never reuse an exited PID.
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--db", default=None, help="Persistent demo database (never automatically deleted)")
    parser.add_argument("--live", action="store_true", help="Stream current-time simulated telemetry using fast, labelled demo rules")
    parser.add_argument("--baseline", choices=["seed", "steady"], default="seed",
                        help="With --live: replay seed temperatures, or keep trucks steady so only injected demo scenarios excurse")
    parser.add_argument("--startup-timeout", type=float, default=120)
    args = parser.parse_args()
    if args.baseline != "seed" and not args.live:
        parser.error("--baseline requires --live")
    args.db = args.db or ("live-demo.db" if args.live else "dev.db")
    processes: list[subprocess.Popen] = []
    try:
        if not 1 <= args.backend_port <= 65535 or not 1 <= args.frontend_port <= 65535:
            raise RuntimeError("Ports must be between 1 and 65535.")
        if args.backend_port == args.frontend_port:
            raise RuntimeError("Frontend and backend ports must be different.")
        if args.startup_timeout <= 0:
            raise RuntimeError("Startup timeout must be positive.")
        for port in (args.backend_port, args.frontend_port):
            require_free_port(port)

        python = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        interpreter = str(python) if python.is_file() else sys.executable
        check = subprocess.run([interpreter, "-c", "import fastapi, uvicorn, sqlalchemy, pydantic"], capture_output=True)
        if check.returncode:
            raise RuntimeError("Backend dependencies are missing. Install requirements.txt into .venv first (see README.md).")
        node = find_node()
        next_cli = ROOT / "frontend/node_modules/next/dist/bin/next"
        if not next_cli.is_file():
            raise RuntimeError("Frontend dependencies are missing. Run npm ci in frontend with Node 24.15+ first.")

        backend_url = f"http://127.0.0.1:{args.backend_port}"
        frontend_url = f"http://127.0.0.1:{args.frontend_port}"
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "NEXT_TELEMETRY_DISABLED": "1",
               "BACKEND_ORIGIN": backend_url,
               "PATH": str(Path(node).parent) + os.pathsep + os.environ.get("PATH", "")}
        print("Starting Coldline demo. Data is preserved; Ctrl+C stops both services.\n", flush=True)
        backend = start([interpreter, "-m", "backend.cli", "live-demo" if args.live else "demo", "--db", args.db,
                         "--assume-utc", "--output", "data/dev-replay.json", "--port", str(args.backend_port),
                         *(["--baseline", args.baseline] if args.live else [])], ROOT, env)
        processes.append(backend)
        wait_ready(backend, backend_url + "/health", "Backend", args.startup_timeout)
        frontend = start([node, str(next_cli), "dev", "--hostname", "127.0.0.1", "--port", str(args.frontend_port)], ROOT / "frontend", env)
        processes.append(frontend)
        wait_ready(frontend, frontend_url, "Frontend", args.startup_timeout)
        print("  Browser passwords are stable: see config/demo-passwords.local.json (edit to change).", flush=True)
        print(f"\nColdline is ready!\n  Frontend: {frontend_url}\n  API docs: {backend_url}/docs\n"
              "  Login: username=nimbus.demo  password=nimbus123\n"
              "  Press Ctrl+C here to stop both services.\n", flush=True)
        while True:
            for label, process in (("Backend", backend), ("Frontend", frontend)):
                if process.poll() is not None:
                    raise RuntimeError(f"{label} stopped unexpectedly (exit {process.returncode}). Stopping the other service.")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nStopping Coldline…", flush=True)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"\nCannot run Coldline: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        for process in reversed(processes):
            stop(process)


if __name__ == "__main__":
    # CTRL_BREAK_EVENT also supports controlled shutdown from Windows terminals/tests.
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    raise SystemExit(main())
