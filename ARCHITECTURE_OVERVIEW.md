# Coldline: architecture overview

This document summarises Coldline's design principles, architectural patterns, guardrails, security, SOLID usage, database schema, real-time behaviour, caching and roadmap. For detailed behaviour see [SOLUTION_DESIGN.md](SOLUTION_DESIGN.md), [README.md](README.md) and [frontend/ARCHITECTURE.md](frontend/ARCHITECTURE.md).

## 1. System design principles

- **Safety first and deterministic:** only a rule-based detector opens or closes incidents. No ML or LLM sits in the alert path.
- **Explainable decisions:** every incident stores its evidence, the rule snapshot it used and its lifecycle timestamps.
- **Honest semantics:** a data gap is "unknown", stale data is never shown as "safe", and the system never claims a root cause.
- **Fail closed:** the app refuses to start without credentials, rejects an unknown schema, and returns a retryable 503 rather than guessing.
- **Idempotency everywhere:** readings, acknowledgements, outbox rows, scenario runs and replays can all be repeated safely.
- **Tenant isolation by construction:** the tenant always comes from the credential, never from the request body.
- **Least privilege and defence in depth.**
- **Stateless compute, state in the database,** so the app can scale horizontally.
- **Configuration over code:** new customers, rules and channels need JSON config, not a code fork.
- **Evolutionary architecture:** start on SQLite, move to PostgreSQL, then split the worker out, all with the same code.
- **Observable by default:** structured logs, request IDs, metrics and probes.

## 2. Architectural patterns

| Pattern | Where |
|---|---|
| Modular monolith | One deployable with separate domain, storage, API, notification, identity and observability modules |
| Hexagonal (ports and adapters) | Pure detector core; HTTP, CLI replay and the simulator are adapters that call the same ingest service |
| State machine | Incident lifecycle: normal → candidate → open → recovering → recovered |
| Transactional outbox | Notification rows commit in the same transaction as the incident |
| Competing consumers, lease | Workers claim outbox rows with `FOR UPDATE SKIP LOCKED` and a 60 s lease |
| Retry with exponential backoff and jitter, plus a dead-letter queue | Notification delivery |
| Idempotent receiver | Reading identity or fingerprint; `X-Coldline-Delivery` header for webhook receivers |
| Snapshot | The rule is copied into each candidate and incident |
| Append-only audit log | `incident_events` timeline |
| Repository / gateway | The `Store` class hides SQL behind a common interface for SQLite and PostgreSQL |
| App factory and dependency injection | `create_app(store, credentials, users, worker, oidc)` |
| Middleware pipeline | Request ID → body limit → metrics → access log |
| Health and readiness probes | `/health` (liveness) and `/ready` (database and worker) |
| Frontend: container/presentational and atomic design | Feature controllers own data; atoms → molecules → organisms are props-only |
| Client cache with tag invalidation | RTK Query |
| Dev proxy | Next.js proxies `/api` to FastAPI in development |

## 3. Guardrails

### Backend

**Alert correctness (the safety core)**
- Only the rule-based Python detector opens or recovers incidents. The "AI" summaries are deterministic and never call an external model.
- An incident opens only after the temperature stays above the threshold for the full sustained window; a single spike cannot open one.
- A data gap longer than the allowed maximum breaks continuity. Missing data never counts as recovery, and an open incident stays open while telemetry is missing.
- Recovery requires continuous normal readings for the configured recovery window.
- Each incident keeps a snapshot of the rule it opened under, so later config changes don't rewrite history.
- Late readings are stored but never change past decisions. Duplicates are ignored. A changed reading that reuses the same ID is rejected as a conflict.
- Explanations state only what was observed. They never claim a root cause or that cargo is safe or spoiled, and gaps are labelled "unknown".

**Data integrity**
- A reading, the detector state, the incident, its timeline entry and its notification rows are saved in one transaction: all or nothing.
- The truck's state is locked before it is read (SQLite `BEGIN IMMEDIATE`; PostgreSQL `SELECT … FOR UPDATE` on the truck row), so two requests can't both change the same truck.
- Database unique constraints and foreign keys back up the application checks.
- Schema migrations are versioned, and the app refuses to start on an unknown newer schema.

**Input validation**
- Pydantic models reject unknown fields.
- Batches accept 1–100 readings, and request bodies are capped at 256 KiB (larger requests get a 413).
- Timestamps must include a timezone and may not be more than 5 minutes in the future. Temperatures must be finite numbers in Celsius.
- Text fields have length limits; for example, an acknowledgement note is limited to 500 characters and an assistant message to 2,000.
- Customer config is validated on load:
  - up to 100 tenants and 1,000 trucks per tenant
  - no duplicate trucks or devices
  - valid notification channels and escalation order

