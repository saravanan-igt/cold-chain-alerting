"""AI Incident Triage, Forensic Analysis, and Driver Dispatch Script Generator."""
from __future__ import annotations

from typing import Any

from backend.ai.client import invoke_claude

SYSTEM_PROMPT = """You are an Operations Forward Deployed Incident Commander and Cold-Chain Bio-Logistics Specialist.
When a temperature excursion incident occurs in a refrigerated truck carrying sensitive cargo (such as pharmaceuticals or perishable goods), your task is to synthesize the technical evidence into:
1. An Executive Triage Briefing.
2. Degree-Minute Cargo Exposure and Spoilage Prognosis.
3. An Actionable SOP Dispatch Checklist for the operations team.
4. A concise, urgent, professional Driver Dispatch Script (ready to copy and send via SMS/fleet message).

You must respond ONLY with a valid JSON object matching the requested schema. No markdown fences outside the JSON, no commentary."""


def cognitive_fallback_triage(
    incident: dict[str, Any],
    evidence: list[dict[str, Any]],
    rule: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic high-detail cognitive triage generator when Claude API is not called."""
    truck_id = incident.get("truck_id", "Unknown")
    threshold = float(rule.get("threshold_c", 8.0))
    peak_c = float(incident.get("observed_max_c", 0.0))
    warm_secs = float(incident.get("supported_warm_seconds", 0.0))
    warm_mins = round(warm_secs / 60.0, 1)
    lifecycle = incident.get("lifecycle", "open")
    gaps = incident.get("telemetry_gap_count", 0)

    # Calculate degree-minutes above threshold
    degree_minutes = 0.0
    for reading in evidence:
        t = reading.get("temperature_c", 0.0)
        if t > threshold:
            degree_minutes += (t - threshold) * 5.0  # approximate 5-min intervals
    degree_minutes = round(degree_minutes, 1)

    spoilage_status = "CRITICAL" if degree_minutes > 15.0 or peak_c > 12.0 else "ELEVATED" if degree_minutes > 5.0 else "MODERATE"

    return {
        "incident_id": incident.get("id"),
        "truck_id": truck_id,
        "executive_summary": (
            f"Truck {truck_id} suffered a sustained temperature excursion exceeding {threshold}°C for "
            f"{warm_mins} supported minutes (peak: {peak_c:.1f}°C). Cumulative thermal stress is {degree_minutes} °C-minutes. "
            f"Status is currently {lifecycle.upper()}."
        ),
        "thermal_forensics": {
            "excursion_started_at": incident.get("excursion_started_at"),
            "qualified_at": incident.get("qualified_at"),
            "peak_temperature_c": peak_c,
            "supported_warm_minutes": warm_mins,
            "accumulated_degree_minutes": degree_minutes,
            "telemetry_gaps_encountered": gaps,
            "recovery_status": "Confirmed" if incident.get("recovery_confirmed_at") else "Unconfirmed / Active",
        },
        "cargo_impact_assessment": {
            "risk_level": spoilage_status,
            "shelf_life_impact": "Estimated 15-25% reduction in product stability window; quarantine upon arrival recommended.",
            "stability_budget_exceeded": degree_minutes > 10.0,
            "inspection_requirement": "Mandatory visual inspection and certificate of temperature history required for receiver.",
        },
        "sop_action_checklist": [
            "Contact driver immediately via dispatch radio or phone to confirm vehicle location.",
            "Verify reefer diesel tank level and engine unit operation status.",
            "Instruct driver to ensure cargo doors are firmly sealed and latch is undamaged.",
            "Locate nearest cold-storage logistics hub within a 30-minute radius as emergency backup.",
            "Tag load for Quality Assurance thermal quarantine upon arrival at destination dock.",
        ],
        "driver_dispatch_script": (
            f"ALERT NIMBUS OPS TO DRIVER {truck_id}: Cargo temperature exceeded safe limit ({peak_c:.1f}°C recorded, limit is {threshold}°C). "
            f"Please check your refrigeration unit immediately. Ensure reefer engine is running and setpoint is correct. "
            f"Do not open cargo doors. Reply to dispatch with status immediately."
        ),
    }


def generate_incident_triage(
    incident: dict[str, Any],
    evidence: list[dict[str, Any]],
    rule: dict[str, Any],
) -> dict[str, Any]:
    """Generates complete AI forensic triage and driver dispatch script using Claude."""
    truck_id = incident.get("truck_id", "Unknown")
    user_prompt = f"""INCIDENT TRIAGE REQUEST:
Incident Details:
{incident}

Configured Safety Rule:
{rule}

Associated Evidence Readings ({len(evidence)} total):
{evidence}

Please produce a comprehensive incident triage analysis containing:
1. Executive summary of the excursion.
2. Thermal forensics (peak temp, degree-minutes, gap impact).
3. Cargo impact assessment (spoilage risk, stability budget impact).
4. Operations SOP Action Checklist (5 concrete steps).
5. Driver dispatch communication script (urgent, professional message).

Respond with a JSON object strictly having these keys:
{{
  "incident_id": "{incident.get('id')}",
  "truck_id": "{truck_id}",
  "executive_summary": string,
  "thermal_forensics": {{
    "excursion_started_at": string,
    "qualified_at": string,
    "peak_temperature_c": float,
    "supported_warm_minutes": float,
    "accumulated_degree_minutes": float,
    "telemetry_gaps_encountered": integer,
    "recovery_status": string
  }},
  "cargo_impact_assessment": {{
    "risk_level": "CRITICAL" | "ELEVATED" | "MODERATE" | "LOW",
    "shelf_life_impact": string,
    "stability_budget_exceeded": boolean,
    "inspection_requirement": string
  }},
  "sop_action_checklist": [string],
  "driver_dispatch_script": string
}}"""

    fallback = lambda: cognitive_fallback_triage(incident, evidence, rule)
    return invoke_claude(SYSTEM_PROMPT, user_prompt, fallback_fn=fallback)
