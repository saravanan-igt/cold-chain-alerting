import hmac
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import OperationalError

from backend.storage import SCHEMA_VERSION, Store, load_config
from backend.configuration import Credential
from backend.domain import Reading
from backend.auth import COOKIE, SESSION_SECONDS, OperatorSessions
from backend.identity import OidcVerifier
from backend.notifications import NotificationWorker
from backend.observability import configure_logging, logger, metrics, request_id_var
from backend.scenarios import SAMPLE_SECONDS, catalogue, describe
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
    readings: list[Reading] | None = Field(default=None, max_length=100)
    incident_id: str | None = None


class AiChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    truck_id: str | None = None
    incident_id: str | None = None


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=500)


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    truck_id: str = Field(min_length=1, max_length=80)
    scenario: str = Field(min_length=1, max_length=60)


class ScenarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["running", "completed", "cancelled"]


REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
QUIET_PATHS = ("/health", "/ready", "/metrics")


def create_app(store=None, credentials=None, users=None, worker=None, oidc=None):
    configure_logging()

    @asynccontextmanager
    async def lifespan(app):
        owned = store is None
        app.state.store = store or Store(os.getenv("COLDCHAIN_DATABASE_URL") or os.getenv("COLDCHAIN_DB", "coldchain.db"))
        config = load_config(os.getenv("COLDCHAIN_CONFIG", "config/customers.json"))
        app.state.store.provision(config)
        app.state.credentials = credentials if credentials is not None else json.loads(os.environ.get("COLDCHAIN_CREDENTIALS", "{}"))
        accounts = users if users is not None else json.loads(os.environ.get("COLDCHAIN_USERS", "{}"))
        tenant_ids = {tenant["id"] for tenant in config["tenants"]}
        for username, account in accounts.items():
            if not username or account.get("tenant") not in tenant_ids or not account.get("password_hash", "").startswith("scrypt$"):
                raise ValueError("Operator account requires a username, known tenant and scrypt password hash")
        # Sessions live in the shared database so any replica can serve any request.
        app.state.sessions = OperatorSessions(accounts, store=app.state.store)
        app.state.oidc = oidc if oidc is not None else OidcVerifier.from_env(tenant_ids)
        if not app.state.credentials and not accounts and not app.state.oidc:
            raise RuntimeError("Configure credentials/accounts/OIDC or run python -m backend.cli demo")
        for key, raw in app.state.credentials.items():
            identity = Credential.model_validate(raw)
            customer = next((t for t in config["tenants"] if t["id"] == identity.tenant), None)
            if not key or customer is None:
                raise ValueError("Credential references an unknown tenant or empty key")
            if identity.role == "device" and not any(t["id"] == identity.truck_id and t["device_id"] == identity.device_id for t in customer["trucks"]):
                raise ValueError("Credential references an unauthorized stream")
        app.state.worker = None
        if worker is not None:
            app.state.worker = worker or None
        elif os.getenv("COLDCHAIN_NOTIFICATION_WORKER", "1") == "1":
            app.state.worker = NotificationWorker(app.state.store).start()
        logger.info("Coldline API started", extra={"event": "startup"})
        yield
        if app.state.worker and app.state.worker.thread:
            app.state.worker.stop()
        if owned:
            app.state.store.engine.dispose()

    app = FastAPI(title="Coldline · Cold-chain operations", version="1.0.0", lifespan=lifespan)
    key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    @app.middleware("http")
    async def bound_body(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID.match(supplied) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            # Enforce actual bytes, including requests without Content-Length.
            response = None
            if request.method == "POST":
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 262144:
                        response = JSONResponse({"detail": "Request exceeds 256 KiB"}, status_code=413)
                        break
                request._body = bytes(body)
            if response is None:
                response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Request-ID"] = request_id
            route = request.scope.get("route")
            template = getattr(route, "path", None) or ("static" if route is not None else "unmatched")
            elapsed = time.perf_counter() - started
            metrics.inc("coldline_http_requests_total", method=request.method, route=template, status=str(response.status_code))
            metrics.observe("coldline_http_request_duration_seconds", elapsed, method=request.method, route=template)
            if not request.url.path.startswith(QUIET_PATHS) and template != "static":
                logger.info("%s %s %s %.1fms", request.method, template, response.status_code, elapsed * 1000,
                            extra={"event": "http_request", "method": request.method, "route": template,
                                              "status": response.status_code, "duration_ms": round(elapsed * 1000, 1)})
            return response
        finally:
            request_id_var.reset(token)

    def principal(request: Request, key: str | None = Depends(key_header)):
        for secret, identity in request.app.state.credentials.items():
            if key and hmac.compare_digest(key.encode(), secret.encode()):
                return {**identity, "via": "api_key"}
        authorization = request.headers.get("Authorization", "")
        if not key and request.app.state.oidc and authorization[:7].lower() == "bearer ":
            identity = request.app.state.oidc.verify(authorization[7:].strip())
            if identity:
                return {**identity, "via": "oidc"}
            raise HTTPException(401, "Invalid or unauthorised bearer token")
        if not key:
            identity = request.app.state.sessions.resolve(request.cookies.get(COOKIE))
            if identity:
                return {**identity, "via": "cookie"}
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

    def acting_operator(request: Request, identity=Depends(operator)):
        # Cookie-authenticated state changes need the custom header (CSRF defence in depth).
        if identity.get("via") == "cookie" and request.headers.get("X-Coldline-Request") != "browser":
            raise HTTPException(403, "Browser request header required")
        return identity

    def actor(identity):
        return identity.get("username") or f"api-key:{identity['tenant']}"

    @app.exception_handler(OperationalError)
    async def database_busy(_, exc):
        return JSONResponse({"detail": "Storage unavailable; retry with the same event identity"}, status_code=503, headers={"Retry-After": "2"})

    @app.get("/health")
    def health():
        """Liveness: the process is serving requests. Does not touch dependencies."""
        return {"status": "ok", "schema_version": SCHEMA_VERSION}

    @app.get("/ready")
    def ready(request: Request):
        """Readiness: database reachable at the expected schema and, if hosted here, the worker is cycling."""
        checks = {}
        try:
            checks["database"] = "ok" if request.app.state.store.ping() == SCHEMA_VERSION else "schema_mismatch"
        except Exception as exc:  # report, never raise: the orchestrator only needs the status code
            checks["database"] = f"error: {type(exc).__name__}"
        worker_ = request.app.state.worker
        if worker_ is not None and worker_.thread is not None:
            checks["notification_worker"] = "ok" if worker_.healthy() or (worker_.last_run is None and worker_.thread.is_alive()) else "stalled"
        status = 200 if all(value == "ok" for value in checks.values()) else 503
        return JSONResponse({"status": "ready" if status == 200 else "not_ready", "checks": checks}, status_code=status)

    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus(request: Request):
        expected = os.getenv("COLDCHAIN_METRICS_TOKEN")
        supplied = request.headers.get("Authorization", "")
        if expected and not hmac.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
            raise HTTPException(401, "Metrics token required")
        counts = request.app.state.store.outbox_counts()
        worker_ = request.app.state.worker
        gauges = {
            "coldline_open_incidents": ("Open incidents across all tenants", counts.get("open_incidents", 0)),
            "coldline_outbox_pending": ("Notifications waiting for delivery or retry", counts.get("pending", 0) + counts.get("sending", 0)),
            "coldline_outbox_dead": ("Dead-lettered notifications needing operator action", counts.get("dead", 0)),
            "coldline_worker_last_cycle_age_seconds": ("Seconds since the in-process worker last cycled (-1 if not hosted here)",
                                                       time.time() - worker_.last_run if worker_ and worker_.last_run else -1),
        }
        return PlainTextResponse(metrics.render(gauges), media_type="text/plain; version=0.0.4")

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
                item["ai_evaluation"] = evaluate_real_alert(item["truck_id"], [], item["rule"], incident=item)
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

    @app.post("/api/v1/incidents/{incident_id}/acknowledge")
    def acknowledge(request: Request, incident_id: str, body: AcknowledgeRequest | None = None, identity=Depends(acting_operator)):
        """Record that a named operator owns the response. Idempotent; stops further escalation."""
        note = body.note.strip() if body and body.note else None
        result = request.app.state.store.acknowledge(identity["tenant"], incident_id, actor(identity), note or None)
        if result is None:
            raise HTTPException(404, "Incident not found")
        logger.info("Incident acknowledged", extra={"event": "acknowledged", "tenant": identity["tenant"], "incident_id": incident_id})
        return {"incident_id": incident_id, **result}

    @app.get("/api/v1/notifications")
    def notifications(request: Request, status: Literal["pending", "sending", "delivered", "dead"] | None = None,
                      limit: Annotated[int, Query(ge=1, le=100)] = 50,
                      offset: Annotated[int, Query(ge=0, le=100000)] = 0, identity=Depends(operator)):
        return {"items": request.app.state.store.list_notifications(identity["tenant"], status, limit, offset), "limit": limit, "offset": offset}

    @app.post("/api/v1/notifications/{notification_id}/retry")
    def retry_notification(request: Request, notification_id: int, identity=Depends(acting_operator)):
        if not request.app.state.store.retry_notification(identity["tenant"], notification_id):
            raise HTTPException(404, "No dead-lettered notification with this id")
        return {"id": notification_id, "status": "pending"}

    # ---- live-demo scenario injection (only for tenants labelled demo_mode=live_simulation) ----
    def demo_tenant(request: Request, identity=Depends(operator)):
        config = request.app.state.store.tenant_config(identity["tenant"]) or {}
        if config.get("demo_mode") != "live_simulation":
            raise HTTPException(404, "Demo scenarios are only available for live-simulation tenants")
        return identity

    def demo_actor(request: Request, identity=Depends(demo_tenant)):
        return acting_operator(request, identity)

    def truck_rules(request, tenant):
        return {truck["id"]: truck["rule"] for truck in request.app.state.store.fleet(tenant)["trucks"]}

    @app.get("/api/v1/demo/scenarios")
    def demo_scenarios(request: Request, active: bool = False, identity=Depends(demo_tenant)):
        tenant = identity["tenant"]
        config = request.app.state.store.tenant_config(tenant)
        rules = truck_rules(request, tenant)
        runs = request.app.state.store.list_scenarios(tenant, active_only=active)
        for run in runs:
            definition = catalogue(rules[run["truck_id"]]).get(run["scenario"], {})
            run.update(label=definition.get("label", run["scenario"]), genuine=definition.get("genuine"),
                       expected_incident=definition.get("expected_incident"), steps=definition.get("steps", []))
        return {"sample_seconds": SAMPLE_SECONDS, "catalogue": describe(config["rule"]), "runs": runs}

    @app.post("/api/v1/demo/scenarios", status_code=201)
    def start_demo_scenario(request: Request, body: ScenarioRequest, identity=Depends(demo_actor)):
        rules = truck_rules(request, identity["tenant"])
        if body.truck_id not in rules:
            raise HTTPException(404, "Truck not found")
        if body.scenario not in catalogue(rules[body.truck_id]):
            raise HTTPException(422, "Unknown scenario for this truck's rule")
        run, error = request.app.state.store.request_scenario(identity["tenant"], body.truck_id, body.scenario, actor(identity))
        if error:
            raise HTTPException(409, error)
        logger.info("Demo scenario requested", extra={"event": "demo_scenario", "tenant": identity["tenant"], "scenario": body.scenario, "truck_id": body.truck_id})
        return run

    @app.patch("/api/v1/demo/scenarios/{run_id}")
    def update_demo_scenario(request: Request, run_id: int, body: ScenarioUpdate, identity=Depends(demo_actor)):
        run, changed = request.app.state.store.update_scenario(identity["tenant"], run_id, body.status)
        if run is None:
            raise HTTPException(404, "Scenario run not found")
        if not changed:
            raise HTTPException(409, f"Scenario run is {run['status']}")
        return run

    @app.get("/api/v1/ai/status")
    def ai_status():
        return get_ai_status()

    @app.post("/api/v1/ai/evaluate-alert")
    def ai_evaluate(request: Request, body: EvaluateAlertRequest, identity=Depends(operator)):
        tenant = identity["tenant"]
        fleet_info = request.app.state.store.fleet(tenant)
        truck = next((t for t in fleet_info["trucks"] if t["id"] == body.truck_id), None)
        if truck is None:
            raise HTTPException(404, "Truck not found")
        readings = (
            [row.canonical() for row in body.readings]
            if body.readings is not None
            else request.app.state.store.get_truck_readings(tenant, body.truck_id, limit=100)
        )
        if any(row["truck_id"] != body.truck_id for row in readings):
            raise HTTPException(422, "All readings must belong to the requested truck")
        rule = truck["rule"]
        incident = None
        if body.incident_id:
            incident = request.app.state.store.detail(tenant, body.incident_id)
            if incident is None or incident["truck_id"] != body.truck_id:
                raise HTTPException(404, "Incident not found for this truck")
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
        return assess_fleet_with_ai(fleet_info, {}, {})

    @app.post("/api/v1/ai/chat")
    def ai_copilot_chat(request: Request, body: AiChatRequest, identity=Depends(operator)):
        tenant = identity["tenant"]
        selected_incident = None
        selected_truck = body.truck_id
        if body.incident_id:
            selected_incident = request.app.state.store.detail(tenant, body.incident_id, limit=1)
            if selected_incident is None or (
                selected_truck and selected_incident["truck_id"] != selected_truck
            ):
                raise HTTPException(404, "Incident not found for this customer and truck")
            selected_truck = selected_truck or selected_incident["truck_id"]
        fleet_info = request.app.state.store.fleet(tenant)
        incidents = request.app.state.store.list_incidents(tenant, limit=10)
        context = {
            "fleet": fleet_info,
            "incidents": incidents,
            "selected_truck": selected_truck,
            "selected_incident": selected_incident,
        }
        return chat_with_copilot(body.message, context)

    if Path("frontend/out").is_dir():
        app.mount("/", StaticFiles(directory="frontend/out", html=True), name="dashboard")
    return app
