# TrustShield

**A local-first underwriting copilot that detects document tampering and forgery across a loan
application packet — and explains every decision.**

For every loan packet (identity document, ITR / Form 16, bank statements, salary slips, and optional
property/legal documents), TrustShield runs a layered analysis **entirely on the machine** and returns
a **trust score (0–100)**, a full **evidence chain**, and a **recommended action** — approve, manual
review, or freeze.

> 🔒 **100% local. No data ever leaves the machine.** Every external verification (GSTIN, MCA21,
> CERSAI, AIS, DigiLocker) is a local mock reading synthetic fixtures. There are **no network calls at
> runtime** — enforced by [`scripts/verify_local_only.py`](scripts/verify_local_only.py), which fails
> the build if any outbound call appears.

---

## What it does

TrustShield inspects each document through five independent detection layers that corroborate each
other and roll up into one auditable score:

| Layer | What it catches |
|---|---|
| **Pixel forensics** | Painted-over numbers, splices, copy-move, JPEG-ghosts, screen-recapture — via ELA, sensor-noise-loss, copy-move and recompression analysis on scans and phone photos. |
| **Semantic ID + QR** | PAN / Aadhaar structural validity and the card's signed QR cross-checked against the printed text — catches valid-looking but wrong edits. |
| **Learned forgery model** | An opt-in U-Net (“deep scan”) that localizes *seamless* edits the hand-tuned heuristics miss. Higher recall, with honestly-measured limits (see below). |
| **Trust score + evidence** | A weighted, documented blend → a 0–100 score, an ordered evidence chain, and a defensible recommended action. |
| **Cross-application graph** | Links fraud rings and double-financed collateral **across** separate applications — patterns no single file reveals. |

On top of that, a **KYC + underwriting** pass establishes identity & address, reconciles declared vs.
proven income across documents, and computes FOIR / affordability.

Every score comes with a human-readable **evidence chain** — never a black-box number. A *freeze*
always requires concrete document or graph evidence; a model hunch with nothing to point at is routed
to manual review, never an auto-reject.

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Dashboard   │ ──▶ │  Forensics   │     │     Risk     │
│ React + Vite │     │   FastAPI    │     │   FastAPI    │
│   :5173      │ ──▶ │   :8001      │ ◀─▶ │   :8002      │
└──────────────┘     └──────────────┘     └──────────────┘
        │                    │                    │
        └──────── shared schemas + mock adapters (local only) ────────┘
```

- **Service A — Forensics + Ingestion** (`services/forensics/`, port 8001) — intake, PDF metadata &
  template fingerprint, OCR + entity extraction, pixel/image forensics, the learned-model seam.
- **Service B — Risk + Scoring** (`services/risk/`, port 8002) — semantic rules, Isolation Forest +
  gradient-boosted model, trust-score aggregation, NetworkX cross-application graph.
- **Service C — Dashboard** (`services/dashboard/`, port 5173) — the investigator UI (Home, the
  Investigator console, and an annotated Examples gallery).
- **Shared** — Pydantic schemas (`shared/schemas/`), local mock verification adapters (`shared/mocks/`).
- **Data** — synthetic generator (`data/generator/`) → packets + ground-truth `labels.json`
  (`data/synthetic/`). A curated, cross-verified `demo/` corpus is built by
  [`scripts/build_demo_folder.py`](scripts/build_demo_folder.py).

---

## Quick start (Docker)

The fastest path — boots all three services (trained risk models are committed, so no setup needed):

```bash
docker compose up --build
#   forensics  → http://localhost:8001/health
#   risk       → http://localhost:8002/health
#   dashboard  → http://localhost:5173
```

Open **http://localhost:5173**. The two health dots go green when the backends are up.

---

## Run locally (without Docker)

> **Prerequisites:** Python 3.11+, Node 18+. Tesseract OCR is optional (enables OCR-based checks; the
> pipeline degrades gracefully without it).

```bash
# 1. Create a virtualenv and install dependencies
python -m venv .venv
. .venv/Scripts/activate                 # Windows PowerShell: .venv\Scripts\Activate.ps1
                                         # macOS/Linux:        source .venv/bin/activate
pip install -r services/forensics/requirements.txt
pip install -r services/risk/requirements.txt
pip install -r data/generator/requirements.txt
pip install pytest

# 2. Start the two backend services (run from the repo root so `shared` imports resolve)
python -m uvicorn services.forensics.app.main:app --port 8001 &
python -m uvicorn services.risk.app.main:app --port 8002 &

# 3. Start the dashboard
cd services/dashboard && npm install && npm run dev      # → http://localhost:5173
```

Run all Python commands **from the repo root** (the repo root is the import root).

### Optional: the learned forgery model ("deep scan")

The single-document tool runs the zero-false-positive **heuristics by default**. When a document looks
clean, a **“Run learned model (deep scan)”** button runs the opt-in U-Net, which localizes seamless
edits the heuristics miss. The deep scan needs PyTorch and the model weights present locally:

```bash
pip install -r services/forensics/requirements-models.txt   # installs torch
python services/forensics/train_forgery.py                  # trains weights → models/forgery/unet/weights/
```

> **Honest limit:** the U-Net is strong at *localizing* edits on synthetic documents, but has a
> measured **~19% false-positive rate on clean documents** (it over-flags the Form-16 salary region)
> and does not yet transfer to real phone-photos of ID cards. That is exactly why it is **opt-in**,
> never the default detection path. The guaranteed-local layer is heuristics + semantic + QR, which
> hold a **0/95** false-positive rate on clean documents.

---

## Demo & verification

```bash
# Reproducible 3-minute demo: rebuild the cross-application graph and replay the staged packets
python scripts/seed_demo.py            # prints "Demo replay OK" when every packet matches expectations
#   then follow DEMO.md for the live walkthrough

# Build the browsable, cross-verified demo corpus (clean+edited docs across difficulty + curated packets)
python scripts/build_demo_folder.py    # → demo/

# (Optional) regenerate the synthetic packets — they are already committed
python -m data.generator.generate

# Prove there are no network calls at runtime
python scripts/verify_local_only.py

# Run the test suite
pytest tests/
```

---

## Repository layout

```
README.md          PROGRESS.md (build log) · DECISIONS.md (why-log) · DEMO.md (walkthrough)
services/          forensics · risk · dashboard
shared/            schemas (the contract) · mocks (local verification adapters) · privacy (PII redaction)
data/              generator (synthetic packets) · synthetic (output + labels.json)
demo/              browsable, cross-verified demo corpus (documents + packets)
scripts/           verify_local_only.py · seed_demo.py · build_demo_folder.py
tests/             pytest suite
```

---

## Honest notes

- The models are trained on **synthetic** packets to prove the pipeline. The production answer is to
  retrain on the institution's own labelled history, on the institution's own hardware — the
  architecture (explainable trees + rules + graph) is what transfers.
- External registry checks (GSTIN / CERSAI / AIS / …) are **local mock adapters** behind a
  production-shaped interface; the single seam is where a real client would drop in.
- Every decision exports as a JSON evidence report from the dashboard, so any verdict is auditable.
