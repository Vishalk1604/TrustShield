# TrustShield

**A local-first underwriting copilot that detects document tampering and forgery across a loan application packet — and explains every decision.**

Built for the SuRaksha (Canara Bank) hackathon. For every loan packet (identity doc, ITR / Form 16, bank statements, salary slips, optional property/legal doc), TrustShield runs three analyses **entirely on the laptop** and returns a **trust score (0–100)**, a full **evidence chain**, and a **recommended action** — approve, manual review, or freeze.

> 🔒 **100% local. No data ever leaves the machine.** Every external verification (GSTIN, MCA21, CERSAI, AIS, DigiLocker) is a local mock reading synthetic fixtures. There are no network calls at runtime — this is enforced by [`scripts/verify_local_only.py`](scripts/verify_local_only.py).

## What it does

| Analysis | What it catches |
|---|---|
| **Forensic tamper detection** | Edited figures, font/object inconsistencies, suspicious producer/modification software, copy-pasted regions, incremental-update revisions, reused templates |
| **Cross-document semantics** | ITR income ≠ bank-statement credits ≠ salary-slip totals; name/PAN/date mismatches across documents |
| **Behavioral anomaly scoring** | Template reuse across applicants, anomalous metadata timestamps, abnormal create→submit velocity (local Isolation Forest) |

Every score comes with a human-readable **evidence chain** — never a black-box number.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Dashboard   │──▶ │  Forensics   │     │     Risk     │
│ React + Vite │     │   FastAPI    │     │   FastAPI    │
│   :5173      │──▶ │   :8001      │◀──▶│   :8002      │
└──────────────┘     └──────────────┘     └──────────────┘
        │                    │                    │
        └──────── shared schemas + mock adapters (local only) ────────┘
```

- **Service A — Forensics + Ingestion** (`services/forensics/`, port 8001)
- **Service B — Risk + Scoring** (`services/risk/`, port 8002)
- **Service C — Dashboard** (`services/dashboard/`, port 5173)
- **Shared** — Pydantic schemas (`shared/schemas/`), mock verification adapters (`shared/mocks/`)
- **Data** — synthetic data generator (`data/generator/`) → packets + ground-truth `labels.json` (`data/synthetic/`)

## Quick start

```bash
# 1. Boot all three services
docker compose up --build

#    forensics  → http://localhost:8001/health
#    risk       → http://localhost:8002/health
#    dashboard  → http://localhost:5173

# 2. (Optional) regenerate synthetic test packets — they're already committed
python -m venv .venv && . .venv/Scripts/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r data/generator/requirements.txt
python -m data.generator.generate

# 3. Prove there are no network calls
python scripts/verify_local_only.py

# 4. Run tests
pip install pytest && pytest tests/
```

> **Prerequisites:** Docker Desktop, Python 3.11+, Node 18+. Tesseract OCR is required from **Phase 2** onward (not needed for Phase 0).

## Project status

This is a phased build. See [`PROGRESS.md`](PROGRESS.md) for what's done and [`plan.md`](plan.md) for the full plan and the idea behind each phase. Non-obvious choices are logged in [`DECISIONS.md`](DECISIONS.md).

**Currently:** Phase 0 — foundation, scaffolding, and synthetic data.

## Repository layout

```
plan.md           Master build plan (read first) · PROGRESS.md · DECISIONS.md
services/         forensics · risk · dashboard
shared/           schemas (the contract) · mocks (local verification adapters)
data/             generator (synthetic packets) · synthetic (output + labels.json)
scripts/          verify_local_only.py (no-network guard)
tests/            pytest suite
```

Every folder has a `CLAUDE.md` with local context for AI-assisted development.
