"""Tenant-scoped fleet status summary derived from detector and telemetry freshness."""
from typing import Any


def cognitive_fallback_fleet_assessment(
    fleet: dict[str, Any],
    readings_by_truck: dict[str, list[dict[str, Any]]],
    rules_by_truck: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    assessments = []
    open_count = pending_count = fresh_count = attention_count = 0

    for truck in fleet.get("trucks", []):
        truck_id = truck["id"]
        status = truck["status"]
        freshness = truck["freshness"]
        open_count += int(status == "open")
        pending_count += int(status == "pending")
        fresh_count += int(freshness == "fresh" and status not in ("open", "pending"))
        attention_count += int(freshness in ("stale", "never_seen", "future"))

        category = {
            "open": "OPEN_INCIDENT",
            "pending": "PENDING_CANDIDATE",
            "unknown": "NO_TELEMETRY",
            "normal": "NO_OPEN_INCIDENT",
        }.get(status, "UNKNOWN")
        if freshness != "fresh" and status != "unknown":
            category = "TELEMETRY_" + freshness.upper()
        summary = (
            f"Last observation: {truck['temperature_c']} °C at {truck['last_observation_at']}."
            if truck["temperature_c"] is not None
            else "No accepted observation is available."
        )
        assessments.append({
            "truck_id": truck_id,
            "status": status,
            "temperature_c": truck["temperature_c"],
            "ai_severity": "WARNING" if status in ("open", "pending") or freshness != "fresh" else "LOW",
            "ai_category": category,
            "is_real_alert": status == "open",
            "confidence_score": None,
            "summary": summary,
            "recommended_action": "Review the configured rule and the customer's approved operating procedure.",
        })

    condition = (
        "ACTIVE_INCIDENTS" if open_count
        else "DATA_QUALITY_REVIEW" if pending_count or attention_count
        else "NO_OPEN_INCIDENTS"
    )
    return {
        "tenant": fleet.get("tenant"),
        "fleet_health_score": None,
        "overall_condition": condition,
        "active_critical_alerts": open_count,
        "predictive_warnings": pending_count + attention_count,
        "normal_operating_trucks": fresh_count,
        "executive_dispatch_summary": (
            f"{open_count} open incidents, {pending_count} pending candidates, and "
            f"{attention_count} trucks with stale, missing, or future telemetry across "
            f"{len(assessments)} registered trucks. No cargo-risk score is calculated."
        ),
        "key_action_items": [
            "Review open incidents using the customer's approved operating procedure.",
            "Check connectivity and sensor status for trucks with stale or missing telemetry.",
        ],
        "truck_assessments": assessments,
    }


def assess_fleet_with_ai(
    fleet: dict[str, Any],
    readings_by_truck: dict[str, list[dict[str, Any]]],
    rules_by_truck: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return cognitive_fallback_fleet_assessment(fleet, readings_by_truck, rules_by_truck)
