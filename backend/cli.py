import argparse
import json
import os
import secrets
from pathlib import Path

from backend.replay import print_report, replay
from backend.storage import Store, load_config
from backend.auth import hash_password


def main():
    parser = argparse.ArgumentParser(description="Coldline local operations")
    parser.add_argument("command", choices=["replay", "serve", "demo", "live-demo"])
    parser.add_argument("--db", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--source", default="starter_kit/data/sensor_readings.json")
    parser.add_argument("--tenant", default="nimbus")
    parser.add_argument("--assume-utc", action="store_true")
    parser.add_argument("--output", default="data/replay.json")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    args.db = args.db or ("live-demo.db" if args.command == "live-demo" else "coldchain.db")
    args.config = args.config or ("config/live-demo.json" if args.command == "live-demo" else "config/customers.json")
    config = load_config(args.config)
    os.environ["COLDCHAIN_DB"], os.environ["COLDCHAIN_CONFIG"] = args.db, args.config
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
            default_pw = "nimbus123" if tenant["id"] == "nimbus" else f"{tenant['id']}123"
            password = os.environ.get("COLDCHAIN_DEMO_PASSWORD", default_pw)
            users[username] = {"tenant": tenant["id"], "password_hash": hash_password(password)}
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
            worker = threading.Thread(target=stream, args=(f"http://127.0.0.1:{args.port}", args.source, customer, credentials, stop), daemon=True)
            worker.start()
        print(f"Dashboard: http://127.0.0.1:{args.port} | API docs: /docs", flush=True)
        try:
            uvicorn.run("backend.api:create_app", factory=True, host="127.0.0.1", port=args.port, workers=1)
        finally:
            stop.set()
            if worker:
                worker.join(timeout=6)


if __name__ == "__main__":
    main()
