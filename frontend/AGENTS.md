<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Coldline architecture conventions

- Read `ARCHITECTURE.md` before extending a feature.
- Keep `src/app` routes thin; feature controllers own workflow orchestration.
- Atomic UI components accept props and callbacks. Do not import the store, services or feature controllers into `src/components`.
- Put API contracts/endpoints in `types` and `services`; use RTK Query rather than hand-written fetch/polling effects.
- Create stores per authenticated session. Never create a module-level Redux store or persist operator keys.
- Colocate component styles in SCSS modules. Keep global styles limited to tokens and vendor defaults.
- Preserve Next static-export serving through FastAPI and test the development proxy when changing routing.
- Verify with `npm run typecheck`, `npm run lint`, `npm test`, and `npm run build` using Node 24+.
