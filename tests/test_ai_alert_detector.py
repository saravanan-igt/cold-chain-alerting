"""Tests for deterministic, evidence-grounded operational summaries."""
import pytest

from backend.ai.client import get_ai_status
from backend.ai.detector import evaluate_real_alert
from backend.ai.triage import generate_incident_triage
from backend.ai.fleet_advisor import assess_fleet_with_ai
from backend.ai.copilot import chat_with_copilot


def test_ai_status_structure(monkeypatch):
    status = get_ai_status()
    assert "configured_rule_evaluation" in status["capabilities"]
    assert "supported_providers" in status
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    assert get_ai_status()["provider"] == "deterministic_rules"
    assert get_ai_status()["has_api_key"] is False


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
    assert result["severity"] == "WARNING"
    assert result["confidence_score"] is None
    assert result["alert_category"] == "QUALIFIED_EXCURSION"
    assert result["suppressed_as_benign"] is False
    assert "T-01" in result["one_line_summary"]
    assert result["cargo_spoilage_risk"] == "NOT_ASSESSED"


def test_short_spike_does_not_qualify():
    """An isolated warm observation is below the sustained-duration rule."""
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
    assert result["suppressed_as_benign"] is False
    assert result["alert_category"] == "NO_QUALIFIED_EXCURSION"
    assert result["cargo_spoilage_risk"] == "NOT_ASSESSED"


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

    assert result["is_real_alert"] is False
    assert result["alert_category"] == "UNCONFIRMED_TELEMETRY_GAP"
    assert result["severity"] == "WARNING"
    assert "gap" in result["one_line_summary"].lower()
    assert "not assumed" in result["one_line_summary"].lower()


def test_ai_detect_sub_threshold_drift():
    """A below-threshold rise is not presented as a predictive safety warning."""
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

    assert result["alert_category"] == "NO_QUALIFIED_EXCURSION"
    assert result["severity"] == "LOW"


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
