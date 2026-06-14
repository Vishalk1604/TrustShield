# TrustShield — Master Build Plan

> **Read this first, every session.** This is the single source of truth for *what we're building and why*, the full phase map, and the standing decisions. It ships inside the repo so any teammate's Claude (or a fresh session) can pick up the thread without re-reading the whole codebase. Companion files: [`PROGRESS.md`](PROGRESS.md) (what's done / resume point), [`DECISIONS.md`](DECISIONS.md) (why we chose things), and a `CLAUDE.md` in every meaningful folder.

---

## 1. What & why

TrustShield is a **100% local-first, real-time underwriting copilot** for the SuRaksha (Canara Bank) hackathon.

**Problem statement (the theme we're solving):** *How can a bank automatically detect tampering, changes, or forgery across **land records, legal documents, and financial statements** in real time, and provide intelligent insights to support faster, reliable decision-making during underwriting?*

For every loan application packet — identity, **financial** docs (ITR/Form 16, bank statements, salary slips) and **legal & land records** (sale deed, encumbrance certificate, property valuation, legal opinion) — TrustShield runs its analysis stack **entirely on the laptop, in real time**, and returns a **trust score (0–100)** + a full **evidence chain** + a **recommended action** (approve / manual review / freeze), in an investigator dashboard.

### The winning angle — collateral & cross-document fraud, not just "is this one PDF edited"
Most teams will detect "was this single PDF modified." The expensive, real underwriting fraud is broader and *cross-document* — and that's where we win:
- **Forged title / tampered land records** — altered owner name or survey number on a sale deed; a doctored **encumbrance certificate (EC)** that hides an existing mortgage.
- **Double-financing / loan stacking** — the *same property* pledged as collateral across multiple applications/banks (exactly what CERSAI exists to catch). A single-document tool is blind to this; our **cross-application graph** lights it up.
- **Valuation inflation** — a property valued far above market to justify a larger loan (abnormal loan-to-value).
- **Income forgery** — inflated Form 16 / bank credits that don't reconcile with tax records.
- **Organized rings** — one forged template reused across many "applicants."

TrustShield connects the dots **across the whole packet and across prior applications, in real time** — turning days of manual verification into minutes, with a regulator-ready audit trail. That breadth (financial **+** legal **+** land), the collateral-fraud graph, on-prem privacy, and an explainable trained model are the four things judges remember.

### The analysis stack
1. **Forensic tamper detection** — PDF metadata + modification-software trace, structural template fingerprint, font/object/copy-paste/incremental-update anomalies. Document-type-agnostic: works on financial *and* legal/land PDFs.
2. **Cross-document semantic validation** — OCR + entity extraction + a rules engine: income vs bank-credits vs tax-slab; **owner/PAN/property-ID/address consistency across sale deed ↔ EC ↔ valuation ↔ application**; loan-to-value sanity; EC vs CERSAI charge cross-check.
3. **Behavioral & statistical anomaly** — unsupervised **Isolation Forest** over behavioral features (template reuse, metadata-timestamp anomalies, create→submit velocity).
4. **Learned risk model** — a trained, **explainable** classifier (gradient-boosted trees) over *all* engineered signals → a calibrated fraud probability **with per-feature attributions** (feature importance / SHAP-style). Delivers the "real model + metrics" credibility while staying fully auditable — never a black-box number.
5. **Cross-application graph** — nodes = applicants, employers, PANs, template hashes **and property/title IDs**; surfaces fraud rings **and double-financed collateral**.

### Non-negotiable constraints (every phase, every line)
- **No external network calls at runtime.** Every external verification (GSTIN, MCA21, CERSAI, AIS, DigiLocker) is a **local mock** reading synthetic JSON fixtures behind a clean adapter interface that *looks* production-ready ("swap the adapter for the real API later") but never hits the network.
- **Explainability is the product.** No score — including the model's — without a human-readable evidence chain + feature attribution.
- **Privacy is a feature.** No customer data leaves the machine; PII redacted in logs; every decision is an auditable, exportable report.
- **Laptop-only, light tools.** Docker Compose or plain local processes; SQLite (not Postgres), NetworkX (not Neo4j) unless explicitly upgraded + logged in DECISIONS.md.
- **Honest about ML.** Models are trained on *synthetic* data to prove the pipeline; the architecture is what transfers — say so, and have "retrain on the bank's labeled history" as the production answer.

### Architecture
- **Service A — Forensics + Ingestion** (FastAPI, port 8001): metadata, mod-software trace, object-tree template fingerprint, OCR, entity extraction.
- **Service B — Risk + Scoring** (FastAPI, port 8002): semantic rules (financial + property), Isolation Forest, **supervised risk model**, property-aware NetworkX cross-application graph, trust-score aggregation, evidence-chain assembly.
- **Service C — Dashboard** (React + Vite, port 5173): upload packet → **live/real-time** processing → trust score + evidence chain + recommended action + tampered-vs-clean comparison + **model-metrics view** + cluster/collateral graph.
- **Shared**: Pydantic schemas (the contract), synthetic data generator, mock external-verification adapters.
- Internal REST between services is plumbing, not the pitch.

### Stack
Python 3.11+ · FastAPI · PyMuPDF (fitz) · Tesseract (pytesseract) · **scikit-learn (Isolation Forest + Gradient Boosting / Random Forest)** · feature-importance / SHAP-style attribution · NetworkX · Pydantic v2 · React + Vite · Docker Compose · SQLite.

---

## 2. Phase map (the whole idea, end to end)

Each phase is self-contained: ends with its checks green, updates PROGRESS.md + any touched CLAUDE.md, and commits. **`scripts/verify_local_only.py` must pass at the end of every phase.**

| # | Phase | Where | Headline deliverable |
|---|---|---|---|
| 0 | Foundation, scaffolding, synthetic data | repo-wide | ✅ Bootable skeleton + schemas + synthetic packets + mocks + verify guard |
| 1 | Document Integrity / Forensics | `services/forensics/` | `POST /forensics/analyze` → EvidenceItem[]; metadata + template fingerprint + tamper signals (any doc type) |
| 2 | Semantic Consistency / Underwriting | `forensics/` (OCR) + `risk/` (rules) | OCR + extraction + cross-document rules across **financial AND legal/land** docs (+ extend generator with land/legal packets) |
| 3 | Anomaly + **Learned Risk Model** | `services/risk/` | Isolation Forest **+ supervised, explainable classifier** + `train.py` + metrics (AUC / PR / confusion / feature importance) |
| 4 | Trust Score Aggregation & Evidence Chain | `services/risk/` | `POST /risk/score` → blended TrustScore (rule weights ⊕ model probability) + evidence chain + recommendation |
| 5 | Cross-Application Graph (differentiator) | `services/risk/` | NetworkX graph incl. **property/title nodes** → fraud rings **and double-financed collateral**; persisted |
| 6 | Investigator Dashboard | `services/dashboard/` | Real-time upload → score + evidence chain + tampered-vs-clean + **model-metrics view** + collateral/cluster graph + exportable report |
| 7 | Privacy & trust layer | repo-wide | PII redaction in logs; on-premise statement in UI; `PRIVACY.md` |
| 8 | Demo script & narrative | repo-wide | `DEMO.md` 3-min story + staged packets (incl. a double-financing graph reveal) + `seed_demo.py` |

Per-phase deliverables and exact checks are detailed in §4.

---

## 3. Standing decisions (see DECISIONS.md for full rationale)

- Python **3.11-slim** service images; host dev on 3.12 (compatible).
- **PyMuPDF (fitz)** is the single PDF library for building + tampering synthetic docs.
- Generator is **deterministic** (fixed seed); generated synthetic PDFs **are committed** (tiny, synthetic, zero PII).
- **Document scope = financial + legal/land**, not just financial — to match the problem statement. Doc types extend to `sale_deed`, `encumbrance_certificate`, `property_valuation`, `legal_opinion` (plus existing identity/itr/form16/bank_statement/salary_slip).
- **Two models, both explainable:** unsupervised **Isolation Forest** (novelty) + supervised **gradient-boosted trees** (calibrated fraud probability with feature importance). Tree-based + attributions keeps it auditable. No deep/black-box models — explainability is a hard requirement in regulated lending.
- Ports: forensics **8001**, risk **8002**, dashboard **5173**.
- Import model: repo root is the PYTHONPATH root; `shared` / `data` are top-level packages; Python services run as module paths (`uvicorn services.forensics.app.main:app`). Compose bind-mounts the repo into `/app`.
- FastAPI `CORSMiddleware` allows `http://localhost:5173`.
- **NetworkX over Neo4j**, **SQLite over Postgres** — laptop/local constraint.
- Git: commit straight to **main**; **no `Co-Authored-By` / AI attribution trailers** (repo-owner preference).

---

## 4. Per-phase detail & checks

### Phase 0 — Foundation ✅ (done)
Repo skeleton + all CLAUDE.md + this `plan.md` + PROGRESS.md/DECISIONS.md/README + Docker Compose booting 3 services with `/health` + shared Pydantic schemas + synthetic data generator + `labels.json` + mock adapters + `verify_local_only.py`.

### Phase 1 — Forensics
`POST /forensics/analyze` → `EvidenceItem[]`. PDF metadata (create/mod dates, producer/creator, mod-software trace); **object-tree template fingerprint hash** (exposed for Service B clustering); tamper signals (font inconsistency, text-layer vs image-layer mismatch, incremental-update/revision detection, copy-paste/object anomalies). Works on any document type — financial or legal/land.
**Checks:** every tampered packet raises ≥1 correct forensic finding, clean packets none — print precision/recall vs `labels.json`; template hash collides for reused templates, differs otherwise; verify-local passes.

### Phase 2 — Semantic Consistency (financial + legal/land)
First, **extend the generator** with legal/land documents and their fraud types: `sale_deed`, `encumbrance_certificate`, `property_valuation`, `legal_opinion`; new fraud types `forged_title`, `tampered_encumbrance`, `valuation_inflation`, `property_mismatch`, `double_financing` (shared property across packets). Add matching CERSAI/registry fixtures.
Then OCR (Tesseract; fast path uses embedded text when present) + entity extraction (income, employer, PAN, account numbers, salary credits, tax, dates, **property id / survey number, owner name, property address, valuation amount, loan amount**) + a rules engine:
- Financial: income vs salary-credit vs tax-slab alignment; date/sequence sanity; name/PAN consistency.
- **Property/legal:** owner name on sale deed == applicant; **property-id/address consistent across sale deed ↔ EC ↔ valuation ↔ application**; loan-to-value sanity (flag abnormal LTV); EC vs **CERSAI** charge cross-check (undisclosed existing mortgage).
Each inconsistency → EvidenceItem with the two conflicting values + sources.
**Checks:** every inconsistency packet → correct evidence line, consistent packets no false-positive; extraction spot-checked on ≥5 packets; verify-local passes. *(Prereq: Tesseract — already installed; see DECISIONS.md for the explicit path.)*

### Phase 3 — Anomaly + Learned Risk Model
Feature engineering from all signals: forensic flags, semantic-rule violations, behavioral features (template-reuse count, timestamp anomalies, submission velocity), property features (LTV, charge-mismatch). Then:
- **Isolation Forest** (unsupervised) on clean packets for novelty/anomaly sub-score + top contributing features.
- **Supervised classifier** (gradient-boosted trees / random forest) trained on the labeled synthetic set → calibrated **fraud probability**, explained via **feature importance / SHAP-style attributions**.
- `train.py` retrains both from synthetic data offline; persist via joblib.
- Print **metrics**: ROC-AUC, precision/recall, confusion matrix, top features — these become Phase 6 demo charts.
**Checks:** both models train offline with no network; meaningful fraud/clean separation (print AUC + example explanations); models committed or LFS-tracked (logged in DECISIONS.md); verify-local passes.

### Phase 4 — Trust Score Aggregation
Composite 0–100 trust score that **blends** the rule/forensic signals with the model probability, with an **explicit, documented weighting** (and the model's contribution shown, not hidden). Evidence-chain assembly (ordered, severity/source-tagged, deduplicated, includes the model's top feature attributions). Recommended action with defensible thresholds. `POST /risk/score` → TrustScore + evidence chain + recommendation (main orchestration endpoint).
**Checks:** end-to-end confusion-matrix summary vs `labels.json`; every score has a non-empty evidence chain; weights/thresholds/model-contribution documented in DECISIONS.md; verify-local passes.

### Phase 5 — Cross-Application Graph (only after 0–4 solid)
NetworkX graph: nodes = applicants, employers, CA firms, PANs, template hashes, **and property/title IDs**; edges = shared attributes. Per-packet upsert + cluster surfacing: fraud rings ("shares template + employer with N flagged apps") **and double-financed collateral ("this property is pledged in N other live applications")**. Return a small subgraph for viz; persist locally (pickle/SQLite) so the demo accumulates across uploads.
**Checks:** template-reuse packets form the correct ring; a property reused across packets forms a **collateral cluster**; unrelated packets stay unlinked; subgraph small + fast; verify-local passes.

### Phase 6 — Investigator Dashboard (wins/loses the demo)
**Real-time** upload → live processing → trust score + recommended action + **evidence chain** (scannable, severity-color-coded, source-attributed = centerpiece); side-by-side **tampered-vs-clean** comparison; a **Model Insights view** (ROC/PR curve, confusion matrix, feature-importance bars) for technical credibility; the **collateral/cluster graph**; **exportable evidence report**. Local services only.
**Checks:** full flow works for all packet types (financial + legal/land); evidence chain legible to a non-technical reader; model-metrics + graph render; export produces a clean report; no hardcoded remote URLs.

### Phase 7 — Privacy & trust layer
PII redaction in all logs (mask PAN, account numbers, names, **property ids**); "All processing on-premise; no customer data transmitted externally" surfaced in the UI; finalize the exportable auditable report; root `PRIVACY.md`.
**Checks:** grep a demo run's logs → no raw PII; verify-local passes; PRIVACY.md accurate.

### Phase 8 — Demo script & narrative
Root `DEMO.md` (3-min narrative + exact upload order + expected results). Staged packets: one clean (approves), one tampered (forensics catches), one cross-doc-inconsistent (semantics catches), and a **double-financing reveal** (upload a 2nd/3rd packet → graph flags the same property/title across applications = the wow). `seed_demo.py` for identical replays; honest "real vs mocked" + "trained on synthetic, retrain on real" Q&A; the model-metrics slide.
**Checks:** seed + follow DEMO.md reproduces the demo twice from clean state; all docs current; final verify-local passes; final commit + push.

---

## 5. Working agreement (how we run the build)

1. **Start of session:** read `plan.md` (this file) + `PROGRESS.md`; resume from the first unchecked phase.
2. **During a phase:** make reasonable choices for ambiguities, implement, and log non-obvious ones in `DECISIONS.md` — don't stall.
3. **End of a phase:** run that phase's checks (fix before committing — a green PROGRESS.md must mean it actually works); update PROGRESS.md + touched CLAUDE.md; commit `Phase N: <desc>` (no AI co-author trailer); push to `main`; print the commit hash.
4. **Global rules:** never a real network call at runtime; never a score without an evidence chain; never log raw PII; keep it laptop-runnable; explainable models only.
