# Coldline · Cold-chain alerting

A working multi-customer foundation for the Nimbus Freight FDE case study: deterministic detection, tenant-scoped API, durable incident state, explainable replay, configurable customer rules, and a React operations dashboard.

**Actual supplied-dataset result:** 54 readings → **2 opening incidents**, T-01 and T-05. Both start at 08:10 UTC, qualify at 08:20, and recover at 08:50 on July 20, 2026. T-04's missing interval breaks continuity; T-02 is a brief spike; T-03 stays normal. See [exported evidence](examples/supplied-dataset-result.json) and [solution design](SOLUTION_DESIGN.md).

## Quick start (PowerShell, from repository root)

**Already set up? Start both frontend and backend with one command:**

```powershell
.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:3000** and sign in with the printed **Nimbus Freight username and password**. The launcher starts the seeded demo API and Next.js development server, waits for both to become ready, and connects the API proxy automatically. It uses the project-local Node runtime when available, otherwise Node 24.15+ on PATH. Press **Ctrl+C** in the same terminal to stop both services and their workers. Existing `dev.db` data is preserved; demo credentials are regenerated at each launch.

Optional ports/database: `.venv\Scripts\python.exe run.py --frontend-port 3001 --backend-port 8001 --db another-demo.db`. The script reports occupied ports or missing dependencies instead of stopping unrelated processes or installing packages automatically. On macOS/Linux use `.venv/bin/python run.py`.

**First-time setup or production-style static demo:**

Prerequisites: Python 3.11+ (verified with 3.12), **Node.js 24.15+**, npm, and package-registry access. Python-only replay and API do not require Node. The frontend uses Next.js 16 App Router, React 19, Redux Toolkit and RTK Query; see [frontend architecture](frontend/ARCHITECTURE.md). The starter files are preserved; the safe loader is reused, while its cadence-based detector is replaced.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.venv/Scripts/python.exe -m backend.cli demo --db demo.db --assume-utc
```

Open **http://127.0.0.1:8000** and enter the printed **Nimbus Freight username and password**. Demo passwords are randomly generated per start and stored as salted scrypt hashes in the server environment. Browser sessions use HTTP-only SameSite cookies. Demo runs replay before serving; restarting against an identical replay database deduplicates it. It does not erase the database. Use a new `--db` filename for a fresh scenario or rule comparison. Do not mix a live ingestion database with replay: late/conflicting results fail the replay command and require a fresh database.

On macOS/Linux use `.venv/bin/python` in place of `.venv/Scripts/python.exe`. If `python` is not on PATH, use your installed Python 3.11+ executable to create the environment. If your organization intercepts TLS, configure its trusted CA; do not disable certificate validation. In this workspace, Python installation used `--use-feature=truststore` with the Windows certificate store.

`npm run build` generates a Next.js static export in `frontend/out`, which FastAPI serves at `/`. Without that build, the API still works at `/docs`; `/` has no dashboard. Old Vite `dist` assets are no longer served. No separate Node production server is needed for this deployment mode.

For frontend development, keep the backend running and run `npm run dev` in `frontend`. Open **http://127.0.0.1:3000**; Next.js proxies `/api` to port 8000. Set `BACKEND_ORIGIN` before starting development if your backend uses a different address. Run the backend from the repository root. No external fonts, paid assets or external AI services are required.

Replace `dev` with `build`, `test`, `lint`, or `typecheck` for other commands. `run.py` can use a supported project-local Node runtime or a compatible version on `PATH`.

