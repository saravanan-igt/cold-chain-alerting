"""Notification delivery worker for the transactional outbox.

Delivery is at-least-once: each attempt carries a stable ``X-Coldline-Delivery`` id
so receivers can de-duplicate. Webhooks are HMAC-SHA256 signed over
``"{timestamp}.{body}"`` with a secret read from the environment at send time.
Retryable failures back off exponentially; permanent failures and exhausted retries
are dead-lettered for operator review and manual retry.
"""
import hashlib
import hmac
import json
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from backend.observability import logger, metrics
from backend.storage import MAX_DELIVERY_ATTEMPTS


class PermanentDeliveryError(Exception):
    pass


def backoff_seconds(attempt):
    return min(900, 5 * 2 ** (attempt - 1)) * random.uniform(0.8, 1.2)


def summary(payload):
    incident = payload["incident"]
    verb = {"incident.opened": "OPENED", "incident.recovered": "RECOVERED", "incident.acknowledged": "ACKNOWLEDGED",
            "incident.escalated": f"ESCALATED (level {payload.get('escalation_level')}) - unacknowledged"}[payload["event"]]
    text = (f"[Coldline] {payload['tenant']} truck {incident['truck_id']}: temperature incident {verb}. "
            f"Above {payload['rule']['threshold_c']:g} C since {incident['excursion_started_at']}; observed max {incident['observed_max_c']:g} C.")
    if payload.get("acknowledgement"):
        text += f" Acknowledged by {payload['acknowledgement']['acknowledged_by']}."
    return text


def sign(secret, timestamp, body):
    return "v1=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def deliver(channel, row, client):
    payload = row["payload"]
    if channel["type"] == "log":
        logger.warning(summary(payload), extra={"event": "notification", "tenant": row["tenant"], "incident_id": row["incident_id"],
                                                "channel": channel["id"], "notification_id": row["id"]})
        return
    content = {"text": summary(payload)} if channel.get("format") == "slack" else payload
    body = json.dumps(content, separators=(",", ":"), sort_keys=True).encode()
    timestamp = str(int(time.time()))
    headers = {"Content-Type": "application/json", "User-Agent": "Coldline-Notifier/2",
               "X-Coldline-Event": payload["event"], "X-Coldline-Delivery": f"{row['tenant']}:{row['id']}",
               "X-Coldline-Timestamp": timestamp}
    if channel.get("secret_env"):
        secret = os.environ.get(channel["secret_env"])
        if not secret:
            raise RuntimeError(f"Signing secret {channel['secret_env']} is not configured")
        headers["X-Coldline-Signature"] = sign(secret, timestamp, body)
    response = client.post(channel["url"], content=body, headers=headers)
    if 200 <= response.status_code < 300:
        return
    if response.status_code in (408, 429) or response.status_code >= 500:
        raise RuntimeError(f"HTTP {response.status_code}")
    raise PermanentDeliveryError(f"HTTP {response.status_code}")


class NotificationWorker:
    def __init__(self, store, interval=2.0, client=None):
        self.store, self.interval = store, interval
        self.client = client or httpx.Client(timeout=5, follow_redirects=False)
        self.stop_event = threading.Event()
        self.thread = None
        self.last_run = None

    def run_once(self, now=None):
        now = now or datetime.now(timezone.utc)
        counts = {"escalated": 0, "delivered": 0, "retry": 0, "dead": 0}
        for tenant, incident_id, level in self.store.due_escalations(now):
            if self.store.escalate(tenant, incident_id, level, now):
                counts["escalated"] += 1
                logger.warning("Incident escalated", extra={"event": "escalation", "tenant": tenant, "incident_id": incident_id, "level_index": level})
        configs = {}
        for row in self.store.claim_notifications(now):
            if row["tenant"] not in configs:
                configs[row["tenant"]] = {c["id"]: c for c in ((self.store.tenant_config(row["tenant"]) or {}).get("notifications") or {}).get("channels", [])}
            channel = configs[row["tenant"]].get(row["channel_id"])
            try:
                if channel is None:
                    raise PermanentDeliveryError("Channel is no longer configured")
                deliver(channel, row, self.client)
            except Exception as exc:  # each delivery is isolated; one bad endpoint never blocks the queue
                permanent = isinstance(exc, PermanentDeliveryError) or row["attempts"] >= MAX_DELIVERY_ATTEMPTS
                error = f"{type(exc).__name__}: {exc}"
                retry_at = None if permanent else now + timedelta(seconds=backoff_seconds(row["attempts"]))
                self.store.finish_notification(row["id"], False, error, retry_at, now)
                result = "dead" if permanent else "retry"
                counts[result] += 1
                metrics.inc("coldline_notifications_total", channel_type=row["channel_type"], result=result)
                logger.error("Notification delivery failed", extra={"event": "notification_failed", "tenant": row["tenant"],
                             "notification_id": row["id"], "channel": row["channel_id"], "attempt": row["attempts"], "result": result, "error": error})
            else:
                self.store.finish_notification(row["id"], True, now=now)
                counts["delivered"] += 1
                metrics.inc("coldline_notifications_total", channel_type=row["channel_type"], result="delivered")
        self.last_run = time.time()
        return counts

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("Notification worker cycle failed", extra={"event": "worker_error"})
            self.stop_event.wait(self.interval)

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="coldline-notifications", daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)
        self.client.close()

    def healthy(self, max_age=30):
        return self.last_run is not None and time.time() - self.last_run < max(max_age, self.interval * 5)
