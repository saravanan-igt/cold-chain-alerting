"""Dependency-free observability: structured logs, request correlation and Prometheus text metrics.

Counters are per process. Scrape every replica; aggregate in Prometheus. Labels never
include tenant, truck or user identifiers, to keep cardinality bounded and avoid
leaking customer data into shared monitoring.
"""
import json
import logging
import os
import sys
import threading
import time
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger("coldline")

_HELP = {
    "coldline_http_requests_total": ("counter", "HTTP requests by method, route template and status"),
    "coldline_http_request_duration_seconds": ("summary", "HTTP request latency by method and route template"),
    "coldline_readings_total": ("counter", "Ingested readings by outcome"),
    "coldline_incidents_total": ("counter", "Incident lifecycle transitions"),
    "coldline_notifications_total": ("counter", "Notification delivery attempts by channel type and result"),
    "coldline_escalations_total": ("counter", "Escalations raised for unacknowledged incidents"),
    "coldline_acknowledgements_total": ("counter", "Incident acknowledgements"),
}


class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.values = {}

    @staticmethod
    def _key(name, labels):
        return name, tuple(sorted(labels.items()))

    def inc(self, name, value=1.0, **labels):
        with self.lock:
            key = self._key(name, labels)
            self.values[key] = self.values.get(key, 0.0) + value

    def observe(self, name, seconds, **labels):
        self.inc(name + "_sum", seconds, **labels)
        self.inc(name + "_count", 1, **labels)

    def get(self, name, **labels):
        with self.lock:
            return self.values.get(self._key(name, labels), 0.0)

    def render(self, gauges=None):
        def escape(value):
            return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        def fmt(name, labels, value):
            label_text = ",".join(f'{k}="{escape(v)}"' for k, v in labels)
            return f"{name}{{{label_text}}} {value:g}" if label_text else f"{name} {value:g}"

        with self.lock:
            items = sorted(self.values.items())
        lines, declared = [], set()
        for (name, labels), value in items:
            family = name.removesuffix("_sum").removesuffix("_count") if name not in _HELP else name
            if family not in declared and family in _HELP:
                kind, text = _HELP[family]
                lines += [f"# HELP {family} {text}", f"# TYPE {family} {kind}"]
                declared.add(family)
            lines.append(fmt(name, labels, value))
        for name, (text, value) in (gauges or {}).items():
            lines += [f"# HELP {name} {text}", f"# TYPE {name} gauge", fmt(name, (), value)]
        return "\n".join(lines) + "\n"


metrics = Metrics()


class JsonFormatter(logging.Formatter):
    FIELDS = ("event", "method", "route", "status", "duration_ms", "tenant", "incident_id", "channel",
              "notification_id", "attempt", "result", "error", "level_index", "scenario", "truck_id")

    def format(self, record):
        entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
                 "level": record.levelname, "logger": record.name, "message": record.getMessage()}
        request_id = request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        for field in self.FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging():
    if getattr(logger, "_coldline_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("COLDCHAIN_LOG_FORMAT", "text").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("COLDCHAIN_LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    logger._coldline_configured = True
