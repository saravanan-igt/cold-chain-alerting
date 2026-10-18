"""Unit tests for Claude AI Real Alert Detection and Forensic Triage Engine."""
import pytest

from backend.ai.client import get_ai_status
from backend.ai.detector import evaluate_real_alert
from backend.ai.triage import generate_incident_triage
from backend.ai.fleet_advisor import assess_fleet_with_ai
from backend.ai.copilot import chat_with_copilot


def test_ai_status_structure(monkeypatch):
    status = get_ai_status()
    assert "real_alert_detection" in status["capabilities"]
    assert "telemetry_gap_reasoning" in status["capabilities"]
    assert "supported_providers" in status

    # Test Gemini provider activation
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    gemini_status = get_ai_status()
    assert gemini_status["provider"] == "gemini"
    assert "gemini" in gemini_status["model"].lower()

    # Test Anthropic provider preference
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    anthropic_status = get_ai_status()
    assert anthropic_status["provider"] == "anthropic"
    assert "claude" in anthropic_status["model"].lower()


def test_ai_detect_genuine_sustained_alert():
    """T-01 scenario: sustained warming across 4+ readings peaking at 9.6 C."""
    readings = [
        {"timestamp": "2026-07-20T08:10:00+00:00", "temperature_c": 8.5},
        {"timestamp": "2026-07-20T08:15:00+00:00", "temperature_c": 9.0},
        {"timestamp": "2026-07-20T08:20:00+00:00", "temperature_c": 9.4},
        {"timestamp": "2026-07-20T08:25:00+00:00", "temperature_c": 9.6},
        {"timestamp": "2026-07-20T08:30:00+00:00", "temperature_c": 9.3},
    ]
    rule = {"threshold_c": 8.0, "sustained_minutes": 10, "max_gap_minutes": 5, "recovery_minutes": 5}
    result = evaluate_real_alert("T-01", readings, rule)

    assert result["is_real_alert"] is True
    assert result["severity"] == "CRITICAL"
    assert result["confidence_score"] >= 0.90
    assert result["alert_category"] == "COMPRESSOR_REFRIGERATION_FAILURE"
    assert result["suppressed_as_benign"] is False
    assert "T-01" in result["one_line_summary"]


def test_ai_suppress_transient_door_spike():
    """T-02 scenario: isolated spike of 8.9 C with immediate recovery."""
    readings = [
        {"timestamp": "2026-07-20T08:00:00+00:00", "temperature_c": 6.0},
        {"timestamp": "2026-07-20T08:05:00+00:00", "temperature_c": 6.2},
        {"timestamp": "2026-07-20T08:10:00+00:00", "temperature_c": 8.9},
        {"timestamp": "2026-07-20T08:15:00+00:00", "temperature_c": 6.5},
        {"timestamp": "2026-07-20T08:20:00+00:00", "temperature_c": 6.3},
    ]
    rule = {"threshold_c": 8.0, "sustained_minutes": 10, "max_gap_minutes": 5, "recovery_minutes": 5}
    result = evaluate_real_alert("T-02", readings, rule)

    assert result["is_real_alert"] is False
    assert result["suppressed_as_benign"] is True
    assert result["alert_category"] == "TRANSIENT_DOOR_OPENING"
    assert result["cargo_spoilage_risk"] == "NEGLIGIBLE"


def test_ai_detect_telemetry_gap_excursion():
    """T-04 scenario: 10-minute gap with warmth before (8.9 C) and after (9.1 C)."""
    readings = [
        {"timestamp": "2026-07-20T08:25:00+00:00", "temperature_c": 8.7},
        {"timestamp": "2026-07-20T08:30:00+00:00", "temperature_c": 8.9},
        # 10 min unmonitored gap here
        {"timestamp": "2026-07-20T08:40:00+00:00", "temperature_c": 9.1},
        {"timestamp": "2026-07-20T08:45:00+00:00", "temperature_c": 8.5},
    ]
    rule = {"threshold_c": 8.0, "sustained_minutes": 10, "max_gap_minutes": 5, "recovery_minutes": 5}
    result = evaluate_real_alert("T-04", readings, rule)

    assert result["is_real_alert"] is True
    assert result["alert_category"] == "TELEMETRY_GAP_EXCURSION"
    assert result["severity"] == "CRITICAL"
    assert "gap" in result["root_cause_hypothesis"].lower() or "blackout" in result["root_cause_hypothesis"].lower()


def test_ai_detect_sub_threshold_drift():
    """T-03 scenario: creeping upward from 5.8 to 7.0 C under the 8.0 ceiling."""
    readings = [
        {"timestamp": "2026-07-20T08:00:00+00:00", "temperature_c": 5.8},
        {"timestamp": "2026-07-20T08:05:00+00:00", "temperature_c": 6.0},
        {"timestamp": "2026-07-20T08:10:00+00:00", "temperature_c": 6.3},
        {"timestamp": "2026-07-20T08:15:00+00:00", "temperature_c": 6.6},
        {"timestamp": "2026-07-20T08:20:00+00:00", "temperature_c": 6.8},
        {"timestamp": "2026-07-20T08:25:00+00:00", "temperature_c": 7.0},
    ]
    rule = {"threshold_c": 8.0, "sustained_minutes": 10, "max_gap_minutes": 5, "recovery_minutes": 5}
    result = evaluate_real_alert("T-03", readings, rule)

    assert result["alert_category"] == "SUB_THRESHOLD_DRIFT"
    assert result["severity"] == "WARNING"


def test_ai_incident_triage():
    incident = {
        "id": "inc-01",
        "truck_id": "T-01",
        "lifecycle": "open",
        "excursion_started_at": "2026-07-20T08:10:00+00:00",
        "qualified_at": "2026-07-20T08:20:00+00:00",
        "observed_max_c": 9.6,
        "supported_warm_seconds": 1200,
        "telemetry_gap_count": 0,
        "recovery_confirmed_at": None,
    }
    evidence = [
        {"timestamp": "2026-07-20T08:10:00+00:00", "temperature_c": 8.5},
        {"timestamp": "2026-07-20T08:15:00+00:00", "temperature_c": 9.0},
        {"timestamp": "2026-07-20T08:20:00+00:00", "temperature_c": 9.6},
        {"timestamp": "2026-07-20T08:25:00+00:00", "temperature_c": 9.4},
    ]
    rule = {"threshold_c": 8.0, "sustained_minutes": 10, "max_gap_minutes": 5, "recovery_minutes": 5}
    triage = generate_incident_triage(incident, evidence, rule)

    assert triage["truck_id"] == "T-01"
    assert len(triage["sop_action_checklist"]) >= 3
    assert len(triage["driver_dispatch_script"]) > 20
    assert triage["thermal_forensics"]["peak_temperature_c"] == 9.6


def test_ai_copilot_chat():
    context = {
        "fleet": {"trucks": [{"id": "T-01", "status": "open"}, {"id": "T-04", "status": "normal"}]},
        "incidents": [],
    }
    ans_t04 = chat_with_copilot("Why did T-04 not alert on the gap?", context)
    assert "T-04" in ans_t04["reply"]
    assert len(ans_t04["suggested_actions"]) > 0

    ans_sms = chat_with_copilot("Draft an SMS for the driver", context)
    assert "DISPATCH" in ans_sms["reply"].upper()