## Replay and tests

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m backend.cli replay --db replay.db --assume-utc --output data/replay.json
```

Replay prints a table and explanatory sentences and exports complete incident IDs, rules, timestamps, maxima, counts and fleet state as JSON. The explicit UTC assumption is required because the supplied dataset lacks timezone offsets. JSON's `reference_time` is 2026-07-20 08:50 UTC. The dashboard evaluates freshness against the current server clock and labels these old observations as historical.

```text
Truck  Start (UTC)  Qualified  Lifecycle  Peak C  Evidence  Recovery
T-01   08:10        08:20      recovered     9.6         9 08:50
T-05   08:10        08:20      recovered     9.6         9 08:50
```

Each incident has three opening observations and nine total evidence observations, including recovery. The IDs are deterministic for a tenant/truck/start/rule. Processing times reflect the actual replay run and therefore vary across fresh databases; event-time decisions do not. Rerunning identical input against the same database reports 54 duplicates without new incidents or opening events. `examples/supplied-dataset-result.json` is the actual implementation output, not a hand-written fixture.

## Customer customization and credentials

Edit [config/customers.json](config/customers.json), or select another file using `--config`. It contains Nimbus and Alpine, including the same truck ID in separate tenants. Names, accent colors, devices and operational rules vary per customer. A truck's optional `rule` object overrides the tenant rule. Rules have `threshold_c`, `sustained_minutes`, `max_gap_minutes`, and `recovery_minutes`. All durations are positive minutes. Changes load on service startup; active candidates/incidents retain their original rule snapshot. Unknown fields and duplicate truck/device identities are rejected. Limits: 100 tenants and 1,000 trucks per tenant in this MVP; the fleet endpoint returns that bounded registered fleet.

Provisioning creates/updates entries and does not delete omitted historical records. Remove or reassign devices only through a reviewed administrative migration. Keep customer configuration in deployment-specific version control and separate from credentials. For an isolated deployment, provide a config containing only that customer. Adding a second customer does not require a code fork.

| Environment variable | Purpose |
|---|---|
| `COLDCHAIN_DATABASE_URL` | SQLite path or SQLAlchemy URL, e.g. `postgresql+psycopg://user@host/coldline`; CLI sets it from `--db` (legacy `COLDCHAIN_DB` is still read) |
| `COLDCHAIN_DB_AUTH` | `azure-managed-identity` fetches an Entra token per PostgreSQL connection (install `azure-identity`) |
| `COLDCHAIN_DB_POOL_SIZE` | PostgreSQL connection pool size per process (default 5) |
| `COLDCHAIN_NOTIFICATION_WORKER` | `1` (default) runs the delivery/escalation worker inside the API; set `0` on API replicas when `backend.cli worker` runs separately |
| `COLDCHAIN_OIDC_ISSUER`, `COLDCHAIN_OIDC_AUDIENCE`, `COLDCHAIN_OIDC_JWKS_URL` | Enable OIDC bearer tokens (RS256/ES256) |
| `COLDCHAIN_OIDC_TENANT_CLAIM`, `COLDCHAIN_OIDC_ROLES_CLAIM`, `COLDCHAIN_OIDC_OPERATOR_ROLE` | Claim mapping (defaults `coldline_tenant`, `roles`, `coldline.operator`) |
| `COLDCHAIN_METRICS_TOKEN` | Optional bearer token required by `/metrics` |
| `COLDCHAIN_LOG_FORMAT`, `COLDCHAIN_LOG_LEVEL` | `json` or `text` (default); log level (default `INFO`) |
| *channel `secret_env`* | Each webhook channel names the env variable holding its HMAC signing secret |
| `COLDCHAIN_CONFIG` | Customer config file; CLI sets it from `--config` |
| `COLDCHAIN_CREDENTIALS` | JSON map from secret key to authorized principal; useful for device and API-key clients |
| `COLDCHAIN_USERS` | JSON map of operator usernames to tenant and scrypt password hash; enables browser login |
| `DEVICE_KEY` | Simulator's device key; choose another variable with `--key-env` |
| `COLDCHAIN_DEMO_PASSWORD` | Optional fixed password for local `demo`/`live-demo` commands only; never set a production default |
| `COLDCHAIN_SECURE_COOKIES` | Set to `1` behind HTTPS; Compose overrides to `0` for localhost-only HTTP development |

Example credential shape, with **placeholder secrets to replace**:

```json
{
  "replace-with-random-operator-secret": {"tenant": "nimbus", "role": "operator"},
  "replace-with-random-device-secret": {
    "tenant": "nimbus", "role": "device", "truck_id": "T-01", "device_id": "sensor-T-01"
  }
}
```

Supply that JSON through `COLDCHAIN_CREDENTIALS`, then run:

```powershell
.venv/Scripts/python.exe -m backend.cli serve --db live.db
```

