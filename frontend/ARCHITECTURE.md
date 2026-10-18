# Frontend architecture

Coldline uses **Next.js 16 App Router, React 19, Redux Toolkit and RTK Query**, with TypeScript, React Bootstrap and colocated SCSS modules. Package versions are pinned in `package.json` and `package-lock.json`.

## Boundaries

```text
src/
  app/                 Next.js server layout/page, loading and error boundaries
  components/
    atoms/             Button, Brand, StatusBadge, Timestamp
    molecules/         MetricCard, Panel, Pagination, IncidentRow, feedback
    organisms/         FleetTable, FleetMetrics, IncidentList, evidence dialog/chart
    templates/         WorkspaceTemplate and LoginTemplate (layout slots)
  features/
    auth/              Session validation and credential lifetime
    dashboard/         Query orchestration, selectors and screen composition
    incidents/         Selected incident query and evidence pagination
  services/            Typed API endpoints, error mapping and operator validation
  store/               Store factory, typed hooks, provider and UI slice
  types/               API contracts, independent of rendering and persistence
  lib/                 Pure formatting helpers
  styles/              Global design tokens and minimal vendor defaults
  test/                Shared test setup and synthetic fixtures
```

Atomic design describes composition, not where every business operation belongs. Atoms form molecules; organisms compose those into complete sections; templates accept layout slots. Features connect these sections to the application. `app/page.tsx` only selects the entry feature. Presentation components receive typed props and callbacks; they never import Redux, API services or feature controllers. ESLint enforces that boundary. New customer branding belongs in tokens/configuration, while a new customer workflow belongs in a feature—not in a generic button or table.

## Server and client responsibilities

The root page/layout are Server Components. They render the public shell and metadata. The session boundary, Redux provider and interactive dashboard are Client Components. Server Components neither access the Redux store nor serialize tenant credentials. Client components use hooks and event handlers, with effect-driven code limited to external lifecycle concerns such as request cancellation and browser focus listeners. RTK Query replaces bespoke fetch effects and polling timers.

The deployed build is a **Next.js static export** in `frontend/out`, served by FastAPI alongside `/api`. This preserves the existing one-process demo and same-origin authentication. It intentionally does not use Server Actions, runtime SSR or a Node production server; those require a different deployment mode if later justified. `next dev` runs at `http://127.0.0.1:3000` and proxies `/api` to `BACKEND_ORIGIN` (default `http://127.0.0.1:8000`). No production rewrite is assumed inside exported assets.

## State ownership

| Kind of state | Owner | Why |
|---|---|---|
| Fleet, incidents, evidence, loading/errors | RTK Query | Cache, deduplication, request lifecycle, polling and focus/reconnect refresh |
| Lifecycle filter, list page, selected incident, evidence page | Redux `dashboard` slice | Shared state transitions; filters/selections reset dependent pagination |
| Operator key and active session | Auth boundary memory; store middleware extra argument | No localStorage, cookies, Redux state or persisted secrets |
| Password field draft and sign-in progress | Local component state | Short-lived interaction state, no global consumers |
| Metrics and historical-data indicator | Pure selectors | Derived from authoritative API data, not duplicated state |

Each successful sign-in mounts a new, keyed `StoreProvider`. `makeStore` creates a store for that session; there is no module-level store singleton. Unmount aborts running RTK queries and resets their cache. A late response from an old store cannot populate the new customer's store. Redux DevTools is disabled because request metadata can contain authorization headers. Client-side boundaries do not replace backend authorization.

Queries refresh every 15 seconds while focused, and on reconnect/focus. `currentData` is used for parameterized queries so changing a filter, incident or evidence page cannot display a previous query's results as the new selection. The detail dialog refreshes too. Empty, loading, error/retry and stale-data states are explicit; the chart never draws a line across an unsupported telemetry gap. Detection thresholds and incident transitions remain in Python.

## Extending the application

1. Add/update a transport type in `types/domain.ts` and a typed endpoint in `services/coldchain-api.ts`.
2. Add a feature hook/controller that owns orchestration. Reuse RTK Query data rather than copying it into a second slice.
3. Build prop-driven components at the appropriate atomic level, with colocated `.module.scss`.
4. Compose them in a feature and keep route files thin. Keep ephemeral input local; add Redux state only when multiple parts of a workflow share it.
5. Add behavior tests for the changed workflow, including errors and customer isolation when relevant.

## Verification and tooling

Use Node 24+, `npm ci`, then `npm run typecheck`, `npm run lint`, `npm test`, and `npm run build`. `npm run format` applies Prettier. No Vite application remains; Vitest may use Vite internally as a test runner dependency.

All eight frontend tests pass: authentication, failed login, API failure/retry, filtering, detail evidence, customer switching under Strict Mode, late-response isolation, API request deduplication/credentials, pagination resets and chart gaps. The Python HTTP smoke test serves the actual Next export and requests its generated static assets. A separate local development smoke check verified the Next login HTML and both unauthenticated/authenticated API proxy behavior. Type checking, lint, production build and the 23 backend tests pass. These checks do not replace visual browser QA.

TypeScript 6 and ESLint 9 are pinned for compatibility with the current `eslint-config-next` peer/API requirements; TypeScript 7 and ESLint 10 are not compatible with that tooling combination. ESLint 9 is upstream-deprecated, so track the framework's lint-tooling updates. The full npm audit currently reports five high-severity **development-only dependency entries** for one unpatched `braces` advisory through Next's lint plugin (`fast-glob` / `micromatch`). They do not ship in the static export. Do not blindly run `npm audit fix --force`: its proposed fix downgrades the Next lint configuration to an incompatible major. Production dependencies are audited separately with `npm audit --omit=dev`.

References: [Next.js App Router](https://nextjs.org/docs/app/getting-started), [Redux Toolkit with Next.js](https://redux.js.org/usage/nextjs).

Browser authentication uses username/password through `/api/v1/session` and an HTTP-only SameSite cookie. The store is recreated on login and disposed on sign-out; passwords and session tokens never enter Redux. API-key support remains only for programmatic clients and compatibility tests.
