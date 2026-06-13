# TrustShield — Decision Log

Append-only. Each entry: date · decision · why · alternatives considered. Newest at the bottom of each phase.

## Phase 0 (2026-06-13)

- **NetworkX over Neo4j** for the cross-application graph (Phase 5). *Why:* the build must run on a single laptop with no external services; an in-memory NetworkX graph (persisted to pickle/SQLite) covers the demo's clustering needs without the operational weight of a graph DB. A Neo4j upgrade would be a separate, explicitly-approved change logged here.
- **SQLite over Postgres** for local persistence. *Why:* zero-setup, file-based, laptop-friendly; the data volume in a demo is tiny.
- **PyMuPDF (fitz) as the single PDF library** for both *building* and *tampering* synthetic documents. *Why:* fitz is already a hard dependency for the forensics service, can author PDFs, set arbitrary metadata, perform incremental saves (to forge revision artifacts), and copy/redact regions — so we avoid pulling in a second lib (reportlab) just for generation.
- **Deterministic generator (fixed RNG seed); committing the generated synthetic PDFs.** *Why:* the PDFs are tiny, fully synthetic (no real PII), and committing them means a fresh clone can run the demo with zero setup. The generator is deterministic, so they can also be regenerated identically. Alternative (gitignore the PDFs, regenerate on clone) rejected for adding a setup step before the demo works.
- **Python 3.11-slim base images** for the FastAPI service containers; local host development runs 3.12. *Why:* 3.11 is the stated floor and yields smaller, well-supported wheels (PyMuPDF, scikit-learn); the code stays 3.11/3.12 compatible.
- **Import model: repo root is the PYTHONPATH root.** `shared` and `data` are top-level packages; Python services run as module paths (`uvicorn services.forensics.app.main:app`); Compose bind-mounts the repo into `/app` with `PYTHONPATH=/app`. *Why:* both services and the generator share one schema/mocks codebase without packaging/publishing a wheel; bind-mount gives hot reload for the demo.
- **Service requirements are scoped per phase.** Phase 0 service `requirements.txt` only pins `fastapi/uvicorn/pydantic`; heavier deps (PyMuPDF, pytesseract, scikit-learn, networkx) are added in the phase that first needs them. *Why:* keeps early images small and build times fast; avoids implying capabilities that don't exist yet.
- **Ports:** forensics 8001, risk 8002, dashboard 5173. CORS on the FastAPI services allows `http://localhost:5173` so the browser dashboard can call them directly.
- **Git: commit straight to `main`** (no per-phase feature branches). *Why:* early-stage, effectively solo cadence; revisit if multiple teammates start working in parallel.
