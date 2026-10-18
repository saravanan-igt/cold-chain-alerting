from datetime import datetime, timedelta, timezone

import pytest

from backend.domain import Reading, Rule, advance, utc

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def sample(minute, temperature=9, **kw):
    return Reading(truck_id="T-01", device_id="sensor-T-01", timestamp=BASE + timedelta(minutes=minute), temperature_c=temperature, **kw)


def run(points, rule=Rule()):
    state, opened, changes = {}, [], []
    for minute, temp in points:
        state, changed, did_open = advance(state, sample(minute, temp), rule, "nimbus", utc(BASE))
        if did_open:
            opened.append(changed)
        if changed:
            changes.append(changed)
    return state, opened, changes


@pytest.mark.parametrize("points", [
    [(0, 6), (5, 7), (10, 8)], [(0, 9), (5, 9), (10, 8)],
    [(0, 9), (5, 8), (10, 9), (15, 9)], [(0, 9), (6, 9), (11, 9)],
])
def test_no_false_open(points):
    assert run(points)[1] == []


def test_exact_boundaries_and_single_open():
    state, opened, changes = run([(0, 9), (5, 10), (10, 11), (15, 9)])
    assert len(opened) == 1
    assert opened[0]["qualified_at"] == utc(BASE + timedelta(minutes=10))
    assert changes[-1]["supported_warm_seconds"] == 900
    assert state["active"]["evidence_count"] == 4


def test_recovery_and_reopen():
    state, opened, changes = run([(0, 9), (5, 9), (10, 9), (15, 8), (20, 9), (25, 8), (30, 8), (35, 9), (40, 9), (45, 9)])
    assert len(opened) == 2
    assert changes[-2]["lifecycle"] == "recovered"
    assert state["active"]["excursion_started_at"] == utc(BASE + timedelta(minutes=35))


def test_gap_does_not_close_or_realert():
    state, opened, changes = run([(0, 9), (5, 9), (10, 9), (15, 7), (30, 7), (35, 9)])
    assert len(opened) == 1
    assert state["active"]["lifecycle"] == "open"
    assert state["active"]["telemetry_gap_count"] == 1
    assert state["active"]["supported_warm_seconds"] == 600


def test_rule_snapshot_persists_until_candidate_finishes():
    state, _, _ = advance({}, sample(0), Rule(), "nimbus", utc(BASE))
    state, _, _ = advance(state, sample(5), Rule(threshold_c=20), "nimbus", utc(BASE))
    state, incident, opened = advance(state, sample(10), Rule(threshold_c=20), "nimbus", utc(BASE))
    assert opened and incident["rule"]["threshold_c"] == 8


@pytest.mark.parametrize("field,value", [("timestamp", "2026-01-01T00:00:00"), ("temperature_c", float("nan")), ("temperature_c", float("inf")), ("unit", "F"), ("timestamp", 123)])
def test_invalid(field, value):
    raw = sample(0).canonical()
    raw[field] = value
    with pytest.raises(ValueError):
        Reading.model_validate(raw)
