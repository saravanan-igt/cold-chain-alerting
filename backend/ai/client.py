"""Compatibility status endpoint for the local, deterministic advisory services."""
from typing import Any


def get_ai_status() -> dict[str, Any]:
    return {
        "provider": "deterministic_rules",
        "model": "coldline-detector-v1",
        "mode": "local",
        "has_api_key": False,
        "gemini_configured": False,
        "anthropic_configured": False,
        "available_providers": ["deterministic_rules"],
        "supported_providers": ["deterministic_rules"],
        "capabilities": [
            "configured_rule_evaluation",
            "telemetry_gap_visibility",
            "incident_evidence_summary",
            "tenant_scoped_fleet_summary",
        ],
        "limitations": [
            "no_equipment_cause_inference",
            "no_cargo_disposition_assessment",
            "no_external_model_calls",
        ],
    }
