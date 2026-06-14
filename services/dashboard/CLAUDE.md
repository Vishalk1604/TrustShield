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
- **Done (Phase 6):** full investigator console — packet picker (driven by `GET /risk/demo/packets`),
  trust gauge + recommendation, forensic/semantic/model sub-scores, severity-colored evidence chain,
  cross-application graph SVG (`GraphView.jsx`), and JSON report export. `src/api.js` wraps the local
  risk endpoints; `POST /risk/demo/seed` + `POST /risk/demo/score/{id}` provide the data.
- **Done (Phase 9 — §6.D3):** a **Tamper localization** panel (annotated page images with the edit
  region boxed) + per-finding region badges in the evidence cards, fed by the new `tamper_overlays`
  field on the demo-score response. Still no new npm deps (base64 PNGs rendered server-side by PyMuPDF).

## Phase 9 notes (§6.D3 — tamper localization)
- `POST /risk/demo/score/{id}` now also returns `tamper_overlays:[{doc,page,image_b64}]` **outside** the
  `decision` payload, so the exported JSON report stays lean. `App.jsx` reads `result.tamper_overlays`.

## Phase 6 notes
- The browser cannot pass local file paths to the backend, so the demo scores the committed synthetic
  packets **by id** via `/risk/demo/*`. A real upload flow (multipart → forensics) is a later refinement.
- No new npm dependencies were added (React + inline styles + hand-rolled SVG only) to keep the image
  small and the build fast. `package-lock.json` is committed; `node_modules/` and `dist/` are gitignored.
