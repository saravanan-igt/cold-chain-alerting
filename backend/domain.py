"""Pure event-time state machine. No clocks, database or transport dependencies."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    threshold_c: float = Field(default=8, allow_inf_nan=False, ge=-100, le=100)
    sustained_minutes: float = Field(default=10, gt=0, le=1440, allow_inf_nan=False)
    max_gap_minutes: float = Field(default=5, gt=0, le=1440, allow_inf_nan=False)
    recovery_minutes: float = Field(default=5, gt=0, le=1440, allow_inf_nan=False)

    def snapshot(self):
        return {**self.model_dump(), "version": sha256(self.model_dump_json().encode()).hexdigest()[:12]}


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    truck_id: str = Field(min_length=1, max_length=80)
    device_id: str = Field(min_length=1, max_length=80)
    timestamp: datetime
    temperature_c: float = Field(allow_inf_nan=False)
    humidity_pct: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    unit: Literal["C"] = "C"
    event_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("timestamp", mode="before")
    @classmethod
    def iso_only(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("timestamp must be an ISO-8601 string with timezone")
        return value

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp requires a timezone offset")
        return value.astimezone(timezone.utc)

    def canonical(self):
        return {**self.model_dump(mode="json"), "timestamp": utc(self.timestamp)}


def advance(previous: dict, reading: Reading, configured_rule: Rule, tenant: str, processed_at: str):
    """Return (new state, changed incident, did_open). Caller enforces ordering."""
    state = deepcopy(previous)
    now, temp = utc(reading.timestamp), reading.temperature_c
    active, candidate = state.get("active"), state.get("candidate")
    rule = (active or candidate or {}).get("rule", configured_rule.snapshot())
    gap = seconds(state["last_at"], now) if state.get("last_at") else 0
    continuous = gap <= rule["max_gap_minutes"] * 60
    warm = temp > rule["threshold_c"]
    changed, opened = None, False
    if active:
        active["last_observation_at"] = now
        active["evidence_count"] += 1
        active["observed_max_c"] = max(active["observed_max_c"], temp)
        if not continuous:
            active["telemetry_gap_count"] += 1
        if warm and state.get("last_warm") and continuous:
            active["supported_warm_seconds"] += gap
        if warm or not continuous:
            active["recovery_started_at"] = None
        if not warm:
            active["recovery_started_at"] = active["recovery_started_at"] or now
            if seconds(active["recovery_started_at"], now) >= rule["recovery_minutes"] * 60:
                active["lifecycle"] = "recovered"
                active["recovery_confirmed_at"] = now
                state["active"] = None
        changed = active
    else:
        if not continuous or not warm:
            candidate = None
        # A new candidate takes the current configuration; existing ones retain their snapshot.
        if candidate is None:
            rule = configured_rule.snapshot()
            warm = temp > rule["threshold_c"]
        if warm:
            if candidate is None:
                candidate = {"start": now, "rule": rule, "count": 0, "max": temp}
            candidate["count"] += 1
            candidate["max"] = max(candidate["max"], temp)
            supported = seconds(candidate["start"], now)
            if supported >= rule["sustained_minutes"] * 60:
                incident_id = str(uuid5(NAMESPACE_URL, f"{tenant}/{reading.truck_id}/{candidate['start']}/{rule['version']}"))
                changed = {
                    "id": incident_id, "truck_id": reading.truck_id, "rule": rule,
                    "excursion_started_at": candidate["start"], "qualified_at": now,
                    "opened_processed_at": processed_at, "lifecycle": "open",
                    "recovery_started_at": None, "recovery_confirmed_at": None,
                    "last_observation_at": now, "evidence_count": candidate["count"],
                    "opening_evidence_count": candidate["count"], "observed_max_c": candidate["max"],
                    "qualifying_supported_seconds": supported, "supported_warm_seconds": supported,
                    "telemetry_gap_count": 0,
                    "explanation": f"Truck {reading.truck_id} had {candidate['count']} consecutive readings above {rule['threshold_c']:g} C from {candidate['start']} to {now}, with no gap exceeding {rule['max_gap_minutes']:g} minutes. The qualifying reading met the {rule['sustained_minutes']:g}-minute rule; one incident opened.",
                }
                state["active"], candidate, opened = changed, None, True
        state["candidate"] = candidate
    state.update(last_at=now, last_temperature_c=temp, last_warm=warm)
    return state, changed, opened
