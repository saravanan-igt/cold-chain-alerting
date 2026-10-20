import argparse
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from backend.replay import print_report, replay
from backend.storage import Store, load_config
from backend.auth import hash_password


def maintenance(args):
    """Commands that never start the API: backup, restore, verify-backup and the standalone worker."""
    if args.command in ("backup", "restore") and "://" in args.db and not args.db.startswith("sqlite"):
        raise SystemExit("Backup/restore commands cover SQLite. Use managed point-in-time recovery or pg_dump for PostgreSQL.")
    if args.command in ("backup", "restore") and args.db.startswith("sqlite:///"):
        args.db = args.db.removeprefix("sqlite:///")
    if args.command == "backup":
        from backend import backup
        output = args.output if args.output != DEFAULT_OUTPUT else f"backups/coldline-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.db"
        print(json.dumps(backup.backup(args.db, output), indent=2))
    elif args.command == "verify-backup":
        from backend import backup
        print(json.dumps(backup.verify(args.input), indent=2))
    elif args.command == "restore":
        from backend import backup
        print(json.dumps(backup.restore(args.input, args.db, force=args.force), indent=2))
    elif args.command == "worker":
        import signal
        import threading
        from backend.notifications import NotificationWorker
        from backend.observability import configure_logging, logger
        configure_logging()
        store = Store(args.db)
        store.provision(load_config(args.config))
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
        worker = NotificationWorker(store).start()
        logger.info("Notification worker running; Ctrl+C to stop", extra={"event": "worker_start"})
        while not stop.wait(1):
            pass
        worker.stop()
        store.engine.dispose()


DEFAULT_OUTPUT = "data/replay.json"


def main():
    parser = argparse.ArgumentParser(description="Coldline local operations")
    parser.add_argument("command", choices=["replay", "serve", "demo", "live-demo", "worker", "backup", "restore", "verify-backup"])
    parser.add_argument("--db", default=None, help="SQLite path or SQLAlchemy URL (default: COLDCHAIN_DATABASE_URL or a local file)")
    parser.add_argument("--config", default=None)
    parser.add_argument("--source", default="starter_kit/data/sensor_readings.json")
    parser.add_argument("--tenant", default="nimbus")
    parser.add_argument("--assume-utc", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--input", help="Backup file for restore/verify-backup")
    parser.add_argument("--force", action="store_true", help="Allow restore to replace an existing database")
    parser.add_argument("--baseline", choices=["seed", "steady"], default="seed",
                        help="live-demo: replay seed temperatures, or keep all trucks steady so only injected scenarios excurse")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    args.db = args.db or os.getenv("COLDCHAIN_DATABASE_URL") or ("live-demo.db" if args.command == "live-demo" else "coldchain.db")
    args.config = args.config or ("config/live-demo.json" if args.command == "live-demo"
                                  else os.getenv("COLDCHAIN_CONFIG") or "config/customers.json")
    if args.command in ("restore", "verify-backup") and not args.input:
        parser.error(f"{args.command} requires --input")
    if args.command in ("worker", "backup", "restore", "verify-backup"):
        return maintenance(args)
    config = load_config(args.config)
    os.environ["COLDCHAIN_DATABASE_URL"], os.environ["COLDCHAIN_CONFIG"] = args.db, args.config
    if args.command in ("replay", "demo"):
        store = Store(args.db)
        try:
            report = replay(store, config, args.source, args.tenant, args.assume_utc)
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print_report(report)
            print(f"Export: {target}")
        finally:
            store.engine.dispose()
    if args.command in ("demo", "live-demo"):
        credentials = {}
        users = {}
        for tenant in config["tenants"]:
            username = tenant["id"] + ".demo"
            configured_password = os.environ.get("COLDCHAIN_DEMO_PASSWORD")
            password = configured_password or secrets.token_urlsafe(18)
            users[username] = {"tenant": tenant["id"], "password_hash": hash_password(password)}
            if configured_password:
                print("Browser password was supplied via COLDCHAIN_DEMO_PASSWORD.", flush=True)
            else:
                print(f"Generated browser password: {password}", flush=True)
            print(f"Browser login ({tenant['name']}): username={username}  password={password}", flush=True)
            key = secrets.token_urlsafe(24)
            credentials[key] = {"role": "operator", "tenant": tenant["id"]}
            print(f"Operator key ({tenant['name']}): {key}")
            for truck in tenant["trucks"]:
                key = secrets.token_urlsafe(24)
                credentials[key] = {"role": "device", "tenant": tenant["id"], "truck_id": truck["id"], "device_id": truck["device_id"]}
                print(f"Device key ({tenant['id']}/{truck['id']}): {key}")
        os.environ["COLDCHAIN_CREDENTIALS"] = json.dumps(credentials)
        os.environ["COLDCHAIN_USERS"] = json.dumps(users)
    if args.command in ("serve", "demo", "live-demo"):
        import uvicorn
        import threading
        stop = threading.Event()
        worker = None
        if args.command == "live-demo":
            from backend.live_demo import stream
            customer = next(t for t in config["tenants"] if t["id"] == args.tenant)
            if customer.get("demo_mode") != "live_simulation":
                raise ValueError("Live simulation requires an explicitly labelled live-demo configuration")
            worker = threading.Thread(target=stream, args=(f"http://127.0.0.1:{args.port}", args.source, customer, credentials, stop, args.baseline), daemon=True)
            worker.start()
        print(f"Dashboard: http://127.0.0.1:{args.port} | API docs: /docs", flush=True)
        try:
            uvicorn.run("backend.api:create_app", factory=True, host=args.host, port=args.port, workers=1)
        finally:
            stop.set()
            if worker:
                worker.join(timeout=6)


if __name__ == "__main__":
    main()
