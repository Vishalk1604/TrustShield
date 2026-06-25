# CLAUDE.md — services/dashboard (Service C)

## Purpose
The judge-facing dashboard (React + Vite + `react-router-dom`, no auth). Three routes share a common
`Shell` (top nav with the local-first badge + footer): **Home** (the full judge-facing pitch — hero with
stat callouts, an interactive "spot the edit" over a realistic Form 16 pair, the 5-layer pipeline, an
8-card features grid, honest proof stats + a synthetic→real "honest limit" callout, CTA; R2–R5 done), **Investigator**
(redesigned first-principles around the **5-layer pipeline spine** — two modes: *Loan packet* runs the
full forensic → semantic → model → trust → graph pipeline and *Single document* runs pixel + semantic
forensics on one image; both share one verdict grammar: neon trust gauge + action chip + rationale +
sub-scores, evidence **grouped by pipeline layer** with localization inline, and the cross-application
graph; a **Live/Demo toggle** falls back to baked-in decisions when the backend is down), and
**Examples** (the curated annotated gallery — R6 done — seamless before/after crops tagged by catching
layer + full-document localization overlays + an honest-limit note). Talks only to the LOCAL forensics
(8001) + risk (8002).

> **Design system (premium dark-glass):** `theme.js` holds the tokens (near-black base, `glass()`
> surface helper, per-layer hues, glow/motion scales); `index.css` vendors **Inter** (woff2 under
> `src/assets/fonts/`, no CDN) + the motion keyframes; reusable primitives live in `src/components/ui/`
> (`Gauge`, `Reveal`, `PipelineDiagram`, and `primitives.jsx` = Card/Badge/Stat/SectionHeader/Button).
> Baked-in demo data is in `src/data/` (`demoDecisions.js` captured from a real backend run +
> `curatedCases.js`); overlay PNGs are under `public/demo/`. **No npm deps were added** — a new dep
> requires a `docker compose up -d --build dashboard` (the image bakes `node_modules`; only `src/`,
> `public/`, `index.html` are bind-mounted).

> **History:** a multi-page routed app with auth + two roles + purpose-driven upload existed briefly
> (plan §8/§9, commit `66d9165`) but was reverted to a single-page console for the hackathon
> edit-detection pivot (plan §10). **R1 (this routing shell) reintroduced multi-page routing** — without
> auth — purpose-built for judges per `DASHBOARD_PLAN.md`. The §8/§9 **backend** (auth/cases/
> underwriting) still exists and is unused by this frontend.

## Key files
- `src/main.jsx` — wraps `<App/>` in `<BrowserRouter>`. `src/App.jsx` — route table (`/`, `/investigator`,
  `/examples`), all under `components/Shell.jsx`.
- `src/components/Shell.jsx` — sticky top nav (logo, Home/Investigator/Examples links, local-first
  badge, responsive hamburger below 860px) + footer; renders `<Outlet/>`.
- `src/components/LocalFirstBadge.jsx`, `src/components/Icons.jsx` — hand-rolled inline SVG icons (no
  icon-font / external CDN — local-only contract).
- `src/theme.js` — design tokens (color/font/radius/spacing/shared style primitives) used by all pages.
- `src/pages/Home.jsx` — landing page (hero shipped in R1; problem/pipeline/features/proof sections are
  the next backlog items). `src/pages/Investigator.jsx` — the full working console (moved verbatim from
  the old `App.jsx`). `src/pages/Examples.jsx` — stub pending R6.
- `src/GraphView.jsx` — cross-application graph SVG (used by `pages/Investigator.jsx`). `src/api.js` —
  thin fetch wrappers around the LOCAL `/risk/demo/*` + `/health` endpoints (no auth headers).
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
- **Done (dashboard rebuild R1 — `DASHBOARD_PLAN.md`):** routing shell (Home / Investigator / Examples)
  via `react-router-dom`; the one new npm dependency (already present in `node_modules` from the §8/§9
  era, now declared in `package.json` + `package-lock.json`). Brand tokens in `theme.js`; vendored inline
  SVG icons (no external CDN, no icon-font). The old single-page console moved into `pages/Investigator.jsx`
  unchanged in behavior. `npm run build` green; `verify_local_only.py` passes; Python suite unaffected
  (frontend-only change).

## Phase 9 notes (§6.D3 — tamper localization)
- `POST /risk/demo/score/{id}` now also returns `tamper_overlays:[{doc,page,image_b64}]` **outside** the
  `decision` payload, so the exported JSON report stays lean. `App.jsx` reads `result.tamper_overlays`.

## Phase 6 notes
- The browser cannot pass local file paths to the backend, so the demo scores the committed synthetic
  packets **by id** via `/risk/demo/*`. A real upload flow (multipart → forensics) is a later refinement.
- No new npm dependencies were added (React + inline styles + hand-rolled SVG only) to keep the image
  small and the build fast. `package-lock.json` is committed; `node_modules/` and `dist/` are gitignored.