The API fails startup without at least one operator account, API credential or OIDC configuration. With SQLite run one instance; with PostgreSQL run several replicas (see [Production operations](#production-operations)). Bind locally by default, and terminate TLS at an authenticated deployment boundary for non-local access. Do not put real credentials in source control. The local key mapping is intentionally not enterprise identity management.

## HTTP contract

`X-API-Key`, an OIDC `Authorization: Bearer` token or a browser session cookie authenticates every `/api/v1/*` route. Operators can read and acknowledge; device keys can ingest only their registered stream. A tenant field cannot select another customer. Cookie-authenticated mutations also require `X-Coldline-Request: browser` (CSRF defence). `GET /health` is unauthenticated liveness, `GET /ready` checks the database and worker, `GET /metrics` serves Prometheus text; every response echoes `X-Request-ID`. Interactive schema is at `/docs`.

```http
POST /api/v1/readings
Content-Type: application/json
X-API-Key: <device key>

{
  "readings": [{
    "event_id": "T-01-20260720-081000",
    "truck_id": "T-01",
    "device_id": "sensor-T-01",
    "timestamp": "2026-07-20T08:10:00Z",
    "temperature_c": 8.5,
    "humidity_pct": 58,
    "unit": "C"
  }]
}
```

The envelope accepts 1–100 readings; a single reading uses a one-element list. Maximum request body: 256 KiB. Each reading is independently validated and committed in received order; this is not an atomic batch. HTTP 200 contains per-item outcomes: `accepted`, `duplicate`, `late`, `invalid`, `conflict`, or `unauthorized`. A retry after a partial batch is safe when identities are unchanged. Do not treat HTTP 200 alone as acceptance: inspect `results` and `counts`.

```json
{
  "results": [{"status": "accepted", "reading_id": 1, "incident_id": null}],
  "counts": {"accepted": 1, "duplicate": 0, "late": 0, "invalid": 0, "conflict": 0, "unauthorized": 0}
}
```

Malformed envelopes return 422; missing/invalid credentials 401; wrong credential role 403; oversized bodies 413; busy/unavailable database 503 with retry advice. Validation failures do not persist rows. Future timestamps more than five minutes ahead are invalid. Timestamps require offsets, finite temperatures and Celsius units. Exact duplicates preserve all original side effects. Same device event ID with changed content or distinct readings at an occupied stream timestamp conflict. Without an event ID, identity is a SHA-256 hash of canonical source fields (including optional humidity). Live late events persist with no retroactive decision.

Read routes:

- `GET /api/v1/trucks`: last accepted temperature/time, detector status, independent freshness, rules and late counts. `normal` is a detector state, not a cargo-safety assertion; always read it with freshness.
- `GET /api/v1/incidents?limit=20&offset=0&lifecycle=open&truck_id=T-01`: tenant-scoped list. Filters optional; limit 1–100, offset 0–100000.
- `GET /api/v1/incidents/{id}?limit=100&offset=0`: explanation, original rule, paginated accepted evidence, `acknowledgement`, audit `timeline` and per-channel `notifications`. Other tenants' IDs return 404. Late readings are excluded from decision evidence.

Response routes (operator):

- `POST /api/v1/incidents/{id}/acknowledge` with optional `{"note": "..."}`: records actor and time, stops escalation, is idempotent (`created: false` on repeat). It does not close the incident; only observed recovery does.
- `GET /api/v1/notifications?status=dead`: delivery outbox with attempts and last error. `POST /api/v1/notifications/{id}/retry` re-queues a dead letter.
- `GET|POST /api/v1/demo/scenarios`, `PATCH /api/v1/demo/scenarios/{id}`: live-simulation tenants only (404 otherwise); see [simulating alerts](#simulating-genuine-and-non-genuine-alerts).

The incident keeps `qualifying_supported_seconds`, cumulative `supported_warm_seconds`, `evidence_count`, `opening_evidence_count`, `telemetry_gap_count`, `observed_max_c` and distinct lifecycle timestamps. Supported warm intervals count only warm-to-warm observation pairs within the gap limit. Incident age, if required, is the elapsed time since start; it is not supported exposure time.

## Five-minute panel demo

1. Run the demo, log in with Nimbus's username and password, and point out the historical telemetry banner. Five registered trucks, two recovered incidents, no open incidents; old readings are stale today.
2. Open T-01's incident. Follow 08:10 start → 08:20 qualification → 08:45 recovery candidate → 08:50 confirmed recovery. The chart and table show the evidence and snapshot.
3. Explain T-04's gap and T-05's shuffled source. Rerun replay to show duplicate handling.
4. Sign out and use Alpine's username and password: a different rule and fleet, with no access to Nimbus's incidents.
5. For live ingestion, start `serve --db simulator.db` with your configured keys, set `$env:DEVICE_KEY`, then run `.venv/Scripts/python.exe -m backend.simulator`. The scenario posts normal readings, a spike, sustained warmth, a gap during attempted recovery, recovery, a duplicate and a late reading through the real HTTP endpoint. It intentionally leaves old/stale telemetry relative to now. Use a new database for each independently comparable scenario.

Panel answers:

- **Alert fatigue:** only observed sustained warmth opens; one durable opening event per unresolved incident.
- **Gaps:** missing evidence cannot prove recovery; freshness and lifecycle are independent.
- **Offline versus live:** replay sorts; live late data is retained without retroactive corrections.
- **Restart:** detector state and original rule survive in the same database transaction as evidence.
- **Concurrency:** state is locked before it is read (`BEGIN IMMEDIATE` on SQLite, per-truck `FOR UPDATE` on PostgreSQL); unique constraints enforce identity. SQLite's single writer is the first bottleneck; PostgreSQL removes it.
- **Notification:** the outbox row commits with the incident; a worker delivers at-least-once with signed webhooks, retries, dead-letter and escalation until acknowledged.
- **Customer rules:** configuration changes apply to new candidates; snapshots preserve historical meaning. Multiple sensors need sensor-scoped streams plus a business-approved aggregation policy.

## Scope and limitations

Implemented: deterministic domain engine; SQLite or PostgreSQL persistence with schema v2 migration; authenticated ingestion/read APIs; OIDC bearer verification; database-backed sessions; transactional notification outbox with log, HMAC-signed webhook and Slack-format channels, retries, dead-letter and per-tenant escalation; incident acknowledgement and audit timeline; JSON logs, request IDs, Prometheus metrics and readiness; SQLite backup/verify/restore; offline replay and JSON export; HTTP simulator with genuine/non-genuine scenario injection; tenant and per-truck rules; dashboard; tests. No speculative root-cause claims or LLM dependencies. Email, SMS and pager integrations are reached through webhooks (for example a customer's on-call tool), not native connectors.

Not verified in this repository: PostgreSQL, multi-replica and Docker deployments, and OIDC against a real IdP are implemented but automated tests run on SQLite with locally signed tokens. Run the suite against staging infrastructure before go-live. Login throttling and metric counters are per process. Still to deliver: rate limiting at the ingress, retention policy, quiet hours, a customer onboarding/admin portal, low-temperature alerting, maintenance mode and automatic late-data repair. Batch acknowledgements may partially commit on infrastructure failure; retry using unchanged identities.

Next three priorities: (1) customer decisions on channels, escalation timings, acknowledgement ownership and rules; (2) staging validation on managed PostgreSQL with the customer's IdP and restore drill; (3) device/telemetry health alerts and an audited provisioning workflow. See the design for shared versus dedicated deployments.

## Verification record

- `python -m pytest -q`: **50 passed, 1 skipped** (the launcher integration is skipped when the available Node.js version is below 24.15), including outbox atomicity, signed webhook delivery, retry/backoff/dead-letter, escalation until acknowledgement, sessions shared across two app instances, OIDC verification, backup/restore, v1?v2 migration, scenario expectations against every configured rule, domain boundaries, configuration snapshots, restart continuity, concurrent duplicates, transaction rollback, tenant/device isolation, actual dataset replay and a real TCP server/simulator test.
- `python -m pip check`: no broken requirements. `requirements.txt` locks the verified environment, including transitive dependencies.
- `npm run build`: Next.js production static export passed; its HTML and generated assets were served through the real backend HTTP smoke test. Frontend component/store tests and lint/type checks are described in [frontend architecture](frontend/ARCHITECTURE.md).
- `npm test`: **14 frontend tests passed**, including incident acknowledgement and the demo scenario panel, including customer switching under React Strict Mode, cache isolation, invalid login, API retry and telemetry gap rendering. `npm run typecheck` and `npm run lint` passed.
- Next development smoke check: rendered login HTML, proxied an unauthenticated API request as 401, and forwarded an authenticated request to the correct customer. `npm audit --omit=dev` reported zero vulnerabilities.
- The full npm audit reports five development-only entries for an unpatched `braces` issue reached only through `eslint-config-next`; no fixed upstream release exists. `npm run audit:prod` reports zero. This is a documented accepted risk (see the design's supply-chain note).
- Live smoke check: `live-demo --baseline steady` with a compressor-failure and a door-open-spike scenario injected through the API produced exactly one incident (the genuine one), delivered `incident.opened` and `incident.recovered` through the outbox, and `/ready` reported database and worker `ok`.
- Real HTTP checks served the built HTML/assets and exercised the simulator: 10 accepted, 1 duplicate, 1 late reading, one recovered incident with one telemetry gap.
- Browser visual/interaction verification was **not run**: no browser was connected in the implementation environment. The dashboard still needs a human visual pass, especially on mobile, before presentation.
- One upstream test-client deprecation warning remains: Starlette recommends migrating its test client from `httpx` to `httpx2`. It does not fail the tests.

Effort guidance: this repository implements the core take-home plus a compact UI and simulator. The brief's 3–4 hours is a target, not a measured production estimate; no full engineering time log is claimed. Additional commercial hardening should be planned separately with agreed acceptance criteria.


## Current-time alert demo and browser login

Run both services and a continuous sensor simulator with:

```powershell
.venv/Scripts/python.exe run.py --live
```

Open http://127.0.0.1:3000. Sign in as **nimbus.demo** with the password printed in the terminal. Credentials are regenerated on each launch. Use `alpine.demo` and its printed password to demonstrate customer isolation.

The simulator uses temperatures from `starter_kit/data/sensor_readings.json`, stamps each observation with the current UTC time and sends it through the device-authenticated HTTP ingestion API every 10 seconds. The dashboard explicitly labels this **Live simulation**: these are synthetic observations, not connected truck sensors. The actual detection, persisted incident, evidence and recovery paths run normally. Notifications go to the log channel in this profile; escalation fires 1 minute after opening if the incident is unacknowledged.

The isolated `config/live-demo.json` profile triggers after 30 seconds above 8 C, requires 20 seconds of normal readings for recovery and resets continuity after a gap above 15 seconds. T-01 and T-05 should open incidents roughly 50?60 seconds after streaming starts and recover around 110?120 seconds. The live dashboard polls every 5 seconds. The sequence repeats. T-04 demonstrates a telemetry gap that breaks continuity. Production rules in `config/customers.json` are unchanged.

Live mode uses `live-demo.db`; historical mode (`run.py` without `--live`) uses `dev.db` and preserves the original timestamps. Both preserve existing data. For a clean presentation use `--live --db presentation-01.db` with a new filename. Ctrl+C stops both servers and the simulator. After building the frontend, a backend-only alternative is `python -m backend.cli live-demo` on port 8000.

Operator API keys remain available for scripts and API compatibility; browser users now enter a username and password. Device keys authorize sensor ingestion only. For non-demo `serve`, configure `COLDCHAIN_USERS` as a JSON mapping of username to `{ "tenant": "nimbus", "password_hash": "..." }`; generate each salted hash with `backend.auth.hash_password`. Never commit passwords or credential environment files. Existing `COLDCHAIN_CREDENTIALS` device configuration remains supported.

Sessions expire after eight hours, are revoked on sign-out, and are stored (hashed) in the database so they survive restarts and work across replicas. Reloading the page currently displays the login screen again. Local accounts suit pilots; production should use OIDC (`COLDCHAIN_OIDC_*`) with the customer's IdP and managed user provisioning. Set `COLDCHAIN_SECURE_COOKIES=1` when serving over HTTPS; local HTTP demos leave it unset.

### Simulating genuine and non-genuine alerts

For a controlled presentation start with a steady fleet so that only injected patterns cross the threshold:

```powershell
.venv\Scripts\python.exe run.py --live --baseline steady --db presentation-01.db
```

The dashboard shows a **Simulate a real-time pattern** panel. Choose a truck, then a **genuine excursion** (compressor failure, marginal sustained excursion) or a **non-genuine pattern** (door-open spike, single-sample sensor glitch, warm readings broken by a telemetry gap). Each run shows its expected outcome, the incident actually observed and a verdict (*As expected* or *Mismatch ? review*). Patterns are generated from the truck's own rule, take 50?100 seconds, and are disabled while that truck has an open incident or another run. Without `--baseline steady`, seed temperatures keep replaying on the other trucks. Scripts can inject the same patterns:

```powershell
$h = @{ "X-API-Key" = "<printed operator key>" }
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/demo/scenarios -Headers $h -ContentType application/json -Body '{"truck_id":"T-02","scenario":"door_open_spike"}'
```

During the presentation, acknowledge the genuine incident in its dialog to show the audit timeline, notification deliveries and stopped escalation.

## Deterministic operational summaries

The dashboard's fleet summary, incident review and operations assistant are deterministic views over the authenticated tenant's stored data. The legacy `/api/v1/ai/*` route paths remain, but their summaries do not call Anthropic, Google or any other external model. Response semantics are deliberately evidence-based: confidence and cargo/health scores are unavailable (`null`), and condition/category values describe detector or telemetry state. They do not estimate a root cause, cargo spoilage, product stability, or probability of harm. A gap between warm readings is surfaced as unknown continuity, not interpolated exposure. Dispatch message templates are drafts and must be checked against the customer's approved procedure.

Alert delivery is handled by the notification outbox, not by these summaries. See [Production operations](#production-operations).

## Production operations

**Notifications.** Each tenant's `notifications` block in the customer config declares channels and escalation levels; see [config/customers.production.example.json](config/customers.production.example.json):

```json
"notifications": {
  "channels": [
    {"id": "ops-webhook", "type": "webhook", "url": "https://alerts.example.com/coldline",
     "secret_env": "COLDLINE_WEBHOOK_SECRET_NIMBUS", "events": ["incident.opened", "incident.recovered", "incident.acknowledged"]},
    {"id": "dispatch-slack", "type": "webhook", "format": "slack", "url": "https://hooks.slack.com/services/...", "events": ["incident.opened"]}
  ],
  "escalation": [{"after_minutes": 15, "channels": ["ops-webhook"]}]
}
```

Webhook receivers should verify `X-Coldline-Signature: v1=<hex HMAC-SHA256(secret, timestamp + "." + body)>` with `X-Coldline-Timestamp`, and de-duplicate on `X-Coldline-Delivery` (delivery is at-least-once). Failed deliveries retry with exponential backoff (5 s doubling to 15 min) and dead-letter after 8 attempts or a non-retryable 4xx; monitor `coldline_outbox_dead`.

**Commands.**

```powershell
python -m backend.cli worker                                  # dedicated delivery/escalation worker
python -m backend.cli backup --db coldchain.db                # online SQLite backup + manifest in backups/
python -m backend.cli verify-backup --input backups\coldline-<UTC>.db
python -m backend.cli restore --input backups\coldline-<UTC>.db --db coldchain.db --force
```

PostgreSQL deployments use the provider's point-in-time recovery; the backup command refuses PostgreSQL URLs. Use `COLDCHAIN_LOG_FORMAT=json` in production, scrape `/metrics`, and use `/ready` as the readiness probe.

## Running with Docker Compose

The container starts the configured `serve` command, never the local demo command. There is no default operator password. Create a scrypt hash for a local test account:

```powershell
$passwordHash = .venv\Scripts\python.exe -c "from getpass import getpass; from backend.auth import hash_password; print(hash_password(getpass()))"
$env:COLDCHAIN_USERS = "{`"nimbus.demo`":{`"tenant`":`"nimbus`",`"password_hash`":`"$passwordHash`"}}"
docker compose up --build
```

Browse to **http://127.0.0.1:8000** and log in with username `nimbus.demo` and the password entered above. Compose binds to host loopback only and uses HTTP for local development. For any network-accessible deployment, terminate TLS at a trusted ingress, set `COLDCHAIN_SECURE_COOKIES=1`, provision credentials through a secret manager, and review tenant isolation and backup requirements. `COLDCHAIN_CREDENTIALS` is separately required for device/API-key clients; configure it as an environment secret before connecting sensors.

Stop with `docker compose down`. The named `coldline-data` volume preserves the SQLite database. The image runs as a non-root user, logs JSON and uses `/ready` for its healthcheck.

Multi-instance topology (PostgreSQL, API replicas without in-process workers, one dedicated worker):

```powershell
$env:POSTGRES_PASSWORD = "<strong local password>"
docker compose --profile postgres up --build --scale coldline-api=2
```

API replicas publish on loopback ports 8001?8009; put a load balancer in front of them for real deployments. For Azure, replace the compose database with Azure Database for PostgreSQL, set `COLDCHAIN_DB_AUTH=azure-managed-identity` and omit the password from the URL. The Compose files were not executed in the implementation environment (no Docker available).
