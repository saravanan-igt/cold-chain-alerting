"""Deterministic summaries of rule outcomes and recorded temperature observations."""
from datetime import datetime
from typing import Any


def _ordered(readings: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    values = []
    for row in readings:
        timestamp = datetime.fromisoformat(row["timestamp"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Reading timestamps must include a timezone")
        temperature = float(row["temperature_c"])
        values.append((timestamp, temperature))
    return sorted(values, key=lambda value: value[0])


def calculate_thermal_metrics(
    readings: list[dict[str, Any]],
    threshold_c: float,
    max_gap_minutes: float = 5,
) -> dict[str, Any]:
    """Compute descriptive telemetry facts; no between-sample interpolation is used."""
    ordered = _ordered(readings)
    temperatures = [temperature for _, temperature in ordered]
    gaps = []
    max_gap_seconds = 0
    max_slope = 0.0
    above_count = 0
    max_consecutive = 0
    consecutive = 0
    previous = None

    for point in ordered:
        timestamp, temperature = point
        if previous and (timestamp - previous[0]).total_seconds() > max_gap_minutes * 60:
            consecutive = 0
        is_warm = temperature > threshold_c
        above_count += int(is_warm)
        if is_warm:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0

        if previous:
            previous_at, previous_temperature = previous
            interval = (timestamp - previous_at).total_seconds()
            max_gap_seconds = max(max_gap_seconds, int(interval))
            if interval > max_gap_minutes * 60:
                gaps.append({
                    "from": previous_at.isoformat(),
                    "to": timestamp.isoformat(),
                    "duration_minutes": round(interval / 60, 1),
                    "temp_before": previous_temperature,
                    "temp_after": temperature,
                })
            if interval > 0:
                max_slope = max(max_slope, abs(temperature - previous_temperature) / (interval / 60))
        previous = point

    return {
        "count": len(ordered),
        "min_c": min(temperatures) if temperatures else None,
        "max_c": max(temperatures) if temperatures else None,
        "mean_c": sum(temperatures) / len(temperatures) if temperatures else None,
        "max_slope_c_per_min": max_slope,
        "readings_above_threshold": above_count,
        "consecutive_above_max": max_consecutive,
        "max_gap_seconds": max_gap_seconds,
        "gaps": gaps,
    }


def cognitive_fallback_detection(
    truck_id: str,
    readings: list[dict[str, Any]],
    rule: dict[str, Any],
    metrics: dict[str, Any],
    incident: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe only rule outcomes and telemetry facts; never infer cargo or equipment state."""
    threshold = float(rule.get("threshold_c", 8.0))
    sustained_seconds = float(rule.get("sustained_minutes", 10)) * 60
    max_gap_seconds = float(rule.get("max_gap_minutes", 5)) * 60
    ordered = _ordered(readings)
    qualified = incident is not None
    warm_start = None
    previous = None

    for timestamp, temperature in ordered:
        warm = temperature > threshold
        gap = (timestamp - previous[0]).total_seconds() if previous else 0
        if warm:
            if previous and previous[1] > threshold and gap <= max_gap_seconds:
                warm_start = warm_start or previous[0]
            else:
                warm_start = timestamp
            if (timestamp - warm_start).total_seconds() >= sustained_seconds:
                qualified = True
        else:
            warm_start = None
        previous = (timestamp, temperature)

    unconfirmed_gap = any(
        left[1] > threshold
        and right[1] > threshold
        and (right[0] - left[0]).total_seconds() > max_gap_seconds
        for left, right in zip(ordered, ordered[1:])
    )
    category = (
        "QUALIFIED_EXCURSION" if qualified
        else "UNCONFIRMED_TELEMETRY_GAP" if unconfirmed_gap
        else "NO_QUALIFIED_EXCURSION"
    )
    peak = metrics["max_c"]
    summary = (
        f"Truck {truck_id} has a qualified temperature excursion under the configured rule."
        if qualified else
        f"Truck {truck_id} has warm observations separated by a gap; continuity is not assumed."
        if unconfirmed_gap else
        f"Truck {truck_id} has no qualified excursion in the evaluated observations."
    )
    return {
        "truck_id": truck_id,
        "is_real_alert": qualified,
        "alert_category": category,
        "severity": "WARNING" if qualified or unconfirmed_gap else "LOW",
        "confidence_score": None,
        "root_cause_hypothesis": "Equipment cause is not determined from temperature readings.",
        "thermal_inertia_analysis": "Cargo-core temperature is not measured by this telemetry.",
        "cargo_spoilage_risk": "NOT_ASSESSED",
        "suppressed_as_benign": False,
        "suppress_reason": None,
        "recommended_sop_action": "Use the customer's approved operational and quality procedures.",
        "one_line_summary": summary,
        "observed_peak_c": peak,
        "configured_threshold_c": threshold,
        "telemetry_metrics": metrics,
    }


def evaluate_real_alert(
    truck_id: str,
    readings: list[dict[str, Any]],
    rule: dict[str, Any],
    incident: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate observations deterministically; external model output never changes alert state."""
    threshold = float(rule.get("threshold_c", 8.0))
    metrics = calculate_thermal_metrics(
        readings, threshold, float(rule.get("max_gap_minutes", 5))
    )
    return cognitive_fallback_detection(truck_id, readings, rule, metrics, incident)
