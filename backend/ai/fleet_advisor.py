"""AI Fleet Holistic Risk Advisory and Predictive Anomaly Scanner using Claude."""
from __future__ import annotations

from typing import Any

from backend.ai.client import invoke_claude
from backend.ai.detector import evaluate_real_alert

SYSTEM_PROMPT = """You are a Fleet Operations Chief Engineer and Forward Deployed AI Architect for refrigerated supply chains.
You are evaluating the entire fleet of refrigerated trucks for Nimbus Freight.
Your goal is to synthesize multi-truck telemetry and detect:
1. Fleet-wide operational health score (0-100).
2. Trucks in active critical excursion vs trucks with predictive drift vs normal.
3. Hidden risks (connectivity blackouts with high heat).
4. Strategic dispatcher action plan.

You must respond ONLY with a valid JSON object matching the requested schema. No markdown fences outside the JSON, no commentary."""


def cognitive_fallback_fleet_assessment(
    fleet: dict[str, Any],
    readings_by_truck: dict[str, list[dict[str, Any]]],
    rules_by_truck: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Generates holistic fleet assessment using deterministic cognitive heuristics."""
    truck_assessments = []
    critical_count = 0
    warning_count = 0
    normal_count = 0

    for truck in fleet.get("trucks", []):
        tid = truck["id"]
        truck_readings = readings_by_truck.get(tid, [])
        truck_rule = rules_by_truck.get(tid, truck.get("rule", {"threshold_c": 8.0}))
        eval_result = evaluate_real_alert(tid, truck_readings, truck_rule)

        category = eval_result["alert_category"]
        severity = eval_result["severity"]
        if severity == "CRITICAL":
            critical_count += 1
        elif severity in ("HIGH", "WARNING"):
            warning_count += 1
        else:
            normal_count += 1

        truck_assessments.append({
            "truck_id": tid,
            "status": truck["status"],
            "temperature_c": truck["temperature_c"],
            "ai_severity": severity,
            "ai_category": category,
            "is_real_alert": eval_result["is_real_alert"],
            "confidence_score": eval_result["confidence_score"],
            "summary": eval_result["one_line_summary"],
            "recommended_action": eval_result["recommended_sop_action"],
        })

    total = len(truck_assessments)
    health_score = max(0, int(100 - (critical_count * 30 + warning_count * 15)))

    overall_condition = "CRITICAL_ATTENTION_NEEDED" if critical_count > 0 else "ELEVATED_WATCH" if warning_count > 0 else "OPTIMAL"

    return {
        "tenant": fleet.get("tenant", "nimbus"),
        "fleet_health_score": health_score,
        "overall_condition": overall_condition,
        "active_critical_alerts": critical_count,
        "predictive_warnings": warning_count,
        "normal_operating_trucks": normal_count,
        "executive_dispatch_summary": (
            f"Fleet health score is {health_score}/100 with {critical_count} active critical thermal alerts and "
            f"{warning_count} predictive drift warnings across {total} monitored trucks. Immediate dispatcher attention "
            f"is required for affected vehicles."
        ),
        "key_action_items": [
            "Prioritize radio contact with critical trucks to verify reefer engine status.",
            "Schedule maintenance inspection for trucks showing sub-threshold thermal drift.",
            "Check cellular coverage maps along routes experiencing telemetry blackouts.",
        ],
        "truck_assessments": truck_assessments,
    }


def assess_fleet_with_ai(
    fleet: dict[str, Any],
    readings_by_truck: dict[str, list[dict[str, Any]]],
    rules_by_truck: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Runs a whole-fleet AI risk assessment across all vehicles using Claude."""
    user_prompt = f"""FLEET HEALTH SCAN REQUEST:
Fleet Overview:
{fleet}

Truck Telemetry Samples:
{readings_by_truck}

Truck Rules:
{rules_by_truck}

Please evaluate the entire fleet and provide:
1. Fleet health score (0 to 100).
2. Overall condition: 'OPTIMAL' | 'ELEVATED_WATCH' | 'CRITICAL_ATTENTION_NEEDED'.
3. Counts of critical, warning, and nominal trucks.
4. Executive dispatch summary.
5. Key action items for the dispatch team.
6. Individual truck assessments.

Respond with a JSON object strictly having these keys:
{{
  "tenant": "{fleet.get('tenant', 'nimbus')}",
  "fleet_health_score": integer,
  "overall_condition": "OPTIMAL" | "ELEVATED_WATCH" | "CRITICAL_ATTENTION_NEEDED",
  "active_critical_alerts": integer,
  "predictive_warnings": integer,
  "normal_operating_trucks": integer,
  "executive_dispatch_summary": string,
  "key_action_items": [string],
  "truck_assessments": [
    {{
      "truck_id": string,
      "status": string,
      "temperature_c": float or null,
      "ai_severity": "CRITICAL" | "HIGH" | "WARNING" | "BENIGN" | "LOW",
      "ai_category": string,
      "is_real_alert": boolean,
      "confidence_score": float,
      "summary": string,
      "recommended_action": string
    }}
  ]
}}"""

    fallback = lambda: cognitive_fallback_fleet_assessment(fleet, readings_by_truck, rules_by_truck)
    return invoke_claude(SYSTEM_PROMPT, user_prompt, fallback_fn=fallback)
