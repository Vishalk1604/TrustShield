# TrustShield — Master Build Plan

> **Read this first, every session.** This is the single source of truth for *what we're building and why*, the full phase map, and the standing decisions. It ships inside the repo so any teammate's Claude (or a fresh session) can pick up the thread without re-reading the whole codebase. Companion files: [`PROGRESS.md`](PROGRESS.md) (what's done / resume point), [`DECISIONS.md`](DECISIONS.md) (why we chose things), and a `CLAUDE.md` in every meaningful folder.

---

## 1. What & why

TrustShield is a **100% local-first underwriting copilot** for the SuRaksha (Canara Bank) hackathon — theme: behavior-based fraud/anomaly detection + data privacy. For every loan application packet (identity doc, ITR/Form 16, bank statements, salary slips, optional property/legal doc) it runs three analyses **entirely on the laptop** and returns a **trust score (0–100)** with a full **evidence chain** and a **recommended action** (approve / manual review / freeze), shown in an investigator dashboard.

The three analyses:
1. **Forensic tamper detection** — PDF metadata, modification-software trace, structural template fingerprint, font/object/copy-paste/incremental-update anomalies.
2. **Cross-document semantic validation** — OCR + entity extraction + a rules engine (e.g. ITR income ≠ bank credits ≠ salary-slip total).
3. **Behavioral anomaly scoring** — a local Isolation Forest over financial + behavioral features (template reuse, metadata-timestamp anomalies, create→submit velocity).

### Non-negotiable constraints (every phase, every line)
- **No external network calls at runtime.** Every external verification (GSTIN, MCA21, CERSAI, AIS, DigiLocker) is a **local mock** reading synthetic JSON fixtures behind a clean adapter interface that *looks* production-ready ("swap the adapter for the real API later") but never hits the network.
- **Explainability is the product.** No score without a human-readable evidence chain.
- **Privacy is a feature.** No customer data leaves the machine; PII redacted in logs; every decision is an auditable, exportable report.
- **Laptop-only, light tools.** Docker Compose or plain local processes; SQLite (not Postgres), NetworkX (not Neo4j) unless explicitly upgraded + logged in DECISIONS.md.

### Architecture
- **Service A — Forensics + Ingestion** (FastAPI, port 8001): metadata, modification-software trace, object-tree template fingerprint, OCR, entity extraction.
- **Service B — Risk + Scoring** (FastAPI, port 8002): semantic rules, Isolation Forest, in-memory NetworkX cross-application graph, trust-score aggregation, evidence-chain assembly.
- **Service C — Dashboard** (React + Vite, port 5173): upload packet → live processing → trust score + evidence chain + recommended action + tampered-vs-clean comparison + (stretch) cluster graph.
- **Shared**: Pydantic schemas (the contract), synthetic data generator, mock external-verification adapters.
- Internal REST between services is plumbing, not the pitch.

### Stack
Python 3.11+ · FastAPI · PyMuPDF (fitz) · Tesseract (pytesseract) · scikit-learn (Isolation Forest) · NetworkX · Pydantic v2 · React + Vite · Docker Compose · SQLite.

---

## 2. Phase map (the whole idea, end to end)

Each phase is self-contained: ends with its checks green, updates PROGRESS.md + any touched CLAUDE.md, and commits. **`scripts/verify_local_only.py` must pass at the end of every phase.**

| # | Phase | Where | Headline deliverable |
|---|---|---|---|
| 0 | Foundation, scaffolding, synthetic data | repo-wide | Bootable skeleton + schemas + synthetic packets + mocks + verify guard |
| 1 | Document Integrity / Forensics | `services/forensics/` | `POST /forensics/analyze` → EvidenceItem[]; metadata + template fingerprint + tamper signals |
| 2 | Semantic Consistency / Underwriting | `forensics/` (OCR) + `risk/` (rules) | OCR + entity extraction + cross-document rules engine |
| 3 | Anomaly & Behavioral Scoring | `services/risk/` | Isolation Forest + `train.py` + anomaly sub-score with top features |
| 4 | Trust Score Aggregation & Evidence Chain | `services/risk/` | `POST /risk/score` → TrustScore + evidence chain + recommendation; documented weights/thresholds |
| 5 | Cross-Application Graph (differentiator) | `services/risk/` | NetworkX graph; "shares template hash + employer with N flagged apps"; persisted |
| 6 | Investigator Dashboard | `services/dashboard/` | Upload → live → score + evidence chain + tampered-vs-clean + exportable report |
| 7 | Privacy & trust layer | repo-wide | PII redaction in logs; on-premise statement in UI; `PRIVACY.md` |
| 8 | Demo script & narrative | repo-wide | `DEMO.md` 3-min story + staged packets + `seed_demo.py` |

Per-phase deliverables and exact checks are detailed in §4.

---

## 3. Standing decisions (see DECISIONS.md for full rationale)

- Python **3.11-slim** service images; host dev on 3.12 (compatible).
- **PyMuPDF (fitz)** is the single PDF library for building + tampering synthetic docs.
- Generator is **deterministic** (fixed seed); generated synthetic PDFs **are committed** (tiny, synthetic, zero PII).
- Ports: forensics **8001**, risk **8002**, dashboard **5173**.
- Import model: repo root is the PYTHONPATH root; `shared` / `data` are top-level packages; Python services run as module paths (`uvicorn services.forensics.app.main:app`) so `from shared.schemas.models import ...` resolves. Compose bind-mounts the repo into `/app`.
- FastAPI `CORSMiddleware` allows `http://localhost:5173`.
- **NetworkX over Neo4j**, **SQLite over Postgres** — laptop/local constraint.
- Git: commit straight to **main**.

---

## 4. Per-phase detail & checks

### Phase 0 — Foundation (this is the launchpad; nothing detects anything yet)
Repo skeleton + all CLAUDE.md + this `plan.md` + PROGRESS.md/DECISIONS.md/README + Docker Compose booting 3 services with `/health` + shared Pydantic schemas + synthetic data generator (clean + every fraud type) + `labels.json` ground truth + mock adapters + `verify_local_only.py`.
**Checks:** `docker compose up` → all `/health` 200; generator ≥20 packets + valid `labels.json`; verify-local passes; every required folder has a non-empty CLAUDE.md; git remote confirmed + first push.

### Phase 1 — Forensics
`POST /forensics/analyze` → `EvidenceItem[]`. PDF metadata (create/mod dates, producer/creator, mod-software trace); **object-tree template fingerprint hash** (exposed for Service B clustering); tamper signals (font inconsistency, text-layer vs image-layer mismatch, incremental-update/revision detection, copy-paste/object anomalies).
**Checks:** every tampered packet raises ≥1 correct forensic finding, clean packets none — print precision/recall vs `labels.json`; template hash collides for reused templates, differs otherwise; verify-local passes.

### Phase 2 — Semantic Consistency
OCR pipeline (Tesseract) with a fast path using embedded text when present; entity extraction (declared income, employer, PAN, account numbers, salary credits, tax paid, dates); rules engine (income vs salary-credit vs tax-slab alignment, date/sequence sanity, name/PAN consistency). Each inconsistency → EvidenceItem with the two conflicting values + sources.
**Checks:** every cross-doc-inconsistency packet → correct evidence line, consistent packets no false-positive; extraction spot-checked on ≥5 packets; verify-local passes. *(Prereq: install Tesseract.)*

### Phase 3 — Anomaly & Behavioral Scoring
Feature engineering (financial + template-reuse count, metadata-timestamp anomalies, submission velocity); train Isolation Forest on clean synthetic packets, persist via joblib; `train.py` to retrain; return anomaly sub-score + **top contributing features**.
**Checks:** trains offline; meaningful fraud/clean separation (print AUC + example explanations); model committed or LFS-tracked (logged in DECISIONS.md); verify-local passes.

### Phase 4 — Trust Score Aggregation
Composite 0–100 score with an **explicit, documented weighting**; evidence-chain assembly (ordered, severity/source-tagged, deduplicated); recommended action with defensible thresholds; `POST /risk/score` → TrustScore + evidence chain + recommendation (main orchestration endpoint).
**Checks:** end-to-end confusion-matrix summary vs `labels.json`; every score has a non-empty evidence chain; weights/thresholds documented; verify-local passes.

### Phase 5 — Cross-Application Graph (only after 0–4 solid)
NetworkX graph (nodes = applicants/employers/CA firms/PANs/template hashes; edges = shared attributes); per-packet upsert + cluster surfacing; small subgraph for viz; persisted locally so the demo accumulates across uploads.
**Checks:** template-reuse packets form the correct cluster, unrelated stay unlinked; subgraph small + fast; verify-local passes.

### Phase 6 — Investigator Dashboard (wins/loses the demo)
Upload → live processing → trust score + recommended action + **evidence chain** (scannable, severity-color-coded, source-attributed = centerpiece); side-by-side **tampered-vs-clean** comparison; **exportable evidence report**; cluster graph if Phase 5 done. Local services only.
**Checks:** full flow works for all packet types; evidence chain legible to a non-technical reader; export produces a clean report; no hardcoded remote URLs.

### Phase 7 — Privacy & trust layer
PII redaction in all logs (mask PAN, account numbers, names); "All processing on-premise; no customer data transmitted externally" surfaced in the UI; finalize the exportable auditable report; root `PRIVACY.md`.
**Checks:** grep a demo run's logs → no raw PAN/account/names; verify-local passes; PRIVACY.md accurate.

### Phase 8 — Demo script & narrative
Root `DEMO.md` (3-min narrative + exact upload order + expected results); staged packets (clean / tampered / cross-doc + graph if done); `seed_demo.py` for identical replays; honest "real vs mocked" section + prepared Q&A.
**Checks:** seed + follow DEMO.md reproduces the demo twice from clean state; all docs current; final verify-local passes; final commit + push.

---

## 5. Working agreement (how we run the build)

1. **Start of session:** read `plan.md` (this file) + `PROGRESS.md`; resume from the first unchecked phase.
2. **During a phase:** make reasonable choices for ambiguities, implement, and log non-obvious ones in `DECISIONS.md` — don't stall.
3. **End of a phase:** run that phase's checks (fix before committing — a green PROGRESS.md must mean it actually works); update PROGRESS.md + touched CLAUDE.md; commit `Phase N: <desc>`; push to `main`; print the commit hash.
4. **Global rules:** never a real network call at runtime; never a score without an evidence chain; never log raw PII; keep it laptop-runnable.
