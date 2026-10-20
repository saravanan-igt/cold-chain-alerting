"""Consistent SQLite backup, verification and restore.

Uses SQLite's online backup API, so a backup can be taken while the service is
running (WAL readers are not blocked). Every backup gets a JSON manifest with a
SHA-256 digest, schema version and row counts; restore refuses a backup that fails
``PRAGMA integrity_check`` or the digest. PostgreSQL deployments use managed PITR
(see SOLUTION_DESIGN.md, "Backup and recovery").
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

TABLES = ("tenants", "trucks", "readings", "incidents", "opening_alerts", "incident_events",
          "incident_acknowledgements", "notification_outbox")


def _digest(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _inspect(path):
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        present = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES if table in present}
        return integrity, version, counts
    finally:
        conn.close()


def _copy(source, target):
    src = sqlite3.connect(Path(source).as_posix())
    dst = sqlite3.connect(Path(target).as_posix())
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def backup(db_path, output):
    db_path, output = Path(db_path), Path(output)
    if not db_path.is_file():
        raise FileNotFoundError(f"Database {db_path} does not exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    partial.unlink(missing_ok=True)
    _copy(db_path, partial)
    integrity, version, counts = _inspect(partial)
    if integrity != "ok":
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Backup failed integrity check: {integrity}")
    os.replace(partial, output)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "source": str(db_path), "file": output.name,
                "sha256": _digest(output), "bytes": output.stat().st_size, "schema_version": version, "row_counts": counts}
    Path(str(output) + ".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify(path):
    path = Path(path)
    manifest_path = Path(str(path) + ".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None
    if manifest and manifest["sha256"] != _digest(path):
        raise RuntimeError("Backup digest does not match its manifest")
    integrity, version, counts = _inspect(path)
    if integrity != "ok":
        raise RuntimeError(f"Backup failed integrity check: {integrity}")
    return {"schema_version": version, "row_counts": counts, "manifest": bool(manifest)}


def restore(backup_path, db_path, force=False):
    """Restore into a stopped service's database path. Existing data is only replaced with ``force``."""
    from backend.storage import SCHEMA_VERSION
    report = verify(backup_path)
    if report["schema_version"] > SCHEMA_VERSION:
        raise RuntimeError(f"Backup schema v{report['schema_version']} is newer than this release (v{SCHEMA_VERSION})")
    db_path = Path(db_path)
    if db_path.exists() and not force:
        raise FileExistsError(f"{db_path} exists; stop the service and pass --force to replace it")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _copy(backup_path, db_path)
    integrity, _, counts = _inspect(db_path)
    if integrity != "ok":
        raise RuntimeError(f"Restored database failed integrity check: {integrity}")
    return {"restored_to": str(db_path), "row_counts": counts}
