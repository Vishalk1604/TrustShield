# CLAUDE.md — TrustShield (root)

## Purpose
TrustShield is a 100% local-first underwriting copilot that detects document tampering/forgery across a loan packet and returns an explainable trust score (0–100) + evidence chain + recommended action. This is the root context for AI-assisted work across the whole repo.

## Start-of-session protocol
1. Read [`plan.md`](plan.md) — the full idea + phase map + standing decisions.
2. Read [`PROGRESS.md`](PROGRESS.md) — resume from the first unchecked phase.
3. Make ambiguous calls, implement, and log non-obvious ones in [`DECISIONS.md`](DECISIONS.md). Don't stall.

## Key files / folders
- `plan.md` — master plan (read first). `PROGRESS.md` — phase checklist. `DECISIONS.md` — why-log.
- `docker-compose.yml` — boots forensics (8001) + risk (8002) + dashboard (5173).
- `services/forensics/` — Service A: ingestion, PDF metadata, template fingerprint, OCR (Phase 1–2).
- `services/risk/` — Service B: semantic rules, Isolation Forest, NetworkX graph, scoring (Phase 2–5).
- `services/dashboard/` — Service C: React + Vite investigator UI (Phase 6).
- `shared/schemas/models.py` — the Pydantic contract every service imports.
- `shared/mocks/` — local mock adapters for GSTIN/MCA21/CERSAI/AIS/DigiLocker (zero network).
- `data/generator/` — synthetic packet generator → `data/synthetic/packets/` + `labels.json`.
- `scripts/verify_local_only.py` — fails if any outbound-network code appears outside mocks/tests.

## How it fits
Dashboard (browser) → calls forensics + risk over local REST. Both Python services import the shared schemas and mock adapters. The generator produces the synthetic packets all phases test against; `labels.json` is the ground truth used to prove accuracy.

## Local-only contract (applies everywhere)
- **No real network calls at runtime.** External verifications are local mocks reading JSON fixtures. `verify_local_only.py` enforces this and must pass at the end of every phase.
- **Never output a score without an evidence chain.**
- **Never log raw PII** (PAN, account numbers, names) — redaction lands in Phase 7 but don't introduce raw-PII logging before then.
- Prefer light tools (SQLite, NetworkX) over heavy ones (Postgres, Neo4j); any upgrade is logged in DECISIONS.md.

## How to run / test everything
```bash
docker compose up --build          # all three services; /health on 8001 & 8002, UI on 5173
python -m data.generator.generate  # (re)generate synthetic packets + labels.json
python scripts/verify_local_only.py
pytest tests/
```
Run Python from the **repo root** so `from shared.schemas.models import ...` resolves (repo root is the PYTHONPATH root).

## Gotchas
- Import paths assume repo root on `PYTHONPATH`. In Docker this is `/app` (bind-mounted); locally, run from the repo root (or `pip install -e .` is not used — we rely on path, not packaging).
- Services run as module paths: `uvicorn services.forensics.app.main:app`.
- Tesseract is **not** bundled; it's a Phase 2 prerequisite. Phase 0/1 don't need it.
- Synthetic PDFs under `data/synthetic/packets/` are committed on purpose (tiny, synthetic, zero PII).

## Status
- **All phases complete (0–8).** Forensics + semantic rules + learned model (Isolation Forest + GBC,
  ROC-AUC 0.97) + trust-score aggregation + cross-application graph (fraud rings + double-financed
  collateral) + investigator dashboard + PII-redaction/privacy layer + demo. See `PROGRESS.md` for the
  per-phase log and `DECISIONS.md` for the why. **135 tests pass; `verify_local_only.py` passes.**
- Run the demo: `python -m services.risk.train` (once) → `python scripts/seed_demo.py` → follow `DEMO.md`.
