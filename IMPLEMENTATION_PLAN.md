# Implementation plan

1. Inspect supplied evidence and establish explicit rules. Acceptance: dataset findings and timezone assumption documented.
2. Build a pure incremental detector and transactional tenant-scoped persistence. Acceptance: boundaries, gaps, recovery, idempotency, restart and isolation tests pass.
3. Expose authenticated HTTP ingestion and bounded read APIs; replay through the same service. Acceptance: actual dataset exported with explanations; invalid and late outcomes visible.
4. Add a compact operations dashboard after core verification. Acceptance: real data, historical labeling, errors/empty states, successful type check/build.
5. Finish runbook and solution design. Acceptance: reproducible commands, actual results, customization contract, deployment trade-offs and honest limitations.

No licensed theme or existing frontend is present. Preserve the starter files as supplied reference material. Treat `case-study-brief.md` as the product brief; older drafts are not authoritative.

Completed foundation: engine, tenant/device credentials, SQLite transactions, schema versioning, API, replay, customer configuration, dashboard, HTTP simulator, design and runbook. Actual dataset: 54 readings and two recovered incidents.

Production hardening (completed):

6. Transactional notification outbox and worker. Acceptance: outbox commits/rolls back with the incident; signed webhook, Slack-format and log channels; retry with backoff, dead-letter and operator retry tested.
7. Acknowledgement and escalation. Acceptance: idempotent acknowledgement with audit timeline; escalation levels fire once each until acknowledged; dashboard shows acknowledgement, timeline and deliveries.
8. Multi-instance readiness. Acceptance: PostgreSQL URL support with per-truck row locks, SKIP LOCKED claims and advisory-locked migration/provisioning; database-backed sessions shared by two app instances in tests; schema v1→v2 migration.
9. Identity, observability and recovery. Acceptance: OIDC JWT verification (asymmetric algorithms only, tenant and role claims); managed-identity database tokens; JSON logs, request IDs, `/metrics`, `/ready`; SQLite backup/verify/restore with manifest; non-root container and PostgreSQL/worker Compose profile.
10. Demo alert simulation. Acceptance: rule-relative genuine and non-genuine scenarios injected from the dashboard or API, with expected-versus-observed verdicts; steady baseline option.

Open, customer-dependent: actual channels and on-call integration, escalation timings and quiet hours, acknowledgement ownership, retention/residency, RPO/RTO sign-off. Open, environment-dependent: staging validation on managed PostgreSQL, a real IdP and container runtime (not available in the implementation environment). See `README.md`, `SOLUTION_DESIGN.md`, and `frontend/ARCHITECTURE.md` for current behavior and boundaries.