**Operations safety**
- Notifications are saved with the incident, and delivery is at-least-once.
- Webhooks are HMAC-signed, redirects are not followed, and requests time out after 5 seconds.
- Failed deliveries retry with backoff and go to a dead-letter queue after 8 attempts; operators can retry them.
- Acknowledgement is idempotent and audited. It stops escalation but does not close the incident.
- Demo scenarios run only for tenants in live-simulation mode. They are blocked on a truck that has an open incident or an active run.
- Restore refuses to overwrite an existing database unless forced. Backups are integrity-checked and SHA-256 verified.

### Frontend

- **Architecture rule:** ESLint stops presentation components from importing API or store code; only feature controllers call the API.
- **Customer isolation:** each sign-in creates a fresh Redux store. Sign-out aborts in-flight requests and clears cached data, so a late response can't appear under another customer.
- **No stored secrets:** passwords and tokens never go into Redux, localStorage or readable cookies. Redux DevTools is disabled.
- **Honest display:**
  - Old data is labelled historical or stale, and stale is never shown as safe.
  - The chart doesn't draw a line across a data gap.
  - The live simulation is clearly labelled.
  - Scores the system doesn't have are shown as unavailable.
- **Safe workflows:**
  - Scenario buttons are disabled while a truck is busy.
  - Server conflict and validation messages are shown to the user.
  - Results that don't match the expected outcome are flagged "Mismatch — review".
  - Filtered or paged views use only the current query's data, so a stale result is never shown under a new selection.
- **Explicit states:** loading, empty, error-with-retry and stale-data states are all handled.

## 4. Security layers

1. **Transport:** TLS terminates at the ingress. Cookies can be marked `Secure` (`COLDCHAIN_SECURE_COOKIES=1`), and the dev ports bind to loopback only.
2. **Identity:**
   - Devices and integrations use API keys, compared in constant time.
   - Pilot users have passwords stored as scrypt hashes.
   - Customer sign-in can use OIDC JWTs (RS256/ES256 only; issuer, audience, tenant and role are all checked).
   - The database can use Azure managed identity.
3. **Sessions:**
   - Only SHA-256 hashes of session tokens are stored.
   - Sessions expire after 8 hours and are revoked on sign-out.
   - Cookies are HttpOnly and `SameSite=Strict`.
   - Login is limited to 10 attempts per minute per client.
   - Failed logins take the same time whether or not the username exists.
4. **Authorisation:** roles are separated (device or operator). A device can only send readings for its own truck, and tenant scoping is applied to every query.
5. **Request integrity:**
   - Changes made with a browser cookie need the `X-Coldline-Request: browser` CSRF header.
   - Webhooks are HMAC-signed with a timestamp and do not follow redirects.
   - Responses carry `no-store` and `nosniff` headers.
6. **Secrets:** all secrets come from the environment. No default passwords are committed, and the local demo password file is git-ignored.
7. **Runtime:** the container runs as a non-root user, and `/metrics` can require a token.
8. **Known gaps:**
   - There is no Content-Security-Policy or X-Frame-Options header.
   - There is no general rate limiting beyond login.
   - Both belong at the HTTPS ingress.
   - There is no PostgreSQL row-level security yet.
   - Login throttling and metrics are counted per process.

## 5. SOLID principles

- **S (single responsibility):** each module has one job.
  - `domain` holds the pure detection logic.
  - `storage` handles persistence.
  - `notifications` handles delivery.
  - `identity` verifies OIDC tokens.
  - `observability` handles logs and metrics.
  - `backup` handles backup and restore.
  - `scenarios` is the demo catalogue.
  - In the frontend, controllers fetch data while components only render.
- **O (open/closed):** new tenants, rules, channels, escalation levels and scenarios are added through config or the catalogue, without changing the core.
  - This is only partly true for channel types: adding SMS natively would mean editing `deliver()`. A plugin registry would close that gap.
- **L (Liskov substitution):** the same `Store` contract works for SQLite and PostgreSQL. `OperatorSessions` behaves the same with in-memory or database storage.
- **I (interface segregation):** each endpoint asks only for the dependency it needs (`operator`, `device`, `acting_operator`), and React components take narrow typed props.
- **D (dependency inversion):** collaborators are passed in rather than built inside, so tests can swap them:
  - `create_app` receives the store, worker, OIDC verifier and credentials.
  - `NotificationWorker` receives its HTTP client.
  - `OidcVerifier` receives its key resolver.
  - `Store` receives its token provider.
- **Caveat:** Python here relies on duck typing rather than formal interfaces.

## 6. Database schema (v2)

| Table | Purpose |
|---|---|
| `tenants` | Customer configuration (branding, rules, notification settings) |
| `trucks` | Device binding, current rule, detector state (JSON), late-reading count. Device ID is unique per tenant |
| `readings` | Every received reading with status (accepted, late, …), identity, fingerprint and payload. Unique on (tenant, device, identity) and (tenant, truck, event time) |
| `incidents` | Lifecycle, qualification time, and JSON with evidence summary, rule snapshot and timestamps |
| `opening_alerts` | Exactly one opening event per incident |
| `incident_events` | Append-only timeline: opened, recovered, acknowledged, escalated, notification retry |
| `incident_acknowledgements` | At most one per incident: who, when, note |
| `notification_outbox` | Delivery queue: status, attempts, next attempt, lease, error, payload. Unique per (incident, event, channel) |
| `operator_sessions` | Hashed session tokens with expiry, shared across replicas |
| `demo_scenarios` | Simulation runs and their status |
| `schema_meta` | Schema version |

