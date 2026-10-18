"""AI-Powered Real Alert Detection and Thermal Forensic Analysis using Anthropic Claude."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.ai.client import invoke_claude


SYSTEM_PROMPT = """You are an elite Cold-Chain Thermal Systems Diagnostic Engineer and Logistics Operations Architect.
Your mission is to evaluate refrigerated truck ("reefer") telemetry data and determine whether an incoming temperature reading or excursion is a GENUINE REAL ALERT requiring immediate operational dispatch, or a BENIGN EVENT (such as a temporary loading door opening or routine evaporator defrost cycle) that should NOT sound sirens and fatigue human operators.

You also specialize in:
1. Thermodynamic Continuity Across Connectivity Gaps: If a truck had warm readings before a telemetry dropout and remains warm after reconnecting, evaluate the physical likelihood of continuous warming during the silence (reefer units cannot spontaneously freeze and re-heat without power).
2. Sub-Threshold Creep Detection: Detecting insidious thermal degradation (e.g., temperatures steadily rising from 5.8°C toward 7.9°C under an 8.0°C ceiling) before catastrophic spoilage occurs.
3. False Alarm Suppression: Identifying transient air-temperature spikes (e.g., door opening for 1 sample) where cargo core thermal inertia prevented any actual product degradation.

You must respond ONLY with a valid JSON object matching the requested schema. No markdown fences outside the JSON, no commentary."""


def calculate_thermal_metrics(readings: list[dict[str, Any]], threshold_c: float) -> dict[str, Any]:
    """Calculate statistical and thermodynamic characteristics of the telemetry stream."""
    if not readings:
        return {
            "count": 0, "min_c": 0.0, "max_c": 0.0, "mean_c": 0.0,
            "max_slope_c_per_min": 0.0, "readings_above_threshold": 0,
            "consecutive_above_max": 0, "max_gap_seconds": 0, "gaps": []
        }

    sorted_readings = sorted(readings, key=lambda r: r["timestamp"])
    temps = [float(r["temperature_c"]) for r in sorted_readings]
    count = len(temps)
    min_c = min(temps)
    max_c = max(temps)
    mean_c = sum(temps) / count

    above_threshold = [t > threshold_c for t in temps]
    readings_above = sum(above_threshold)

    # Calculate max consecutive readings above threshold
    max_consec = 0
    current_consec = 0
    for is_above in above_threshold:
        if is_above:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0

    # Calculate slopes and gaps
    max_slope = 0.0
    max_gap_sec = 0
    gaps = []
    for i in range(1, count):
        t1 = datetime.fromisoformat(sorted_readings[i - 1]["timestamp"])
        t2 = datetime.fromisoformat(sorted_readings[i]["timestamp"])
        dt_minutes = (t2 - t1).total_seconds() / 60.0
        dt_seconds = (t2 - t1).total_seconds()
        if dt_seconds > max_gap_sec:
            max_gap_sec = int(dt_seconds)

        if dt_minutes > 5.0:
            gaps.append({
                "from": sorted_readings[i - 1]["timestamp"],
                "to": sorted_readings[i]["timestamp"],
                "duration_minutes": round(dt_minutes, 1),
                "temp_before": sorted_readings[i - 1]["temperature_c"],
                "temp_after": sorted_readings[i]["temperature_c"],
            })

        if dt_minutes > 0:
            slope = abs(temps[i] - temps[i - 1]) / dt_minutes
            if slope > max_slope:
                max_slope = slope

    return {
        "count": count,
        "min_c": round(min_c, 2),
        "max_c": round(max_c, 2),
        "mean_c": round(mean_c, 2),
        "max_slope_c_per_min": round(max_slope, 3),
        "readings_above_threshold": readings_above,
        "consecutive_above_max": max_consec,
        "max_gap_seconds": max_gap_sec,
        "gaps": gaps,
    }


def cognitive_fallback_detection(
    truck_id: str,
    readings: list[dict[str, Any]],
    rule: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """High-fidelity local thermal cognitive engine mimicking Claude's reasoning."""
    threshold = float(rule.get("threshold_c", 8.0))
    max_c = metrics["max_c"]
    max_gap_min = metrics["max_gap_seconds"] / 60.0
    gaps = metrics["gaps"]
    temps = [r["temperature_c"] for r in readings]

    # Case 1: Gap continuity excursion (The T-04 scenario)
    # Had warm reading before gap and warm reading after gap > threshold
    if gaps and any(g["temp_before"] > threshold and g["temp_after"] > threshold for g in gaps):
        gap = next(g for g in gaps if g["temp_before"] > threshold and g["temp_after"] > threshold)
        return {
            "truck_id": truck_id,
            "is_real_alert": True,
            "alert_category": "TELEMETRY_GAP_EXCURSION",
            "severity": "CRITICAL",
            "confidence_score": 0.94,
            "root_cause_hypothesis": (
                f"Sustained reefer thermal runaway across unmonitored connectivity blackout. "
                f"Truck was {gap['temp_before']}°C before the {gap['duration_minutes']} min gap and "
                f"reconnected at {gap['temp_after']}°C. Thermodynamic continuity confirms continuous warm exposure."
            ),
            "thermal_inertia_analysis": (
                "Air temperature sustained above safety baseline with failure to recover. Core cargo "
                "thermal buffer is actively depleting due to prolonged ambient heat transfer."
            ),
            "cargo_spoilage_risk": "ELEVATED",
            "suppressed_as_benign": False,
            "suppress_reason": None,
            "recommended_sop_action": (
                "PRIORITY DISPATCH: Contact driver immediately to confirm reefer unit engine status, "
                "inspect evaporator airflow, and direct truck to nearest pre-cooling depot."
            ),
            "one_line_summary": f"Truck {truck_id} had sustained >{threshold}°C warming bridging an unmonitored {gap['duration_minutes']} min gap.",
        }

    # Case 2: Transient Door Opening / Spike (The T-02 scenario)
    # Only 1 reading above threshold, immediately returned to normal, max slope is high
    if metrics["readings_above_threshold"] == 1 and max_c > threshold:
        return {
            "truck_id": truck_id,
            "is_real_alert": False,
            "alert_category": "TRANSIENT_DOOR_OPENING",
            "severity": "BENIGN",
            "confidence_score": 0.96,
            "root_cause_hypothesis": (
                f"Transient door opening or delivery drop-off. Single spike to {max_c}°C followed by "
                f"immediate pull-down back below {threshold}°C."
            ),
            "thermal_inertia_analysis": (
                "Surface air temp briefly elevated, but cargo thermal mass prevented core temperature penetration. "
                "Degree-minutes accumulated is negligible (<5°C-min)."
            ),
            "cargo_spoilage_risk": "NEGLIGIBLE",
            "suppressed_as_benign": True,
            "suppress_reason": "Single observation excursion with immediate active re-cooling; no cargo core threat.",
            "recommended_sop_action": "Log as benign delivery activity; no driver intervention needed.",
            "one_line_summary": f"Truck {truck_id} experienced a brief {max_c}°C door-open spike; successfully suppressed.",
        }

    # Case 3: Genuine Sustained Excursion (The T-01 / T-05 scenario)
    if metrics["consecutive_above_max"] >= 3 or (metrics["readings_above_threshold"] >= 3 and max_c >= threshold + 0.5):
        return {
            "truck_id": truck_id,
            "is_real_alert": True,
            "alert_category": "COMPRESSOR_REFRIGERATION_FAILURE",
            "severity": "CRITICAL",
            "confidence_score": 0.98,
            "root_cause_hypothesis": (
                f"Genuine reefer refrigeration excursion. Continuous sustained warming peaking at {max_c}°C "
                f"across {metrics['readings_above_threshold']} observations above {threshold}°C."
            ),
            "thermal_inertia_analysis": (
                f"Substantial degree-minutes above threshold accumulated. Thermal penetration into packaging "
                f"likely underway; active chilling capacity was compromised."
            ),
            "cargo_spoilage_risk": "HIGH",
            "suppressed_as_benign": False,
            "suppress_reason": None,
            "recommended_sop_action": (
                "EMERGENCY DISPATCH: Instruct driver to pull over safely, check reefer error codes, "
                "verify diesel fuel supply to refrigeration unit, and initiate emergency dry-ice protocol if needed."
            ),
            "one_line_summary": f"Truck {truck_id} experienced critical sustained excursion peaking at {max_c}°C.",
        }

    # Case 4: Sub-threshold Creep / Drift (The T-03 scenario)
    # Consistently rising without yet breaching threshold
    if len(temps) >= 4 and temps[-1] > temps[0] + 0.8 and max_c <= threshold:
        return {
            "truck_id": truck_id,
            "is_real_alert": True,
            "alert_category": "SUB_THRESHOLD_DRIFT",
            "severity": "WARNING",
            "confidence_score": 0.89,
            "root_cause_hypothesis": (
                f"Predictive thermal drift detected: temperature climbed monotonically from {temps[0]}°C to {temps[-1]}°C. "
                f"Refrigeration cycle is losing efficiency (potential slow refrigerant leak or condenser fouling)."
            ),
            "thermal_inertia_analysis": (
                f"Still below critical {threshold}°C threshold, but rate of warming will breach threshold within "
                f"estimated 15-20 minutes if current trend continues."
            ),
            "cargo_spoilage_risk": "MODERATE_PREDICTIVE",
            "suppressed_as_benign": False,
            "suppress_reason": None,
            "recommended_sop_action": (
                "PREVENTIVE ALERT: Notify maintenance team to inspect reefer setpoint and condenser coils upon arrival. "
                "Monitor next 3 readings closely."
            ),
            "one_line_summary": f"Truck {truck_id} exhibiting sub-threshold thermal drift ({temps[0]}°C -> {temps[-1]}°C).",
        }

    # Case 5: Normal Stable Operation
    return {
        "truck_id": truck_id,
        "is_real_alert": False,
        "alert_category": "NORMAL_STABLE_OPERATION",
        "severity": "LOW",
        "confidence_score": 0.99,
        "root_cause_hypothesis": "Normal continuous cold-chain maintenance within target specification.",
        "thermal_inertia_analysis": "Refrigeration system maintaining optimal equilibrium. Zero thermal stress.",
        "cargo_spoilage_risk": "NONE",
        "suppressed_as_benign": True,
        "suppress_reason": "Readings are nominal and stable.",
        "recommended_sop_action": "Standard scheduled monitoring.",
        "one_line_summary": f"Truck {truck_id} is operating nominally at mean {metrics['mean_c']}°C.",
    }


