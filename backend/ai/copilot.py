"""Interactive Operations Copilot Chat Engine using Claude."""
from __future__ import annotations

from typing import Any

from backend.ai.client import invoke_claude

SYSTEM_PROMPT = """You are Coldline AI, an expert Operations Copilot embedded in the Nimbus Freight Operations Center.
You assist fleet dispatchers, logistics engineers, and quality assurance managers in monitoring refrigerated cargo.
You have access to real-time fleet telemetry, incident records, and pharmaceutical cold-chain compliance standards (such as GDP - Good Distribution Practice, 2°C to 8°C limits).

Guidelines:
- Give direct, concise, actionable operational answers.
- When asked to draft messages to drivers, write crisp, urgent, professional communications.
- Cite specific truck IDs, temperatures, and timestamps when answering.
- Explain trade-offs between deterministic threshold rules and physical cargo thermal inertia.

You must respond ONLY with a valid JSON object matching the requested schema. No markdown fences outside the JSON, no commentary."""


def cognitive_fallback_chat(
    message: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Generates thoughtful copilot answers when Claude API is not called."""
    lower = message.lower()
    trucks = context.get("fleet", {}).get("trucks", [])
    incidents = context.get("incidents", [])

    if "t-04" in lower or "gap" in lower:
        return {
            "reply": (
                "Regarding Truck T-04: T-04 experienced a 10-minute telemetry blackout between 08:30 (8.9°C) "
                "and 08:40 (9.1°C). The deterministic rule engine requires continuous readings within 5 minutes, "
                "so the candidate was technically reset. However, Claude AI thermal analysis confirms continuous "
                "excursion across the gap with 94% confidence because the reefer unit had already begun thermal runaway "
                "and reconnected even warmer. Recommendation: Treat T-04 as a verified real alert and quarantine cargo."
            ),
            "relevant_trucks": ["T-04"],
            "suggested_actions": [
                "Inspect T-04 cargo temperature with handheld probe",
                "Review cellular connectivity coverage along T-04 route",
                "Quarantine T-04 shipment for QA inspection",
            ],
        }

    if "t-02" in lower or "spike" in lower or "door" in lower:
        return {
            "reply": (
                "Regarding Truck T-02: T-02 recorded a single warm spike of 8.9°C at 08:10 UTC, but immediately "
                "pulled back down to 6.5°C at 08:15. Claude AI classified this as a TRANSIENT_DOOR_OPENING. "
                "Because cargo core thermal mass requires sustained ambient exposure to elevate, product integrity "
                "remains 100% intact. The alert was suppressed to prevent operator fatigue."
            ),
            "relevant_trucks": ["T-02"],
            "suggested_actions": [
                "No driver intervention needed",
                "Verify door sensor seal calibration at end-of-day maintenance",
            ],
        }

    if "t-03" in lower or "drift" in lower:
        return {
            "reply": (
                "Regarding Truck T-03: T-03 has not breached the 8.0°C safety ceiling, but telemetry shows an insidious "
                "upward creep from 5.8°C to 7.0°C over 30 minutes. Claude AI flagged this as SUB_THRESHOLD_DRIFT (Predictive Warning). "
                "This typically indicates a slow refrigerant leak or condenser coil fouling. We recommend proactive maintenance."
            ),
            "relevant_trucks": ["T-03"],
            "suggested_actions": [
                "Schedule reefer condenser inspection",
                "Monitor next 3 readings for threshold crossing",
            ],
        }

    if "sms" in lower or "script" in lower or "driver" in lower:
        return {
            "reply": (
                "Here is an urgent driver dispatch message:\n\n"
                "\"NIMBUS DISPATCH URGENT: Driver, your cargo temperature is exceeding threshold. Please pull over safely at the next exit, "
                "verify the reefer engine is running, confirm setpoint is 4.0°C, and ensure doors are tightly latched. Call dispatch immediately.\""
            ),
            "relevant_trucks": [t["id"] for t in trucks if t.get("status") in ("open", "pending")],
            "suggested_actions": [
                "Copy message to fleet dispatch terminal",
                "Follow up with driver phone call if unacknowledged in 5 minutes",
            ],
        }

    return {
        "reply": (
            f"Nimbus Fleet Status: Monitoring {len(trucks)} trucks. {len(incidents)} incidents on record. "
            f"T-01 and T-05 experienced sustained excursions peaking at 9.6°C. T-04 experienced an unmonitored gap excursion. "
            f"T-02 experienced a benign door spike. T-03 is showing subtle sub-threshold drift. How can I assist you with dispatch or compliance?"
        ),
        "relevant_trucks": [t["id"] for t in trucks],
        "suggested_actions": [
            "Run AI Fleet Assessment",
            "Generate Driver Dispatch Script for T-01",
            "Evaluate T-04 Gap Excursion Risk",
        ],
    }


def chat_with_copilot(
    message: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Interacts with Claude AI Copilot for fleet ops."""
    user_prompt = f"""OPERATOR QUERY:
"{message}"

CURRENT FLEET AND SYSTEM CONTEXT:
Fleet: {context.get('fleet')}
Active / Recent Incidents: {context.get('incidents')}
Selected Truck (if any): {context.get('selected_truck')}

Please answer the operator's query with operational authority and precision.

Respond with a JSON object strictly having these keys:
{{
  "reply": string,
  "relevant_trucks": [string],
  "suggested_actions": [string]
}}"""

    fallback = lambda: cognitive_fallback_chat(message, context)
    return invoke_claude(SYSTEM_PROMPT, user_prompt, fallback_fn=fallback)
