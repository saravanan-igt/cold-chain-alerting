Use this prompt in Copilot Agent mode with the starter repository open. It prioritizes the assessed case study while establishing a practical foundation for a multi-customer product.

Two architectural choices are deliberate: SQLite is suitable for the local MVP but permits only one writer at a time, so scaling needs an explicit database migration plan. The Velvet template should be used only if you provide licensed source files; its React compatibility should be checked before choosing Next.js. Sources: [SQLite documentation](https://www.sqlite.org/wal.html), [Velvet template](https://themeforest.net/item/velvet-react-typescript-dashboard-template/52969641).

Copy and paste:

```text
Act as a senior Forward Deployed Engineer, pragmatic software architect, and hands-on full-stack developer.

Architect and implement a cold-chain alerting application for Nimbus Freight using the starter repository and sensor dataset available in this workspace.

Your output must be working code, meaningful tests, and concise documentation—not just recommendations or an architecture proposal.

OBJECTIVE

Nimbus Freight operates refrigerated trucks carrying temperature-sensitive cargo. Sensors report temperature every few minutes, sometimes with gaps, duplicates, or out-of-order delivery.

The operations team needs to identify sustained temperature excursions without receiving an alert for every warm reading or repeated alerts for one ongoing incident.

Build a solution that can demonstrate:
1. Which trucks experienced a sustained excursion.
2. When each excursion started and became alertable.
3. The evidence and rule that caused the alert.
4. Whether the incident remains active, has recovered, or has uncertain status because telemetry is missing.

This is an FDE take-home with a 3–4 hour implementation budget. A correct, explainable, complete solution takes priority over breadth. Establish clear boundaries for eventual deployment to multiple customers without trying to build the entire SaaS platform now.

WORKING APPROACH

Start by inspecting:
- Repository instructions and existing code.
- The supplied violation-detection utility.
- Dataset schema, timestamp format, units, sampling intervals, truck IDs, and data-quality issues.
- Existing dependency and frontend setup.

Preserve useful starter code. Do not replace the repository unnecessarily.

List the most important customer discovery questions, then document reasonable assumptions and proceed. Ask me only about an ambiguity that genuinely prevents implementation. Never invent findings about files or data you cannot access.

If the starter dataset is absent, explicitly report this and create a clearly labelled synthetic fixture for development. Do not represent synthetic results as results from the supplied dataset.

Create a short implementation plan with acceptance criteria, then implement it. Track scope against the time budget. If time becomes tight, reduce UI scope and optional features before compromising detection correctness, tests, reproducibility, or required documentation.

TECHNOLOGY

Backend:
- Python and FastAPI.
- Pydantic request/response validation.
- SQLAlchemy and SQLite for the local MVP.
- pytest.
- Use a simple migration mechanism appropriate to the repository.

Frontend, if the core deliverables are complete:
- React, TypeScript, SCSS, and React Bootstrap.
- Prefer Next.js if compatible with the existing project or supplied theme.
- Otherwise, use React with Vite and document the decision.
- Do not create two frontend applications.
- Keep alerting logic entirely in the Python backend.

Theme:
- If licensed Velvet React TypeScript Dashboard Template files are present, reuse suitable components and styles.
- Inspect compatibility before integrating.
- If unavailable, build an original, restrained operations dashboard using React Bootstrap and SCSS.
- Do not download paid assets, copy proprietary template code, or block implementation on the theme.

Choose compatible stable dependencies and lock versions using the repository’s package-management conventions.

SCOPE AND PRIORITIES

Required:
1. Deterministic detection engine.
2. Dataset replay command that prints and exports explainable alerts.
3. Persistence of readings and incident state.
4. Minimal FastAPI ingestion and read endpoints.
5. Tests covering rule boundaries and failure cases.
6. SOLUTION_DESIGN.md and README.md.

Next, if time permits:
7. A small dashboard with real backend data.
8. A device simulator that posts readings through the ingestion API.

Future work unless unusually easy:
- MQTT broker integration.
- Email, SMS, or external webhook delivery.
- Enterprise authentication and self-service tenant onboarding.
- Distributed workers and message brokers.
- Advanced analytics and AI summaries.

Do not add Kafka, Kubernetes, microservices, CQRS, or elaborate repository abstractions merely to claim scalability.

ALERTING SEMANTICS

Make the rules explicit before implementing them.

Use these initial demo assumptions unless inspection reveals a strong reason to change them:
- Canonical temperature unit: Celsius.
- Excursion threshold: strictly above 8°C.
- Minimum sustained duration: 10 minutes.
- Maximum supported gap between consecutive readings: 5 minutes.
- Recovery: readings at or below 8°C sustained for 5 minutes, with the same maximum-gap rule.
- These are illustrative customer-configurable operational rules, not validated pharmaceutical or food-safety requirements.

Explain the sampling assumption: consecutive above-threshold readings no more than the maximum gap apart are treated as evidence of a continuous excursion between observations. Actual temperature between observations is unknown.

Before an incident opens:
- The first above-threshold reading begins a candidate excursion.
- A reading at or below the threshold resets the candidate.
- A gap greater than the configured maximum resets continuity; the next warm reading begins a new candidate.
- Open an incident only on an observed reading that proves the elapsed sustained duration meets or exceeds the rule.
- Do not trigger an incident simply because wall-clock time passes without readings.

After an incident opens:
- Further warm readings update the existing incident.
- Emit only one opening alert for that incident.
- Begin a recovery candidate on a reading at or below the threshold.
- A warm reading or excessive gap resets the recovery candidate.
- Close the incident only after sufficient observed recovery evidence.
- Once closed, a later sustained excursion can open a new incident.

Missing telemetry:
- Missing data is not evidence of recovery.
- An open incident stays open across telemetry loss.
- Represent data freshness separately from incident lifecycle.
- Do not imply that the entire unobserved gap was above threshold.
- Do not send a second opening alert when telemetry resumes for the same open incident.

Maintain separate fields for:
- Excursion start time.
- Time the qualifying reading occurred.
- Time the system processed the incident opening.
- Recovery start time, if known.
- Time recovery was confirmed.
- Last valid observation time.
- Evidence count and observed maximum temperature.
- Rule version or rule snapshot.

Avoid a single ambiguous “duration” field. Distinguish elapsed incident age from duration supported by continuous telemetry.

DATA ORDERING AND IDEMPOTENCY

Keep event time and ingestion time distinct. Use timezone-aware UTC internally.

For the time-boxed MVP, implement this simple, explicit policy:
- Offline replay: validate, deduplicate, and sort by event time within each tenant/truck stream.
- Live ingestion: process readings in increasing event-time order per stream.
- Persist older readings as late data, but do not retroactively change live incident state or send retrospective notifications.
- Make late-data counts and this limitation visible.

This means offline replay can produce different results from live ingestion under late delivery. Document that honestly. Describe bounded event-time buffering and watermark-based processing as the production evolution.

Handle exact duplicates idempotently:
- Prefer a device event ID when present.
- Otherwise, define a stable deterministic identity from canonical source fields.
- A duplicate must not create another reading, incident, or opening-alert event.
- A conflicting payload using the same identity must produce an explicit conflict.
- Define deterministic handling for different readings with identical event timestamps.
- Document the MVP assumption of one authoritative temperature stream per truck and what changes when multiple sensors exist.

Reject or clearly quarantine invalid readings:
- Missing required fields.
- Invalid or timezone-ambiguous timestamps.
- Non-finite temperatures.
- Unsupported units.
- Unknown devices or unauthorized truck/device relationships.

Separate validation failures, duplicates, late readings, and accepted readings in ingestion results.

ARCHITECTURE

Build a modular monolith with clear separation between:
- Pure domain rules and state transitions.
- Ingestion and application orchestration.
- Persistence.
- API transport.
- Frontend presentation.

Use an incremental state machine rather than repeatedly scanning the full history for every new reading.

Keep authoritative state in the database. Persist the reading, resulting state transition, and opening-alert record atomically.

Serialize state-changing writes appropriately for the SQLite deployment. Do not assume async endpoints or multiple web workers make read-modify-write operations safe. Document the supported single-instance concurrency model.

Use database constraints to enforce relevant uniqueness. Do not rely only on in-memory duplicate checks.

A practical model may include:
- Tenant.
- Truck and its authorized device identity.
- Rule configuration.
- Reading with processing status.
- Persisted detector state.
- Incident.
- Opening-alert event, if separate from Incident.

Prefer the fewest entities that clearly support the required behavior.

Snapshot the rule used by a candidate or incident so historical explanations do not silently change when configuration changes. Rule editing through a UI is optional.

MULTI-CUSTOMER FOUNDATION

The MVP should support a safe, explicit tenant boundary:
- Include tenant identity in relevant records, indexes, and uniqueness constraints.
- Scope all reads and writes to the authenticated tenant.
- Derive tenant identity from a simple credential mapping for the demo, rather than trusting a body field or tenant header alone.
- Bind device credentials to an allowed tenant/device/truck.
- Provide minimal operator authentication for read endpoints if necessary.
- Use environment-based demo credentials and do not commit real secrets.
- Include at least one test proving that tenant A cannot read or mutate tenant B’s data.

Do not create a complete identity-management platform.

In SOLUTION_DESIGN.md, compare:
1. Separate deployment per customer.
2. Shared multi-tenant deployment.

Recommend a sensible initial approach and explain how operational scale, isolation requirements, and compliance needs could change the choice.

API AND IOT

Provide a small API, adapting naming to the existing project:
- POST /api/v1/readings for one reading or a bounded batch.
- GET /api/v1/trucks for latest readings, freshness, and incident status.
- GET /api/v1/incidents with basic pagination and filters.
- GET /api/v1/incidents/{id} with explanation and supporting evidence.
- GET /health.

Use bounded requests and queries, useful error responses, and appropriate indexes.

Document the HTTP ingestion contract with a realistic example payload and response.

If time permits, create a deterministic simulator that uses the real ingestion API and can demonstrate:
- Normal temperatures.
- A short spike.
- Sustained warming.
- Recovery.
- Duplicate delivery.
- Late delivery.
- Connectivity loss.

Explain how a future MQTT adapter would feed the same application service. Do not pretend MQTT is implemented if it is only designed.

DASHBOARD

Build this only after the engine, replay, tests, and required documentation work.

Keep it compact:
- Fleet overview: trucks monitored, active incidents, stale telemetry.
- Truck table: last temperature, observation time, freshness, and incident status.
- Incident list: truck, start, trigger time, lifecycle, and clear reason.
- Detail panel: evidence timeline or simple temperature chart with threshold and incident markers.

Use backend data, clear units and timestamps, accessible status labels, and loading, error, and empty states.

Historical replay must not appear to be live fleet telemetry. Show the replay reference time or clearly label the dataset as historical.

Use lightweight polling if needed. WebSockets are not required.

Do not add decorative pages, fake metrics, unimplemented controls, or unsupported “production-ready” claims.

TESTS AND ACCEPTANCE CRITERIA

Prioritize meaningful domain and integration tests:
- All-normal stream produces zero alerts.
- Short excursion produces zero alerts.
- Exact threshold is not a warm reading.
- Duration exactly meeting the rule opens an incident.
- A normal reading resets a pending excursion.
- A gap exactly at the limit preserves continuity.
- A larger gap resets a pending excursion.
- An ongoing incident emits only one opening alert.
- Recovery requires sustained evidence.
- A brief normal reading does not close an incident.
- A recovered truck can later open a new incident.
- Duplicate submission causes no duplicate side effects.
- Late live data follows the documented policy.
- Shuffled offline input gives the same result after normalization.
- Restarting the application preserves incident continuity.
- Trucks and tenants are evaluated independently.
- Cross-tenant access is denied.
- Invalid readings receive explicit outcomes.

Include a small hand-verifiable fixture independent of the supplied dataset. For example, under the proposed rule:
- Warm readings at 00:00, 00:05, and 00:10 open one incident at 00:10.
- Another warm reading at 00:15 does not open another.
- Normal readings at 00:20 and 00:25 confirm recovery at 00:25.

Run the provided dataset through the actual implementation. Do not guess expected results.

DATASET OUTPUT

Provide a reproducible command that outputs a readable table plus JSON or CSV containing:
- Truck ID.
- Incident ID.
- Excursion start.
- Qualifying event time.
- Threshold and required duration.
- Evidence count and observed maximum.
- Current lifecycle.
- Recovery time, where applicable.
- A factual plain-language explanation.

Example:
“Truck T-04 had consecutive readings above 8°C from 10:05 to
10:15 UTC, with no gap exceeding 5 minutes. The 10:15 reading
satisfied the 10-minute rule; one incident was opened.”

Do not infer reefer failure, spoiled cargo, or other root causes from temperature evidence alone.

Make rerunning the demo reproducible and explain database reset behavior. Do not delete unrelated user data.

DOCUMENTATION

Create SOLUTION_DESIGN.md, targeting 1–2 pages:
- Customer problem and success criteria.
- Key discovery questions and chosen assumptions.
- Exact detection, recovery, gap, duplicate, and ordering semantics.
- Small architecture diagram.
- Implemented scope and deliberate exclusions.
- SQLite and single-instance limitations.
- Multi-customer deployment approach.
- Production evolution and trade-offs.

Create README.md:
- Prerequisites and exact setup commands.
- Environment variables.
- How to run the backend and optional frontend.
- How to replay the supplied dataset.
- How to run tests.
- Actual example output from the supplied dataset.
- A short demo walkthrough.
- Known limitations.
- Implemented versus proposed features.
- Approximate effort and next priorities.

Include a concise panel-preparation section covering:
- Why this design reduces alert fatigue.
- Why gaps are not recovery.
- Why offline and live late-data behavior can differ.
- What happens after a restart.
- How concurrent ingestion is handled.
- What changes for customer-specific rules or multiple sensors.
- Where the first scaling bottleneck is likely to appear.

PRODUCTION EVOLUTION: DESIGN, DO NOT BUILD NOW

Describe a credible migration path:
- PostgreSQL for concurrent writes and stronger operational tooling.
- Durable ingestion queue when measured load requires it.
- Partition processing by tenant and truck to preserve ordering.
- Bounded event-time buffering and a policy for data arriving beyond the lateness window.
- Transactional outbox for external notifications.
- At-least-once delivery with idempotency; do not promise exactly-once external notifications.
- Retention, archival, indexing, and optional time partitioning.
- Device credential rotation and fleet provisioning.
- Metrics for ingestion lag, invalid data, duplicates, late data, stale devices, and alert-delivery failures.
- Backups, recovery, audit history, and deployment isolation.

Use a labelled workload example to estimate events per second from truck count and sampling frequency. Do not claim throughput without measurement.

OPTIONAL AI ENHANCEMENT

Only after the core solution is complete:
- Add an optional human-readable incident summary.
- Prefer a deterministic template as the default.
- If an LLM adapter is added, keep it outside detection logic.
- Do not send customer data to an external provider without explicit configuration.
- Provide a fallback and never invent causes or change incident decisions.
- Keep all core workflows functional without an API key.

DEFINITION OF DONE

Before finishing:
1. Run relevant tests.
2. Replay the supplied dataset.
3. Verify API behavior and duplicate handling.
4. Run the frontend build/type check if a frontend exists.
5. Verify that documented commands match the implementation.
6. State any checks you could not run and why.
7. Remove unfinished UI controls and misleading claims.
8. Summarize actual results, implemented scope, remaining limitations,
   and the next three improvements.

If the implementation budget is exhausted, stop adding features and finish the required deliverables. A correct, explainable alerting engine with a reproducible demo is the primary success criterion.

Begin by inspecting the repository and dataset, stating assumptions,
and then implementing the smallest complete end-to-end solution.
```
