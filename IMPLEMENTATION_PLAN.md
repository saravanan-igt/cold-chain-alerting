# Implementation plan

1. Inspect supplied evidence and establish explicit rules. Acceptance: dataset findings and timezone assumption documented.
2. Build a pure incremental detector and transactional tenant-scoped persistence. Acceptance: boundaries, gaps, recovery, idempotency, restart and isolation tests pass.
3. Expose authenticated HTTP ingestion and bounded read APIs; replay through the same service. Acceptance: actual dataset exported with explanations; invalid and late outcomes visible.
4. Add a compact operations dashboard after core verification. Acceptance: real data, historical labeling, errors/empty states, successful type check/build.
5. Finish runbook and solution design. Acceptance: reproducible commands, actual results, customization contract, deployment trade-offs and honest limitations.

No licensed theme or existing frontend is present. Preserve the starter files as supplied reference material. Use prompt.md as the implementation specification; the older IDE draft has conflicting durations and is not authoritative.

Completed: engine, tenant/device credentials, SQLite transactions, schema versioning, API, replay, 23 passing backend tests, customer configuration, dashboard build, HTTP simulator, design and runbook. Actual dataset: 54 accepted readings and two recovered incidents. Follow-up frontend migration replaces Vite with Next.js App Router, React 19, atomic components, SCSS modules and Redux Toolkit/RTK Query. See frontend/ARCHITECTURE.md for boundaries, tests and the remaining development-only dependency advisory. Visual browser testing remains unavailable because no browser is connected; component rendering, static serving and HTTP integration are verified.
