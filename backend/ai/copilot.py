"""A tenant-scoped deterministic operations assistant; no external model is called."""
from typing import Any


def cognitive_fallback_chat(message: str, context: dict[str, Any]) -> dict[str, Any]:
    fleet = context.get("fleet", {})
    trucks = fleet.get("trucks", [])
    incidents = context.get("incidents", [])
    lowered = message.lower()
    truck = next(
        (item for item in trucks if item["id"] == context.get("selected_truck")),
        None,
    )
    if truck is None:
        truck = next((item for item in trucks if item["id"].lower() in lowered), None)

    if truck:
        timestamp = truck.get("last_observation_at")
        temperature = truck.get("temperature_c")
        reading = (
            f"The last accepted reading was {temperature} °C at {timestamp}."
            if temperature is not None and timestamp
            else "No accepted reading is available."
        )
        reply = (
            f"Truck {truck['id']} is {truck.get('status', 'unknown')} with "
            f"{truck.get('freshness', 'unknown')} telemetry. {reading} "
            "The detector reports rule state only; it does not determine equipment cause or cargo disposition."
        )
        incident = context.get("selected_incident")
        if incident:
            reply += (
                f" Selected incident {incident['id']} is {incident['lifecycle']}, "
                f"qualified at {incident['qualified_at']}."
            )
        suggestions = [
            "Check the customer's approved operating procedure.",
            "Verify sensor connectivity and refrigeration-unit status with dispatch.",
        ]
        if any(term in lowered for term in ("sms", "script", "driver", "message")):
            threshold = truck.get("rule", {}).get("threshold_c")
            detail = f"configured threshold {threshold} °C" if threshold is not None else "configured temperature rule"
            reply += (
                f"\n\nDISPATCH MESSAGE: Please acknowledge the alert for truck {truck['id']}, "
                f"check the unit and sensor, and follow the approved procedure ({detail}). "
                "Cargo disposition must be decided by the customer's quality team."
            )
    else:
        open_count = sum(item.get("status") == "open" for item in trucks)
        pending_count = sum(item.get("status") == "pending" for item in trucks)
        reply = (
            f"Fleet {fleet.get('name', fleet.get('tenant', ''))}: {len(trucks)} registered trucks, "
            f"{open_count} open detector incidents, and {pending_count} pending candidates. "
            f"{len(incidents)} recent incidents are available. I can summarize recorded readings, "
            "but cannot infer equipment failure or cargo safety."
        )
        suggestions = ["Review open incidents.", "Check telemetry freshness."]
        if any(term in lowered for term in ("sms", "script", "driver", "message")):
            reply += (
                "\n\nDISPATCH MESSAGE: Please confirm the current truck and observation, "
                "then follow the customer's approved operating procedure. Cargo disposition "
                "must be decided by the customer's quality team."
            )

    return {
        "reply": reply,
        "relevant_trucks": [truck["id"]] if truck else [],
        "suggested_actions": suggestions,
    }


def chat_with_copilot(message: str, context: dict[str, Any]) -> dict[str, Any]:
    return cognitive_fallback_chat(message, context)
