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
- **Done (Phase 1):** `POST /forensics/analyze` + `analyze/path`, metadata/date checks, structural
  template fingerprint, tamper signals (white-box/font/duplicate-image/incremental-update).
- **Done (Phase 2):** `app/extractor.py` — per-doc-type entity extraction (embedded-text fast path +
  Tesseract OCR fallback, now via the shared `app/ocr.py`).
- **Done (Phase 9 — §6.D2/D3):** `app/ocr.py` (shared local-OCR helpers, incl. `tesseract_available`);
  `analyzer._check_reocr_mismatch` (render→OCR→compare visible amounts/PANs vs the text layer — catches
  whiteout edits, layout-independent, currency-prefixed + "explained-away" precision guards);
  `regions` (page+bbox) on white-box & re-OCR findings + `render_tamper_overlay()` (pure PyMuPDF).
  Re-OCR is evidence-only — **excluded from the risk model's feature vector** (`enable_reocr` flag); see
  root `DECISIONS.md` (Phase 9). Degrades gracefully when Tesseract is absent.
- **Done (Real-doc KYC §9):** `app/ingest/model_registry.py` — the **seam** to the gitignored `models/`
  store (`resolve_model`/`model_available`, env `TRUSTSHIELD_MODEL_DIR`); deep models load from local
  disk when present, else heuristics run (no torch at runtime). New **`address_proof`** doc type
  (classifier keywords + `_extract_address_proof`) for KYC proof-of-address; schema `DocType.ADDRESS_PROOF`.
- TODO (production hardening — see `plan.md` §6.A/§6.D1): real OCR for **image/scanned uploads** (image
  intake, scan preprocessing, layout-aware OCR, doc-type classification, table extraction); and true
  **pixel/image forensics** (ELA, copy-move, noise/JPEG-ghost) for forgeries with no text layer.
