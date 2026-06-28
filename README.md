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

## Quick start — one command (Windows)

This runs everything **locally** (no Docker) and enables the learned-model **deep scan on your GPU**:

```powershell
.\start.ps1          # or just double-click start.bat
```

It starts forensics (:8001), risk (:8002) and the dashboard (:5173), waits for the backends, and opens
**http://localhost:5173** in your browser. Stop everything by closing the windows or running `.\stop.ps1`.

> **No data ships in this repo.** Neither real nor synthetic documents are committed. The launcher
> auto-generates the synthetic loan packets on first run (`python -m data.generator.generate`); the
> dashboard's offline **Demo** mode works immediately from baked results. To rebuild the full image
> dataset / demo corpus, see *Datasets* below.

**First-time setup** (once): create the virtualenv and install dependencies, including PyTorch for the
GPU deep scan.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r services\forensics\requirements.txt -r services\risk\requirements.txt -r data\generator\requirements.txt
.\.venv\Scripts\python -m pip install -r services\forensics\requirements-models.txt   # PyTorch — GPU deep scan
```

> **Prerequisites:** Python 3.11+, Node 18+. For the GPU deep scan, an NVIDIA GPU with a CUDA build of
> PyTorch (it falls back to CPU automatically if CUDA isn't available). Tesseract OCR is optional.

---

## Alternative — Docker

Boots all three services (trained risk models are committed, so no setup needed):

```bash
docker compose up --build
#   forensics  → http://localhost:8001/health
#   risk       → http://localhost:8002/health
#   dashboard  → http://localhost:5173
```

> **Note:** the Docker images are intentionally lightweight and **do not include PyTorch or the model
> weights**, so the learned-model **deep scan is unavailable under Docker** (the single-document tool
> runs the heuristics only). Use the one-command local launcher above to get the GPU deep scan. Also
> generate the synthetic packets first (`python -m data.generator.generate`) — datasets aren't committed.

---

## Run locally — manual

If you prefer to start services yourself (run all Python commands **from the repo root**):

```bash
# backends
python -m uvicorn services.forensics.app.main:app --port 8001 &
python -m uvicorn services.risk.app.main:app --port 8002 &
# dashboard
cd services/dashboard && npm install && npm run dev      # → http://localhost:5173
```

### The learned forgery model ("deep scan")

The single-document tool runs the zero-false-positive **heuristics by default**. When a document looks
clean, a **“Run learned model (deep scan)”** button runs the opt-in U-Net, which localizes seamless
edits the heuristics miss. The deep scan needs PyTorch + the model weights present locally:

```bash
pip install -r services/forensics/requirements-models.txt   # installs torch
python services/forensics/train_forgery.py                  # trains weights → models/forgery/unet/weights/
```

> **Honest limit:** on held-out **synthetic** docs the v2 U-Net is strong — **~100% recall** on
> naive/blended/pro edits at a **~2–3% clean-doc false-positive** rate (vs the old whole-page model's
> ~0.29 pro-recall and ~19% FP). But it is **not yet validated on real phone-photos of ID cards**, so it
> stays **opt-in** (the "deep scan"), never the default. The guaranteed-local default layer is heuristics
> + semantic + QR, which hold a **0 false-positive** rate on clean documents.

---

## Demo & verification

```bash
# Reproducible 3-minute demo: rebuild the cross-application graph and replay the staged packets
python scripts/seed_demo.py            # prints "Demo replay OK" when every packet matches expectations
#   then follow DEMO.md for the live walkthrough

# Build the browsable, cross-verified demo corpus (clean+edited docs across difficulty + curated packets)
python scripts/build_demo_folder.py    # → demo/

# Prove there are no network calls at runtime
python scripts/verify_local_only.py

# Run the test suite
pytest tests/
```

---

## Datasets (not committed — generate locally)

No documents — real **or** synthetic — are committed to this repo; only the generators are. Recreate
what you need locally:

```bash
python -m data.generator.generate          # synthetic loan packets → data/synthetic/packets/ + labels.json
python -m data.generator.build_image_dataset   # the single-document image dataset → data/synthetic/images/
python scripts/build_demo_folder.py        # browsable, cross-verified demo corpus → demo/
```

Real, PII-bearing documents (if you supply any for local validation) live under `data/real/` and are
**never** committed. The one-command launcher generates the packets automatically on first run.

---

## Repository layout

```
README.md          PROGRESS.md (build log) · DECISIONS.md (why-log) · DEMO.md (walkthrough)
start.ps1 / .bat   one-command local launcher · stop.ps1
services/          forensics · risk · dashboard
shared/            schemas (the contract) · mocks (local verification adapters) · privacy (PII redaction)
data/              generator (code) → synthetic/ datasets are generated locally, not committed
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
