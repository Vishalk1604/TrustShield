# CLAUDE.md — services/dashboard (Service C)

## Purpose
The investigator UI (React + Vite). **Phase 0:** a placeholder that pings both backend services'
`/health` and surfaces the on-premise privacy statement. Phase 6 turns it into the real product:
upload a packet → live processing → trust score + evidence chain + tampered-vs-clean comparison +
exportable report.

## Key files
- `index.html` — entry HTML + base styles. `src/main.jsx` — React bootstrap.
- `src/App.jsx` — the page: service-health cards, privacy banner, build-progress list.
- `src/config.js` — local service URLs (`FORENSICS_URL`, `RISK_URL`), defaulting to localhost; override
  via `VITE_FORENSICS_URL` / `VITE_RISK_URL`.
- `vite.config.js` — dev server on `0.0.0.0:5173` (strict port). `Dockerfile` — `node:20-slim`, runs
  the Vite dev server.

## How it fits
Browser-side calls go to the LOCAL forensics (8001) and risk (8002) services only. State flow in
Phase 0 is just `useHealth(base)` polling `/health`.

## Local-only contract
All endpoints are localhost. There are **no remote URLs** anywhere — `scripts/verify_local_only.py`
checks this. If you add a backend call, point it at `FORENSICS_URL` / `RISK_URL`, never a hardcoded
host.

## How to run / test just this part
```bash
cd services/dashboard
npm install
npm run dev            # http://localhost:5173
# or via Docker:  docker compose up dashboard
```
The two backend services must be running for the health dots to go green.

## Gotchas
- Backend CORS allows exactly `http://localhost:5173` / `127.0.0.1:5173`. If you change the dev port,
  update the services' `CORSMiddleware` too.
- The Docker image runs the Vite **dev** server (fine for the demo). A production build would use
  `vite build` + a static server — out of scope for now.

## Status
- **Done (Phase 0):** placeholder page + live service-health polling + privacy banner.
- TODO (Phase 6): upload flow, evidence-chain view, tampered-vs-clean comparison, exportable report,
  cluster graph (if Phase 5 done).
