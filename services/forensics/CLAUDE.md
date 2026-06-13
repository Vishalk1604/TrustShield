# CLAUDE.md — services/forensics (Service A)

## Purpose
Forensics + Ingestion. Owns single-document integrity analysis: PDF metadata + modification-software
trace, structural template fingerprint (object-tree hash), tamper signals, and (Phase 2) OCR +
entity extraction. Emits `EvidenceItem`s of category `forensic`.

## Key files
- `app/main.py` — FastAPI app. **Phase 0:** `GET /health`, `GET /` only. Phase 1 adds
  `POST /forensics/analyze`.
- `requirements.txt` — Phase 0 scope (`fastapi/uvicorn/pydantic`); PyMuPDF + pytesseract added in
  Phase 1/2.
- `Dockerfile` — `python:3.11-slim`; build context is the **repo root** so `shared/` is importable.

## How it fits
The dashboard calls it; later, the risk service consumes its `EvidenceItem`s and the template
fingerprint (for Phase 5 clustering). Imports the contract from `shared/schemas`.

## Local-only contract
No outbound network calls. CORS is opened only for `http://localhost:5173`. The template
fingerprint and metadata reads are pure local PDF operations.

## How to run / test just this part
```bash
# from the repo root (so `shared` resolves)
uvicorn services.forensics.app.main:app --reload --port 8001
curl http://localhost:8001/health        # -> {"status":"ok","service":"forensics",...}
# or via Docker:  docker compose up forensics
```

## Gotchas
- Run from the **repo root** (PYTHONPATH=repo root) or the `from shared.schemas import ...` import
  fails. In Docker this is `/app`.
- **Tesseract is a Phase 2 prerequisite** and is NOT installed in the Phase 0 image. Add it to the
  Dockerfile (`apt-get install tesseract-ocr`) and `pytesseract` to requirements when Phase 2 starts.

## Status
- **Done (Phase 0):** health + schema wiring.
- TODO (Phase 1): `POST /forensics/analyze`, metadata extraction, object-tree fingerprint, tamper
  signals (font/text-vs-image/incremental-update/copy-paste). TODO (Phase 2): OCR + extraction.
