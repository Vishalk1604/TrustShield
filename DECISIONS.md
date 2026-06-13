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

## Build prerequisites installed (2026-06-13) — for the unattended `trustshield-autobuild` routine

To let the every-6-hours routine progress through later phases without stalling on a missing host
dependency, these were pre-installed:

- **Tesseract OCR 5.4.0** (UB-Mannheim build) at `C:\Program Files\Tesseract-OCR\tesseract.exe`.
  - **Gotcha:** winget added it to the *machine* PATH, but the already-running app (and the shells
    its tools spawn) won't see that PATH update until the app is restarted. So **Phase 2 code must
    set `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`**
    (or prepend that dir to PATH) rather than relying on a bare `tesseract` on PATH. Verified
    end-to-end: pytesseract OCRs a rendered Form 16 and recovers "FORM 16 / Rahul Sharma / PAN".
  - The **forensics Docker image** needs its own copy for in-container OCR: add
    `apt-get install -y tesseract-ocr` to `services/forensics/Dockerfile` and `pytesseract` to its
    requirements when Phase 2 lands.
- **Python libs added to `.venv`** for host-side dev/tests of later phases: `pytesseract 0.3.13`,
  `scikit-learn 1.9.0`, `joblib 1.5.3`, `networkx 3.6.1`, `pandas 3.0.3` (+ `numpy`/`scipy`/`Pillow`
  pulled in). Each service still pins its own scoped `requirements.txt` per phase (the venv is for
  local runs, not the container images).
