"""Demo scenario catalogue: genuine and non-genuine excursion patterns.

Each scenario is derived from the tenant's own rule, so the detector — not the
scenario — decides whether an incident opens. ``expected_incident`` documents the
outcome the unchanged rule should produce; the dashboard shows the observed outcome
side by side, which makes a mismatch visible instead of hidden.
"""
from math import ceil, floor

SAMPLE_SECONDS = 10
NORMAL_C = 4.0


def _normal(count):
    return [round(NORMAL_C + (0.2 if index % 2 else -0.1), 1) for index in range(count)]


def _warm(threshold, count, start, step):
    return [round(threshold + start + step * index, 1) for index in range(count)]


def catalogue(rule, interval=SAMPLE_SECONDS):
    """Return scenario definitions for a rule; ``None`` in steps means no sample (telemetry gap)."""
    sustained = rule["sustained_minutes"] * 60
    gap = rule["max_gap_minutes"] * 60
    recovery = rule["recovery_minutes"] * 60
    threshold = rule["threshold_c"]
    # Normal sample spacing must stay comfortably inside the allowed gap despite scheduling jitter.
    if gap < interval * 1.2:
        return {}
    qualifying = ceil(sustained / interval) + 2
    cooling = ceil(recovery / interval) + 2
    # A warm run spanning at least one interval less than the sustained window, for jitter margin.
    short = max(1, ceil(sustained / interval) - 1)
    missing = floor(gap / interval) + 1
    return {
        "compressor_failure": {
            "label": "Compressor failure",
            "genuine": True,
            "expected_incident": True,
            "description": "Refrigeration unit stops: temperature climbs and stays above the threshold beyond the sustained window, then recovers after repair.",
            "steps": _normal(1) + _warm(threshold, qualifying, 1.2, 0.6) + _normal(cooling),
        },
        "marginal_sustained": {
            "label": "Marginal sustained excursion",
            "genuine": True,
            "expected_incident": True,
            "description": "Only slightly above the threshold, but continuously. Small magnitude does not suppress a sustained, continuous excursion.",
            "steps": _normal(1) + _warm(threshold, qualifying, 0.3, 0.05) + _normal(cooling),
        },
        "door_open_spike": {
            "label": "Door-open spike",
            "genuine": False,
            "expected_incident": False,
            "description": "Loading-door opening: a short warm spike that returns below the threshold before the sustained window elapses.",
            "steps": _normal(1) + _warm(threshold, short, 1.8, 0.8) + _normal(3),
        },
        "sensor_glitch": {
            "label": "Single-sample sensor glitch",
            "genuine": False,
            "expected_incident": False,
            "description": "One implausible reading between normal samples. A single sample cannot prove a sustained excursion.",
            "steps": _normal(1) + [round(threshold + 17, 1)] + _normal(3),
        },
        "telemetry_gap": {
            "label": "Warm readings broken by a telemetry gap",
            "genuine": False,
            "expected_incident": False,
            "description": "Warm readings separated by a gap longer than the allowed maximum. Continuity is unproven, so no incident opens; data quality should be reviewed.",
            "steps": _normal(1) + _warm(threshold, short, 1.0, 0.3) + [None] * missing + _warm(threshold, short, 1.2, 0.3) + _normal(3),
        },
    }


def describe(rule, interval=SAMPLE_SECONDS):
    return [{"id": key, **value, "duration_seconds": len(value["steps"]) * interval}
            for key, value in catalogue(rule, interval).items()]
