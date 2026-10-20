"""Evidence-only incident summaries; cargo impact remains a customer quality decision."""
from typing import Any


def cognitive_fallback_triage(
    incident: dict[str, Any],
    evidence: list[dict[str, Any]],
    rule: dict[str, Any],
) -> dict[str, Any]:
    truck_id = incident["truck_id"]
    threshold = float(rule["threshold_c"])
    peak = float(incident["observed_max_c"])
    supported_minutes = round(float(incident["supported_warm_seconds"]) / 60, 1)
    lifecycle = incident["lifecycle"]
    return {
        "incident_id": incident["id"],
        "truck_id": truck_id,
        "executive_summary": (
            f"Truck {truck_id} met the configured temperature rule (> {threshold:g} °C). "
            f"The recorded peak is {peak:.1f} °C across {len(evidence)} evidence readings; "
            f"lifecycle is {lifecycle}."
        ),
        "thermal_forensics": {
            "excursion_started_at": incident["excursion_started_at"],
            "qualified_at": incident["qualified_at"],
            "peak_temperature_c": peak,
            "supported_warm_minutes": supported_minutes,
            "accumulated_degree_minutes": None,
            "telemetry_gaps_encountered": int(incident["telemetry_gap_count"]),
            "recovery_status": "Confirmed" if incident.get("recovery_confirmed_at") else "Unconfirmed",
        },
        "cargo_impact_assessment": {
            "risk_level": "NOT_ASSESSED",
            "shelf_life_impact": "Not assessed; cargo-specific stability data is not configured.",
            "stability_budget_exceeded": None,
            "inspection_requirement": "Refer to the customer's approved quality procedure.",
        },
        "sop_action_checklist": [
            "Confirm the latest sensor reading and telemetry freshness with dispatch.",
            "Check the refrigeration unit and cargo handling conditions using the approved procedure.",
            "Refer cargo disposition to the customer's qualified quality team.",
        ],
        "driver_dispatch_script": (
            f"Dispatch to {truck_id}: the latest recorded temperature excursion met the configured "
            f"alarm rule (> {threshold:g} °C; observed peak {peak:.1f} °C). Please acknowledge and "
            "follow the approved operating procedure. Cargo disposition is not determined by this alert."
        ),
    }


def generate_incident_triage(
    incident: dict[str, Any],
    evidence: list[dict[str, Any]],
    rule: dict[str, Any],
) -> dict[str, Any]:
    return cognitive_fallback_triage(incident, evidence, rule)
