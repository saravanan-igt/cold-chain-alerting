"""Integration tests for AI API endpoints."""
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.storage import Store, load_config
from tests.test_domain import sample


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "ai_test.db")
    value.provision(load_config())
    yield value
    value.engine.dispose()


def test_ai_endpoints_and_auth(store):
    # Ingest readings for T-01 to generate an incident
    for minute in (0, 5, 10, 15):
        store.ingest("nimbus", sample(minute, 9.5).canonical())

    incidents = store.list_incidents("nimbus")
    assert len(incidents) == 1
    incident_id = incidents[0]["id"]

    keys = {
        "op-key": {"tenant": "nimbus", "role": "operator"},
        "device-key": {"tenant": "nimbus", "role": "device", "truck_id": "T-01", "device_id": "sensor-T-01"}
    }

    with TestClient(create_app(store, keys)) as client:
        # 1. AI Status endpoint (public/operator)
        status_res = client.get("/api/v1/ai/status")
        assert status_res.status_code == 200
        data = status_res.json()
        assert "capabilities" in data
        assert "supported_providers" in data

        # 2. Operator authorization requirement
        assert client.get("/api/v1/ai/fleet-assessment").status_code == 401
        assert client.get("/api/v1/ai/fleet-assessment", headers={"X-API-Key": "device-key"}).status_code == 403

        # 3. Fleet assessment endpoint
        fleet_res = client.get("/api/v1/ai/fleet-assessment", headers={"X-API-Key": "op-key"})
        assert fleet_res.status_code == 200
        fleet_ai = fleet_res.json()
        assert "fleet_health_score" in fleet_ai
        assert fleet_ai["fleet_health_score"] is None
        assert len(fleet_ai["truck_assessments"]) > 0

        # 4. Incident triage endpoint
        triage_res = client.get(f"/api/v1/ai/incidents/{incident_id}/triage", headers={"X-API-Key": "op-key"})
        assert triage_res.status_code == 200
        triage = triage_res.json()
        assert triage["incident_id"] == incident_id
        assert len(triage["sop_action_checklist"]) > 0
        assert "driver_dispatch_script" in triage

        # 5. Alert evaluation endpoint
        eval_res = client.post(
            "/api/v1/ai/evaluate-alert",
            json={"truck_id": "T-01"},
            headers={"X-API-Key": "op-key"}
        )
        assert eval_res.status_code == 200
        eval_data = eval_res.json()
        assert eval_data["truck_id"] == "T-01"
        assert eval_data["is_real_alert"] is True
        assert eval_data["confidence_score"] is None
        assert eval_data["cargo_spoilage_risk"] == "NOT_ASSESSED"
        assert client.post(
            "/api/v1/ai/evaluate-alert",
            json={"truck_id": "not-in-this-tenant"},
            headers={"X-API-Key": "op-key"},
        ).status_code == 404

        # 6. Operations Copilot chat endpoint
        chat_res = client.post(
            "/api/v1/ai/chat",
            json={"message": "What is the status of Truck T-01?", "truck_id": "T-01"},
            headers={"X-API-Key": "op-key"}
        )
        assert chat_res.status_code == 200
        chat_data = chat_res.json()
        assert "reply" in chat_data

        # 7. Incidents list endpoint includes AI evaluation
        list_res = client.get("/api/v1/incidents", headers={"X-API-Key": "op-key"})
        assert list_res.status_code == 200
        first_inc = list_res.json()["items"][0]
        assert "ai_evaluation" in first_inc
        assert first_inc["ai_evaluation"]["is_real_alert"] is True