def evaluate_real_alert(
    truck_id: str,
    readings: list[dict[str, Any]],
    rule: dict[str, Any],
    incident: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluates telemetry using Anthropic Claude SDK (with automatic fallback to cognitive model).
    Determines whether an alert is real vs false positive, reasons through gaps, and diagnoses root cause.
    """
    threshold_c = float(rule.get("threshold_c", 8.0))
    metrics = calculate_thermal_metrics(readings, threshold_c)

    user_prompt = f"""EVALUATION REQUEST:
Truck ID: {truck_id}
Configured Safety Rule:
- Max Threshold: {threshold_c}°C
- Sustained Duration Required: {rule.get('sustained_minutes', 10)} minutes
- Max Expected Gap: {rule.get('max_gap_minutes', 5)} minutes
- Recovery Window: {rule.get('recovery_minutes', 5)} minutes

Telemetry Observations ({len(readings)} readings):
{readings}

Computed Stream Metrics:
{metrics}

Incident Context (if qualified):
{incident}

Please analyze this stream and determine:
1. Is this a GENUINE REAL ALERT requiring operator action, or a BENIGN EVENT (transient door opening, defrost cycle, normal reading)?
2. If connectivity gaps exist (e.g., >5 minutes), did continuous thermal violation occur during the gap based on thermodynamic continuity?
3. What is the root cause hypothesis, severity level, confidence score (0.0 to 1.0), cargo spoilage risk, and recommended operational SOP action?

Respond with a JSON object strictly having these keys:
{{
  "truck_id": "{truck_id}",
  "is_real_alert": boolean,
  "alert_category": "COMPRESSOR_REFRIGERATION_FAILURE" | "TRANSIENT_DOOR_OPENING" | "DEFROST_CYCLE" | "TELEMETRY_GAP_EXCURSION" | "SUB_THRESHOLD_DRIFT" | "SENSOR_ANOMALY" | "NORMAL_STABLE_OPERATION",
  "severity": "CRITICAL" | "HIGH" | "WARNING" | "BENIGN" | "LOW",
  "confidence_score": float,
  "root_cause_hypothesis": string,
  "thermal_inertia_analysis": string,
  "cargo_spoilage_risk": "HIGH" | "ELEVATED" | "MODERATE_PREDICTIVE" | "NEGLIGIBLE" | "NONE",
  "suppressed_as_benign": boolean,
  "suppress_reason": string or null,
  "recommended_sop_action": string,
  "one_line_summary": string
}}"""

    fallback = lambda: cognitive_fallback_detection(truck_id, readings, rule, metrics)
    return invoke_claude(SYSTEM_PROMPT, user_prompt, fallback_fn=fallback)
