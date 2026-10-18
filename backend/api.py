import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import OperationalError

from backend.storage import Store, load_config
from backend.configuration import Credential
from backend.auth import COOKIE, SESSION_SECONDS, OperatorSessions
from backend.ai.client import get_ai_status
from backend.ai.detector import evaluate_real_alert
from backend.ai.triage import generate_incident_triage
from backend.ai.fleet_advisor import assess_fleet_with_ai
from backend.ai.copilot import chat_with_copilot


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    readings: list[dict] = Field(min_length=1, max_length=100)


class Outcome(BaseModel):
    status: Literal["accepted", "duplicate", "late", "invalid", "conflict", "unauthorized"]
    reason: str | None = None
    reading_id: int | None = None
    incident_id: str | None = None


class BatchResult(BaseModel):
    results: list[Outcome]
    counts: dict[str, int]


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class EvaluateAlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    truck_id: str = Field(min_length=1, max_length=80)
    readings: list[dict] | None = None
    incident_id: str | None = None


class AiChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    truck_id: str | None = None
    incident_id: str | None = None


def create_app(store=None, credentials=None, users=None):
    @asynccontextmanager
    async def lifespan(app):
        owned = store is None
        app.state.store = store or Store(os.getenv("COLDCHAIN_DB", "coldchain.db"))
        config = load_config(os.getenv("COLDCHAIN_CONFIG", "config/customers.json"))
        app.state.store.provision(config)
        app.state.credentials = credentials if credentials is not None else json.loads(os.environ.get("COLDCHAIN_CREDENTIALS", "{}"))
        accounts = users if users is not None else json.loads(os.environ.get("COLDCHAIN_USERS", "{}"))
        tenant_ids = {tenant["id"] for tenant in config["tenants"]}
        for username, account in accounts.items():
            if not username or account.get("tenant") not in tenant_ids or not account.get("password_hash", "").startswith("scrypt$"):
                raise ValueError("Operator account requires a username, known tenant and scrypt password hash")
        app.state.sessions = OperatorSessions(accounts)
        if not app.state.credentials and not accounts:
            raise RuntimeError("Configure credentials/accounts or run python -m backend.cli demo")
        for key, raw in app.state.credentials.items():
            identity = Credential.model_validate(raw)
            customer = next((t for t in config["tenants"] if t["id"] == identity.tenant), None)
            if not key or customer is None:
                raise ValueError("Credential references an unknown tenant or empty key")
            if identity.role == "device" and not any(t["id"] == identity.truck_id and t["device_id"] == identity.device_id for t in customer["trucks"]):
                raise ValueError("Credential references an unauthorized stream")
        yield
        if owned:
            app.state.store.engine.dispose()

    app = FastAPI(title="Coldline · Cold-chain operations", version="1.0.0", lifespan=lifespan)
    key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    @app.middleware("http")
    async def bound_body(request: Request, call_next):
        # Enforce actual bytes, including requests without Content-Length.
        if request.method == "POST":
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 262144:
                    return JSONResponse({"detail": "Request exceeds 256 KiB"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def principal(request: Request, key: str | None = Depends(key_header)):
        for secret, identity in request.app.state.credentials.items():
            if key and hmac.compare_digest(key.encode(), secret.encode()):
                return identity
        if not key:
            identity = request.app.state.sessions.resolve(request.cookies.get(COOKIE))
            if identity:
                return identity
        raise HTTPException(401, "Missing or invalid session or API key")

    def browser_request(request: Request):
        # A cross-origin HTML form cannot set this header; CORS is not enabled.
        if request.headers.get("X-Coldline-Request") != "browser":
            raise HTTPException(403, "Browser request header required")

    @app.post("/api/v1/session", dependencies=[Depends(browser_request)])
    def login(request: Request, body: Login):
        token, identity = request.app.state.sessions.login(body.username, body.password, request.client.host if request.client else "unknown")
        request.app.state.sessions.revoke(request.cookies.get(COOKIE))
        response = JSONResponse({"username": identity["username"], "tenant": identity["tenant"]})
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                            secure=os.getenv("COLDCHAIN_SECURE_COOKIES", "0") == "1", path="/api/v1")
        return response

    @app.delete("/api/v1/session", dependencies=[Depends(browser_request)])
    def logout(request: Request):
        request.app.state.sessions.revoke(request.cookies.get(COOKIE))
        response = JSONResponse({"status": "signed_out"})
        response.delete_cookie(COOKIE, path="/api/v1", httponly=True, samesite="strict")
        return response

    def operator(identity=Depends(principal)):
        if identity.get("role") != "operator":
            raise HTTPException(403, "Operator credential required")
        return identity

    @app.exception_handler(OperationalError)
    async def database_busy(_, exc):
        return JSONResponse({"detail": "Storage unavailable; retry with the same event identity"}, status_code=503, headers={"Retry-After": "2"})

    @app.get("/health")
    def health():
        return {"status": "ok", "schema_version": 1}

    @app.post("/api/v1/readings", response_model=BatchResult, response_model_exclude_unset=True)
    def ingest(request: Request, body: Batch, identity=Depends(principal)):
        if identity.get("role") != "device":
            raise HTTPException(403, "Device credential required")
        outcomes = [request.app.state.store.ingest(identity["tenant"], row, binding=identity) for row in body.readings]
        return {"results": outcomes, "counts": {status: sum(r["status"] == status for r in outcomes) for status in ("accepted", "duplicate", "late", "invalid", "conflict", "unauthorized")}}

    @app.get("/api/v1/trucks")
    def fleet(request: Request, identity=Depends(operator)):
        return request.app.state.store.fleet(identity["tenant"])

    @app.get("/api/v1/incidents")
    def listing(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                offset: Annotated[int, Query(ge=0, le=100000)] = 0,
                lifecycle: Literal["open", "recovered"] | None = None,
                truck_id: Annotated[str | None, Query(max_length=80)] = None, identity=Depends(operator)):
        items = request.app.state.store.list_incidents(identity["tenant"], limit, offset, lifecycle, truck_id)
        enhanced = []
        for inc in items:
            item = dict(inc)
            if "ai_evaluation" not in item:
                readings = request.app.state.store.get_truck_readings(identity["tenant"], item["truck_id"], limit=50)
                item["ai_evaluation"] = evaluate_real_alert(item["truck_id"], readings, item["rule"], incident=item)
            enhanced.append(item)
        return {"items": enhanced, "limit": limit, "offset": offset}

    @app.get("/api/v1/incidents/{incident_id}")
    def detail(request: Request, incident_id: str,
               limit: Annotated[int, Query(ge=1, le=100)] = 100,
               offset: Annotated[int, Query(ge=0, le=100000)] = 0, identity=Depends(operator)):
        result = request.app.state.store.detail(identity["tenant"], incident_id, limit, offset)
        if result is None:
            raise HTTPException(404, "Incident not found")
        result = dict(result)
        result["ai_evaluation"] = evaluate_real_alert(result["truck_id"], result["evidence"], result["rule"], incident=result)
        result["ai_triage"] = generate_incident_triage(result, result["evidence"], result["rule"])
        return result

    @app.get("/api/v1/ai/status")
    def ai_status():
        return get_ai_status()

    @app.post("/api/v1/ai/evaluate-alert")
    def ai_evaluate(request: Request, body: EvaluateAlertRequest, identity=Depends(operator)):
        tenant = identity["tenant"]
        readings = body.readings
        if not readings:
            readings = request.app.state.store.get_truck_readings(tenant, body.truck_id, limit=100)
        fleet_info = request.app.state.store.fleet(tenant)
        truck = next((t for t in fleet_info["trucks"] if t["id"] == body.truck_id), None)
        rule = truck["rule"] if truck else {"threshold_c": 8.0, "sustained_minutes": 10, "max_gap_minutes": 5, "recovery_minutes": 5}
        incident = None
        if body.incident_id:
            incident = request.app.state.store.detail(tenant, body.incident_id)
        return evaluate_real_alert(body.truck_id, readings, rule, incident)

    @app.get("/api/v1/ai/incidents/{incident_id}/triage")
    def ai_triage(request: Request, incident_id: str, identity=Depends(operator)):
        tenant = identity["tenant"]
        incident = request.app.state.store.detail(tenant, incident_id, limit=200)
        if incident is None:
            raise HTTPException(404, "Incident not found")
        return generate_incident_triage(incident, incident["evidence"], incident["rule"])

    @app.get("/api/v1/ai/fleet-assessment")
    def ai_fleet_scan(request: Request, identity=Depends(operator)):
        tenant = identity["tenant"]
        fleet_info = request.app.state.store.fleet(tenant)
        readings_by_truck = request.app.state.store.get_readings_by_truck(tenant, limit_per_truck=50)
        rules_by_truck = {t["id"]: t["rule"] for t in fleet_info["trucks"]}
        return assess_fleet_with_ai(fleet_info, readings_by_truck, rules_by_truck)

    @app.post("/api/v1/ai/chat")
    def ai_copilot_chat(request: Request, body: AiChatRequest, identity=Depends(operator)):
        tenant = identity["tenant"]
        fleet_info = request.app.state.store.fleet(tenant)
        incidents = request.app.state.store.list_incidents(tenant, limit=10)
        context = {
            "tenant": tenant,
            "fleet": fleet_info,
            "incidents": incidents,
            "selected_truck": body.truck_id,
        }
        return chat_with_copilot(body.message, context)

    if Path("frontend/out").is_dir():
        app.mount("/", StaticFiles(directory="frontend/out", html=True), name="dashboard")
    return app