Indexes cover incident lists by lifecycle and time, evidence lookups, due outbox rows, timelines, session expiry and demo runs.

**Covered:** telemetry, detection state, incidents, audit, acknowledgement, delivery, sessions and demo runs.

**Not covered:** users and RBAC tables (users live in config, environment or the IdP), device registry history, retention and archive, and an admin audit of configuration changes.

## 7. Real-time handling today, and with real devices

- **Ingestion is push-based and synchronous:** a device or gateway sends `POST /api/v1/readings` with its device key. Detection runs inside that request's transaction, so the incident opens as soon as the qualifying reading arrives.
- **Notifications:** the worker polls the outbox every 2 s and delivers webhooks.
- **Dashboard:** RTK Query polls every 15 s, or 5 s in live demo mode, and also refreshes on window focus and reconnect. There is no WebSocket or SSE yet.
- **Real devices today:** any gateway that can make an HTTPS POST works as-is. It should keep readings while offline and resend them later; idempotency makes retries safe, and late readings are recorded but don't rewrite past decisions.
- **Time:** devices need NTP-synced clocks. Readings more than 5 minutes in the future are rejected.

## 8. Caching

- **Frontend:** the RTK Query cache de-duplicates requests, refreshes on a timer, and invalidates by tag (`Incident`, `Demo`) after a change. It is cleared on sign-out.
- **Static assets:** the Next.js export uses content-hashed files that browsers can cache indefinitely.
- **API:** responses are deliberately `Cache-Control: no-store`, because alert data must be fresh and is tenant-sensitive.
- **Backend:** there is no server-side cache (no Redis). Indexed database reads are enough at this scale; tenant config and the OIDC public keys (JWKS) are held in memory.

## 9. Enhancements for a real, device-connected product

1. **Device connectivity:**
   - MQTT broker or Azure IoT Hub / AWS IoT Core ingestion.
   - Per-device X.509 certificates or mutual TLS.
   - A device provisioning service and key rotation.
   - Firmware and configuration twins.
2. **Device health alerts:** "no data for N minutes", low battery, sensor fault and implausible values, each as its own incident type separate from temperature.
3. **Real-time UI:** server-sent events or WebSockets (or Azure SignalR) to push incident changes instead of polling, plus mobile push notifications.
4. **Native channels:** SMS, email, Teams, PagerDuty and Opsgenie through a channel plugin registry; quiet hours and on-call rotas; acknowledgement from the notification itself.
5. **Domain:**
   - Low-temperature (freezing) alerts.
   - Multiple sensors per truck, with a rule for combining them.
   - Product-specific limits and cumulative exposure (mean kinetic temperature).
   - Trip, shipment and GPS context.
   - Maintenance and defrost mode.
   - A policy for how late readings may arrive.
6. **Platform:**
   - A tenant admin portal and audited configuration changes.
   - RBAC tables, SCIM user provisioning and PostgreSQL row-level security.
   - Rate limiting and WAF at the ingress.
   - Data retention, archival and residency controls.
   - Compliance reporting (GDP, 21 CFR Part 11 audit trails).
7. **Operations:**
   - OpenTelemetry tracing and SLO dashboards.
   - Infrastructure as code (Bicep or Terraform).
   - Blue/green deployment.
   - Load and chaos testing, plus restore drills in CI.

## 10. Performance improvements

- **Database:**
  - Store timestamps as `timestamptz` instead of ISO strings.
  - Partition `readings` by time, or move it to TimescaleDB.
  - Add a retention or roll-up job.
  - Pool connections with PgBouncer.
  - Add covering indexes for dashboard queries.
- **Ingestion:**
  - Process each batch in a single transaction per truck instead of one per reading.
  - At high volume, put a queue (Event Hubs or Kafka) in front, partitioned by truck so ordering is preserved.
  - Run several Uvicorn workers or replicas; the CLI currently runs one.
- **Worker:** use PostgreSQL `LISTEN/NOTIFY` to wake the worker instead of polling every 2 s; send deliveries in parallel; reuse HTTP connections.
- **Reads:**
  - Build a fleet-summary read model updated during ingest.
  - Add ETags or conditional GETs for polling.
  - Compress responses with gzip or brotli.
  - Use pagination for large fleets; the cap is 1,000 trucks per tenant today.
- **Frontend:**
  - Push updates with SSE instead of polling.
  - Virtualise long lists and downsample chart points.
  - Lazy-load dialogs.
  - Memoise selectors.
- **Measure first:** add load tests (k6 or Locust) and track p95 ingest latency, outbox delay and the `/metrics` histograms.
