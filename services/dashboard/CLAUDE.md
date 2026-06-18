# CLAUDE.md — services/dashboard (Service C)

## Purpose
The web app (React + Vite + **react-router-dom**). A multi-page product with real auth and two roles
(plan §8): public **Home/About**, **Sign in/up**, a **User** dashboard (upload KYC/loan documents → trust
result + "My submissions"), and an **Admin** review queue → **Case detail** (full evidence chain, KYC,
tamper overlays, graph). Talks only to the LOCAL forensics (8001) + risk (8002) services.

## Key files
- `src/main.jsx` — bootstraps `<BrowserRouter><AuthProvider><App/>`. `src/App.jsx` — router/layout shell.
- `src/auth.jsx` — JWT auth context (localStorage); `src/components/ProtectedRoute.jsx` — route guards.
- `src/pages/*` — Home, About, SignIn, SignUp, UserDashboard, AdminDashboard, CaseDetail.
- `src/components/{Nav,DecisionView}.jsx` — nav (+ health dots) and the reusable decision renderer
  (trust gauge, evidence chain, tamper overlays, graph). `src/GraphView.jsx` — cross-application graph SVG.
- `src/api.js` — token + auth + cases calls (Bearer header) and the retained synthetic-demo calls.
- `src/theme.js` — shared palette + style tokens. `src/config.js` — local service URLs.
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
