# CLAUDE.md — services/dashboard (Service C)

## Purpose
The investigator console (React + Vite, **single page, no routing, no auth** — plain `react`/
`react-dom`). Lists the synthetic loan packets on the left; selecting one runs the full
forensic → semantic → model → graph pipeline and shows the **trust gauge + recommendation,
sub-scores, severity-colored evidence chain, tamper-localization overlays, and the cross-application
graph** on the right, with JSON report export. Talks only to the LOCAL forensics (8001) + risk (8002).

> **History:** a multi-page routed app with auth + two roles + purpose-driven upload existed briefly
> (plan §8/§9, commit `66d9165`) but was **reverted** to this simpler console for the hackathon
> edit-detection pivot (plan §10). The §8/§9 **backend** (auth/cases/underwriting) still exists and is
> just unused by this frontend; the routed UI is recoverable from git if ever wanted.

## Key files
- `src/main.jsx` — renders `<App/>` (no router). `src/App.jsx` — the whole single-page console
  (palette + health polling + trust gauge + sub-scores + evidence cards + tamper-localization + export).
- `src/GraphView.jsx` — cross-application graph SVG. `src/api.js` — thin fetch wrappers around the
  LOCAL `/risk/demo/*` + `/health` endpoints (no auth headers).
- `src/config.js` — local service URLs (`FORENSICS_URL`, `RISK_URL`) + `SERVICES` list; override via
  `VITE_FORENSICS_URL` / `VITE_RISK_URL`.
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
