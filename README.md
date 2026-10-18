# Coldline · Cold-chain alerting

A working multi-customer foundation for the Nimbus Freight FDE case study: deterministic detection, tenant-scoped API, durable incident state, explainable replay, configurable customer rules, and a React operations dashboard.

**Actual supplied-dataset result:** 54 readings → **2 opening incidents**, T-01 and T-05. Both start at 08:10 UTC, qualify at 08:20, and recover at 08:50 on July 20, 2026. T-04's missing interval breaks continuity; T-02 is a brief spike; T-03 stays normal. See [exported evidence](examples/supplied-dataset-result.json) and [solution design](SOLUTION_DESIGN.md).

## Quick start (PowerShell, from repository root)

**Already set up? Start both frontend and backend with one command:**

```powershell
.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:3000** and sign in with the printed **Nimbus Freight username and password**. The launcher starts the seeded demo API and Next.js development server, waits for both to become ready, and connects the API proxy automatically. It uses the project-local Node 24 runtime when available, otherwise Node 24+ on PATH. Press **Ctrl+C** in the same terminal to stop both services and their workers. Existing `dev.db` data is preserved; demo credentials are regenerated at each launch.

Optional ports/database: `.venv\Scripts\python.exe run.py --frontend-port 3001 --backend-port 8001 --db another-demo.db`. The script reports occupied ports or missing dependencies instead of stopping unrelated processes or installing packages automatically. On macOS/Linux use `.venv/bin/python run.py`.

**First-time setup or production-style static demo:**

Prerequisites: Python 3.11+ (verified with 3.12), **Node.js 24+**, npm, and package-registry access. Python-only replay and API do not require Node. The frontend uses Next.js 16 App Router, React 19, Redux Toolkit and RTK Query; see [frontend architecture](frontend/ARCHITECTURE.md). The starter files are preserved; the safe loader is reused, while its cadence-based detector is replaced.

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

This workspace also has a project-local Node 24 runtime because the installed system Node is 18. To use it without changing your machine's installation, run the following from the repository root (workspace-specific paths):

```powershell
$frontendNode = (Resolve-Path .runtime/node/node_modules/node/bin/node.exe).Path
$frontendNpm = 'C:/Program Files/nodejs/node_modules/npm/bin/npm-cli.js'
$env:Path = (Split-Path $frontendNode) + ';' + $env:Path
cd frontend
& $frontendNode $frontendNpm run dev
```

Replace `dev` with `build`, `test`, `lint`, or `typecheck` for other commands. The `.runtime` directory is ignored and is not part of the repository; other machines should install Node 24+ and use standard `npm` commands.

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
| `COLDCHAIN_DB` | SQLite file; CLI sets it from `--db` (default `coldchain.db`) |
| `COLDCHAIN_CONFIG` | Customer config file; CLI sets it from `--config` |
| `COLDCHAIN_CREDENTIALS` | JSON map from secret key to authorized principal; required for `serve` |
| `DEVICE_KEY` | Simulator's device key; choose another variable with `--key-env` |
| `ANTHROPIC_API_KEY` | Optional: Claude SDK API key (activates live Claude 3.5 Sonnet analysis) |
| `ANTHROPIC_MODEL` | Optional: Claude model name (default: `claude-3-5-sonnet-20241022`) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Optional: Google Gemini API key (activates live Gemini 2.5 Flash analysis) |
| `GEMINI_MODEL` | Optional: Gemini model name (default: `gemini-2.5-flash`) |
| `AI_PROVIDER` | Optional: AI provider selection (`auto`, `gemini`, `anthropic`, or `cognitive_simulation`) |
| `COLDCHAIN_DEMO_PASSWORD` | Optional: Fixed browser password for demo/Docker logins (default in Docker: `nimbus123`) |

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

The API fails startup without credentials. There is no default production password. Run one worker/instance, bind locally by default, and terminate TLS at an authenticated deployment boundary for non-local access. Do not put real credentials in source control. The local key mapping is intentionally not enterprise identity management.

## HTTP contract

`X-API-Key` authenticates every `/api/v1/*` route. Operators can read; device keys can ingest only their registered stream. A tenant field cannot select another customer. `GET /health` is unauthenticated liveness; interactive schema is at `/docs`.

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
- `GET /api/v1/incidents/{id}?limit=100&offset=0`: explanation, original rule and paginated accepted evidence. Other tenants' IDs return 404. Late readings are excluded from decision evidence.

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
- **Concurrency:** database-level `BEGIN IMMEDIATE` serializes writers before reading state; unique constraints enforce identity. The first scaling bottleneck is write serialization.
- **Customer rules:** configuration changes apply to new candidates; snapshots preserve historical meaning. Multiple sensors need sensor-scoped streams plus a business-approved aggregation policy.

## Scope and limitations

Implemented: deterministic domain engine; SQLite/SQLAlchemy persistence and schema versioning; authenticated ingestion/read APIs; offline replay and JSON export; HTTP simulator; tenant and per-truck rules; dashboard; tests. The opening event is persisted, but **no email, SMS, webhook or MQTT delivery is implemented**. No speculative root-cause claims or LLM dependencies.

This is a local product foundation, not a production-readiness claim. SQLite requires local durable storage and one supported application instance. Schema v1 supports new database creation and refuses unknown versions; future upgrades need explicit migration steps. Demo credentials lack enterprise expiry, rotation UI and user audit. Production still needs TLS deployment, request-rate controls, backups/restore drills, observability, retention, secret management, OIDC and security review. HTTP payload size is bounded; protect slow clients with gateway timeouts. Batch acknowledgements may partially commit on infrastructure failure; retry using unchanged identities. There is no automatic late-data repair, low-temperature alerting, maintenance mode, acknowledgement workflow or customer onboarding portal.

Next three priorities: (1) customer validation of rules, workflow and deployment requirements; (2) notification outbox plus delivery monitoring and device/telemetry health; (3) production identity, audited provisioning, backups and measured PostgreSQL migration. See the design for shared versus dedicated deployments and a labelled workload estimate.

## Verification record

- `python -m pytest -q`: **23 passed**, including domain boundaries, configuration snapshots, restart continuity, concurrent duplicates, transaction rollback, tenant/device isolation, actual dataset replay and a real TCP server/simulator test.
- `python -m pip check`: no broken requirements. `requirements.txt` locks the verified environment, including transitive dependencies.
- `npm run build`: Next.js production static export passed; its HTML and generated assets were served through the real backend HTTP smoke test. Frontend component/store tests and lint/type checks are described in [frontend architecture](frontend/ARCHITECTURE.md).
- `npm test`: **8 frontend tests passed**, including customer switching under React Strict Mode, cache isolation, invalid login, API retry and telemetry gap rendering. `npm run typecheck` and `npm run lint` passed.
- Next development smoke check: rendered login HTML, proxied an unauthenticated API request as 401, and forwarded an authenticated request to the correct customer. `npm audit --omit=dev` reported zero vulnerabilities.
- The migration's full npm audit reports five development-only entries for an unpatched `braces` issue in Next's lint dependency chain. See the architecture document for the compatibility constraint and why the suggested forced downgrade is not appropriate.
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

The simulator uses temperatures from `starter_kit/data/sensor_readings.json`, stamps each observation with the current UTC time and sends it through the device-authenticated HTTP ingestion API every 10 seconds. The dashboard explicitly labels this **Live simulation**: these are synthetic observations, not connected truck sensors. The actual detection, persisted incident, evidence and recovery paths run normally. No email/SMS delivery is implied.

The isolated `config/live-demo.json` profile triggers after 30 seconds above 8 C, requires 20 seconds of normal readings for recovery and resets continuity after a gap above 15 seconds. T-01 and T-05 should open incidents roughly 50?60 seconds after streaming starts and recover around 110?120 seconds. Dashboard polling can add 15 seconds. The sequence repeats. T-04 demonstrates a telemetry gap that breaks continuity. Production rules in `config/customers.json` are unchanged.

Live mode uses `live-demo.db`; historical mode (`run.py` without `--live`) uses `dev.db` and preserves the original timestamps. Both preserve existing data. For a clean presentation use `--live --db presentation-01.db` with a new filename. Ctrl+C stops both servers and the simulator. After building the frontend, a backend-only alternative is `python -m backend.cli live-demo` on port 8000.

Operator API keys remain available for scripts and API compatibility; browser users now enter a username and password. Device keys authorize sensor ingestion only. For non-demo `serve`, configure `COLDCHAIN_USERS` as a JSON mapping of username to `{ "tenant": "nimbus", "password_hash": "..." }`; generate each salted hash with `backend.auth.hash_password`. Never commit passwords or credential environment files. Existing `COLDCHAIN_CREDENTIALS` device configuration remains supported.

Sessions expire after eight hours, are revoked on sign-out, and are lost on server restart. Reloading the page currently displays the login screen again. Authentication is a single-instance MVP with login throttling, not an enterprise identity provider: production deployment should integrate OIDC/SSO and managed user provisioning. Set `COLDCHAIN_SECURE_COOKIES=1` when serving over HTTPS; local HTTP demos leave it unset.

## Multi-Provider AI Engine: Google Gemini API & Anthropic Claude SDK

Coldline supports both **Google Gemini API** (via the modern `google-genai` SDK) and **Anthropic Claude SDK** (`anthropic`).

### 1. Capabilities
- **Real Alert Qualification**: Evaluates thermal velocity ($dT/dt$), rate of rise, and cargo thermal inertia to distinguish genuine refrigeration failures from benign events (door opening spikes, evaporator defrost cycles).
- **Thermodynamic Continuity Across Telemetry Gaps**: Solves the edge case in Truck T-04 where a 10-minute connectivity blackout resets rigid rule counters even though physical heat transfer persisted unabated throughout the silence.
- **Predictive Sub-Threshold Drift**: Warns dispatchers about subtle warming trends (e.g. Truck T-03 creeping from 5.8°C to 7.0°C) before violation occurs.
- **Automated Incident Triage & Forensic Analysis**: Calculates degree-minutes above threshold, assesses cargo stability budgets, and provides an actionable Operations SOP Checklist.
- **Driver Dispatch Communication Script**: Automatically drafts clear, urgent, professional SMS/radio messages ready for dispatchers to copy with one click.
- **Interactive Operations Copilot**: Slide-out modal allowing operators to converse with Gemini or Claude about live fleet telemetry, gap risks, and compliance guidelines.

### 2. Multi-Provider Selection & Fallback
- **Google Gemini**: Set `$env:GEMINI_API_KEY="AIza..."` or `$env:GOOGLE_API_KEY="AIza..."` (default model: `gemini-2.5-flash`).
- **Anthropic Claude**: Set `$env:ANTHROPIC_API_KEY="sk-ant-..."` (default model: `claude-3-5-sonnet-20241022`).
- **Provider Switching**: Use `$env:AI_PROVIDER="gemini"` or `$env:AI_PROVIDER="anthropic"` (or leave as `"auto"` to select whichever key is active).
- **Cognitive Simulation Fallback**: If neither key is configured, Coldline seamlessly runs an embedded deterministic physics engine that computes degree-minutes, gap interpolation, and MKT with 100% offline uptime and zero crashes.

---

## Running with Docker Desktop

A multi-stage [Dockerfile](Dockerfile) and [docker-compose.yml](docker-compose.yml) are included for one-click launch in **Docker Desktop**.

### 1. Start with Docker Compose (Recommended)

From the project root:

```powershell
# (Optional) pass your AI key into the container:
$env:GEMINI_API_KEY = "your-gemini-key"
# or: $env:ANTHROPIC_API_KEY = "your-claude-key"

# Build and start container
docker compose up --build
```

### 2. Access the Application:
- **Dashboard:** [http://localhost:8000](http://localhost:8000)
- **API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Login Credentials:**
  - **Username:** `nimbus.demo`
  - **Password:** `nimbus123` (configured via `COLDCHAIN_DEMO_PASSWORD` in `docker-compose.yml`)

### 3. Stop the Container:
```powershell
docker compose down
```
Data is persisted in the `./data` directory on your host machine.
