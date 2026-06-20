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

| # | Phase                                     | Where                                 | Headline deliverable                                                                                                     |
|---|-------------------------------------------|---------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| 0 | Foundation, scaffolding, synthetic data   | repo-wide                             | ✅ Bootable skeleton + schemas + synthetic packets + mocks + verify guard                                                |
| 1 | Document Integrity / Forensics            | `services/forensics/`                 | `POST /forensics/analyze` → EvidenceItem[]; metadata + template fingerprint + tamper signals (any doc type)             |
| 2 | Semantic Consistency / Underwriting       | `forensics/` (OCR) + `risk/` (rules)  | OCR + extraction + cross-document rules across **financial AND legal/land** docs (+ extend generator with land/legal packets) |
| 3 | Anomaly + **Learned Risk Model**          | `services/risk/`                      | Isolation Forest **+ supervised, explainable classifier** + `train.py` + metrics (AUC / PR / confusion / feature importance) |
| 4 | Trust Score Aggregation & Evidence Chain  | `services/risk/`                      | `POST /risk/score` → blended TrustScore (rule weights ⊕ model probability) + evidence chain + recommendation             |
| 5 | Cross-Application Graph (differentiator)  | `services/risk/`                      | NetworkX graph incl. **property/title nodes** → fraud rings **and double-financed collateral**; persisted                  |
| 6 | Investigator Dashboard                    | `services/dashboard/`                 | Real-time upload → score + evidence chain + tampered-vs-clean + **model-metrics view** + collateral/cluster graph + exportable report |
| 7 | Privacy & trust layer                     | repo-wide                             | PII redaction in logs; on-premise statement in UI; `PRIVACY.md`                                                          |
| 8 | Demo script & narrative                   | repo-wide                             | `DEMO.md` 3-min story + staged packets (incl. a double-financing graph reveal) + `seed_demo.py`                          |

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

---

## 6. Production Roadmap / Future Work

Phases 0–8 are complete as a **demo on synthetic data**. This section captures what a **real-world**
deployment still needs, grounded in today's actual gaps. It is the backlog beyond the demo — nothing
here is required for the hackathon build, but it is the honest answer to "what would it take to ship
this to a bank?" The hard constraint stays: **everything runs locally; the system never calls an
external API** — so every capability below is either a local model we train or a local mock behind the
production-shaped adapter seam.

### Where we are today (the gaps this roadmap closes)
- **Ingestion** (`services/forensics/app/extractor.py`): embedded-PDF-text fast path + a Tesseract OCR
  fallback that is **never exercised** (all synthetic PDFs carry a text layer). Extraction is **brittle
  regex** keyed to one synthetic layout; `doc_type` is **handed in**, never inferred. No image (JPG/PNG)
  intake, no scan preprocessing, no table parsing, no multi-bank formats.
- **Forensics** (`analyzer.py`): PDF-structure signals (metadata, white-box rects, font set,
  duplicate images, incremental `%%EOF`, structural template hash) **plus a re-OCR vs text-layer
  cross-check (§6.D2 ✅) and tamper localization (§6.D3 ✅)** — render→OCR→compare catches whiteout
  edits independent of PDF structure, and findings now carry page+bbox regions with an annotated
  overlay. Still missing: true **pixel/image-level forensics** (ELA, copy-move, noise/JPEG-ghost) for
  a photographed/scanned forgery with no text layer (§6.D1).
- **Semantics** (`services/risk/app/rules.py`): income↔bank↔salary, name/PAN, owner↔applicant,
  property-id, LTV, valuation↔registry, EC↔CERSAI. No FOIR/affordability, transaction analytics,
  credit-bureau, title-chain, or identifier validation.
- **Models** (`features.py`/`train.py`): 16 hand features; IsolationForest on **10 clean** rows;
  GradientBoosting on **33 rows** that partly memorises (double-financing is separable only via a
  velocity artifact — see DECISIONS.md). No proper split, calibration, real SHAP, or CV models.
- **Data** (`data/generator/generate.py`): 33 deterministic, single-template, digital-born packets —
  too small/uniform to train real models (and the shared template is why 25 packets collide on one
  fingerprint).
- **Platform**: decisions not persisted; graph is a bare pickle; the dashboard scores **by packet-id**
  (no real upload / case management); no feedback loop, model registry, or auth/audit.

### A. Document ingestion & OCR
- **A1. Accept image uploads** (JPG/PNG/TIFF, multi-page) and **scanned/image-only PDFs**, not just text
  PDFs — detect image-only pages and route them to OCR.
- **A2. Scan preprocessing** (OpenCV, local): deskew, denoise, binarize/contrast, DPI normalize, auto-crop.
- **A3. Layout-aware OCR**: upgrade raw Tesseract to a local engine (PaddleOCR / docTR / EasyOCR) for
  tables and key-value regions; keep Tesseract as fallback.
- **A4. Document-type classifier**: infer `doc_type` from content so users can drop an unsorted folder.
- **A5. Layout/table extraction** to replace brittle regex: a bank-statement transaction-table parser +
  multi-format Form 16 / EC / valuation extractors.
- **A6. Extraction confidence + quality gate**: score each field; flag illegible/low-DPI/partial scans
  and request re-upload instead of silently extracting garbage.
- **A7. Multi-institution templates**: per-bank/per-employer format detection.

### B. Synthetic data generator v2 (the fuel for the ML models)
- **B1. Volume & parameterisation**: hundreds–thousands of randomised packets with a held-out
  **train/val/test** split.
- **B2. Layout variety**: several bank / Form 16 / EC / valuation templates so extraction and the
  template-fingerprint stop overfitting one layout (also fixes the 25-packet fingerprint collision).
- **B3. Scanned & image variants**: rasterise a fraction of docs to JPG/PNG/scanned-PDF with realistic
  scan noise (skew, JPEG artifacts, shadows, stamps) to actually exercise the OCR pipeline.
- **B4. Realistic bank statements**: multi-page transaction streams (salary, rent, EMIs, UPI, cash).
- **B5. Remove leakage artifacts**: give relational-only fraud (double-financing) **normal** submission
  velocity so it is genuinely per-packet-indistinguishable — forcing the graph (not an artifact) to
  catch it. Add **hard negatives** (clean-but-risky-looking: high legit LTV, legit repeat applicant).
- **B6. More fraud types** + labels with **fraud sub-type and affected region (bounding boxes)**:
  fabricated identity, fake-employer income inflation, circular salary funding, hidden EMIs, address
  fraud, recycled stamp/seal images, photoshopped scans, valuation collusion.

### C. ML models to train — all local, zero external API
Each capability maps to a concrete **offline-trainable** model and its training data:

| #  | Capability                       | Local model                                                  | Trains on                                           |
|----|----------------------------------|--------------------------------------------------------------|-----------------------------------------------------|
| C1 | Document-type classification     | TF-IDF + LogReg → DistilBERT / LayoutLMv3 (fine-tune)        | generator-v2 doc samples                            |
| C2 | Key-value & table extraction     | LayoutLMv3 / Donut, or a token CRF over OCR tokens           | B2/B3 layouts with field labels                     |
| C3 | Bank-statement txn categorisation| gradient-boosted / small text classifier                     | B4 transaction streams                              |
| C4 | Image-forgery detection (scans)  | CNN on ELA / noise residual; copy-move (keypoint) detector   | B3 tampered vs clean scans                          |
| C5 | Signature / seal verification    | Siamese CNN (same / different)                               | B6 seal & signature pairs                           |
| C6 | Supervised fraud classifier      | **XGBoost / LightGBM**, **calibrated** (isotonic/Platt) + **real SHAP** | B1 packets w/ proper splits                         |
| C7 | Genuine anomaly detection        | IsolationForest / autoencoder on **hundreds** of clean packets | B1 clean set                                        |
| C8 | Relational / graph ML            | node2vec / GNN embeddings + Louvain community detection      | the application graph                               |
| C9 | Legal-text NLP                   | local spaCy / transformer NER + clause flagging              | B-generated legal text                              |

Guiding constraint: **models train offline on synthetic data or the bank's own labelled history**; the
honest production handoff is *"retrain on real labelled outcomes, on-prem."* Replace the current
importance×value attribution with **real SHAP**, and **learn** the aggregation weights/thresholds rather
than hand-setting them.

### D. Forensics — deeper, generalisable
- **D1. Image / pixel forensics** for scans: Error-Level-Analysis, copy-move / splice detection, noise &
  JPEG-ghost analysis, resampling detection (catches forgeries with no PDF text layer).
- **D2. Re-OCR vs text-layer cross-check** ✅ *(done — `analyzer._check_reocr_mismatch`)*: render → OCR
  → compare to the embedded text; a mismatch exposes "visible value ≠ text-layer value" even when
  residue is cleaned — a strong, layout-independent signal. Evidence-only (excluded from the model
  feature vector to avoid train/serve skew). See DECISIONS.md (Phase 9).
- **D3. Tamper localization** ✅ *(done — `regions` on findings + `render_tamper_overlay` + dashboard
  panel)*: findings return page + bounding boxes of *where* the edit is, rendered as a UI overlay.
  (A full per-pixel heatmap remains future work, paired with §6.D1.)
- **D4. Stamp/seal & signature checks** (ties to C4/C5); PDF object-stream & font-subset deep forensics;
  producer/version-vs-claimed-date validation.

### E. Semantic / underwriting depth
- **E1. Affordability / FOIR**: detect existing EMIs from statements → compute FOIR/DTI (core underwriting).
- **E2. Bank-statement analytics**: salary regularity, bounced cheques, pre-application balance inflation,
  circular / mule patterns, average balance.
- **E3. Tax reconciliation**: Form 16 ↔ ITR ↔ AIS/26AS (mock), TDS consistency; GST turnover vs declared
  income for the self-employed.
- **E4. Identifier validators**: PAN checksum, IFSC, Aadhaar format, address consistency, DOB/age-vs-tenure.
- **E5. Property / legal depth**: chain-of-title across deeds, EC period-coverage gaps, property-tax
  receipt, approved plan / RERA; a **local mock credit-bureau (CIBIL-like)** for existing loans / DPD.

### F. Platform & production-readiness
- **F1. Persistence**: SQLite for applications, decisions, and an **immutable audit log** (graph
  SQLite-backed/versioned, not a bare pickle).
- **F2. Real upload & case management**: dashboard multipart upload → forensics → risk; queue, assign,
  status, reviewer notes (replaces the score-by-id demo flow).
- **F3. Human-in-the-loop feedback** → label store → **active-learning** retrain loop.
- **F4. Model ops**: model registry / versioning, drift monitoring, CI metric gates on the v2 test set.
- **F5. Auth / RBAC + audit**; batch / backlog scoring; config-driven thresholds (no magic numbers).
- **F6. Container hygiene**: pin scikit-learn to match the pickled models; bundle OCR (tesseract + lang
  data) in the images (the `./data` mount is already fixed).
- **F7. Redactor i18n**: extend PII patterns to Aadhaar / Voter-ID / GST / IFSC; field-level config.

### G. Explainability & compliance
- **G1. Real SHAP** attributions (local) replacing the approximation; confidence intervals on scores.
- **G2. Tamper-localization heatmaps** surfaced in the UI.
- **G3. Reason-code → policy mapping; STR/SAR-style regulatory export**; basic bias / fairness checks
  (no protected-attribute proxies).

### Priority tiers
- **P0 — makes it real:** A1–A3 (image/scan OCR), A4–A5 (classify + table extract), B1–B3 (data volume +
  scanned variants), ~~D2 (re-OCR cross-check)~~ ✅, C6 (calibrated classifier + SHAP), F1–F2
  (persistence + real upload).
- **P1 — depth & trust:** B4–B6, C1–C4, C7, D1, ~~D3~~ ✅, E1–E3, F3.
- **P2 — scale & compliance:** C5/C8/C9, D4, E4–E5, F4–F7, G1–G3.

---

## 7. Real-document delivery — 2-week sprint (SUPERSEDED by §10 for now; content still valid backlog)

> **Note:** the timeline/staffing here (2 weeks, 2 builders) is **superseded by §10** (solo, 7-day
> hackathon sprint focused on edit-detection). The *content* below — real-doc collection, generator-v2,
> the per-model training table, dataset downloads — remains the **post-hackathon backlog**, not dropped.

**Status:** Phases 0–9 complete (synthetic pipeline + D2/D3 forensics, Dockerised). **M0** done — the
real-document collection kit (`data/real/`, gitignored; see [data/real/README.md](data/real/README.md)).
This section is the **active execution plan** to make TrustShield read **real Indian documents**.

**The unlock:** the five analysis layers consume the `ExtractedEntities` contract
([shared/schemas/models.py](shared/schemas/models.py)), *not* raw documents. Only the
ingestion/extraction **front-end** is coupled to synthetic data. Rebuild that front-end to emit the same
`ExtractedEntities` from real docs and the five layers (rules, model, aggregator, graph) work unchanged.

**Locked scope:** real set (team-supplied) + synthetic **generator-v2** + public datasets · heavier local
models allowed · **financial + KYC first** · local **NVIDIA GPU, 8 GB** · **2 builders** · **~2-week**
deadline · **demo-grade** bar (reads/classifies/scores the docs brought on stage, live). **Honesty:** real
fraud *labels* don't exist for us → the **fraud model trains on synthetic data**; real docs **validate
extraction**, not fraud detection. Production answer = "retrain on the bank's labelled outcomes."

### 7.1 Documents to collect (per [data/real/README.md](data/real/README.md))
| Document | Format | Fields extracted | Feeds |
|---|---|---|---|
| **PAN card** | photo / PDF | name, PAN, DOB | KYC; PAN structure check; name↔PAN cross-match |
| **Aadhaar (MASKED only)** | photo / PDF | name, masked Aadhaar, DOB, address | KYC; **Aadhaar Verhoeff checksum**; name match |
| **Form 16** (Part A+B) | PDF (TRACES) | name, PAN, employer, gross income, TDS, FY | income, tax, name/PAN consistency |
| **Salary slip** | PDF | name, employer, net monthly pay | income corroboration |
| **Bank statement** (6 mo) | PDF (often password) | holder, account, salary credits, balances | income-vs-credits, FOIR, regularity |
| *(opt)* **ITR-V / 26AS / AIS** | PDF | declared income, TDS, reported income | tax reconciliation |
| *(later)* sale deed, EC, valuation, legal opinion | scan/PDF | owner, property-id, charges, valuation | collateral/title (post-sprint) |

Target **5–10 of each Priority-1 type**, mix of clean PDFs + phone photos/scans, ≥2 issuers/banks each;
plus **2–3 deliberately-`_TAMPERED`** copies for forensics. English-first; Indic OCR deferred with legal docs.

### 7.2 Per-model training (local, 8 GB GPU; weights baked locally — no runtime network)
| Component | Model | Trains on |
|---|---|---|
| OCR + tables | PaddleOCR PP-OCRv4 + PP-Structure | pretrained — no training (Tesseract `app/ocr.py` fallback) |
| Doc-type classifier | wk1 TF-IDF+LogReg → wk2 LayoutLMv3-base | generator-v2 + real set; bootstrap RVL-CDIP/FUNSD |
| Key-value extractor | wk1 heuristic label-anchored → wk2 LayoutLMv3-base KV | generator-v2 bbox-labeled fields; real-set validation |
| Bank-statement tables | PP-Structure + rules | heuristic |
| Image-forgery detector | EfficientNet/ResNet CNN (ELA + noise) | **DocTamper** (170k) + team `_TAMPERED` docs |
| Identifier validators | deterministic (no ML) | PAN structure, Aadhaar Verhoeff, IFSC |
| Fraud/risk model | GradientBoosting/XGBoost (existing) | synthetic generator-v2 (splits + calibration + SHAP) |

### 7.3 Sprint — Person 1 (pipeline/code, with the AI) ∥ Person 2 (data + GPU training)
**The 8 GB GPU lives on Person 2's machine, so all dataset work and model training is Person 2's lane;
Person 1 builds the pipeline + the training scripts + integrates the returned weights.**

**Person 2 — data & GPU training (owns the GPU):**
- **P2-1 (d1–3, start now):** document-collection drive → `data/real/` per the README (passwords noted;
  2–3 `_TAMPERED` copies). **Request DocTamper access on day 1** — it is gated (email an education
  address for the password), so allow lead time.
- **P2-2 (d1–4):** download datasets + weights (see §7.4); gather public layout references (IT-portal
  Form 16, 2–3 banks' sample statements, PAN/Aadhaar) to inform generator-v2.
- **P2-3 (d6–11):** run GPU training using Person 1's scripts — (1) image-**forgery CNN** on DocTamper
  (+ team `_TAMPERED`), (2) **LayoutLMv3-base** doc-type + KV on generator-v2, (3) optional risk-model
  retrain (calibration + SHAP). Commit/share the resulting weights for Person 1 to wire in.
- **P2-4 (d5–14):** manual validation of real docs through the demo (log wrong fields per doc type) +
  demo script/slides ("synthetic-trained / real-validated" narrative).

**Person 1 — pipeline & integration (CPU dev, with the AI):**
- **Week 1 — heuristic real-document demo:** `services/forensics/app/ingest/`
  (`loader`/`preprocess`/`ocr_engine`/`classify`/`normalize` + `extract/{form16,salary_slip,bank_statement,
  pan,aadhaar}.py`) → `POST /forensics/ingest` → existing `POST /risk/score`; dashboard drag-drop upload +
  KYC panel + confidence. **Milestone:** upload real Form 16 + salary slip + bank statement + PAN + masked
  Aadhaar → doc-type + fields + KYC validation + trust score, live (pretrained PaddleOCR + heuristics — no
  GPU needed).
- **Week 2 — enable deep models:** build **generator-v2** (realistic layouts, scan/photo variants, bbox
  labels, splits) + write the **training scripts** (`train_forgery_cnn.py`, `train_layoutlm.py`, risk
  retrain) for Person 2 to run; **integrate** the returned weights behind the heuristic fallbacks; polish.
- The final live demo can run on Person 2's GPU box (fast) or on CPU (slower, fine for a few docs).

**If time slips, priority:** wk1 heuristic demo → forgery CNN → LayoutLMv3 KV (heuristic extraction alone
meets the demo-grade bar, so the trained models are upside, not blockers).

### 7.4 Datasets & model weights to download (Person 2)
| What | Source | Size | Why / note |
|---|---|---|---|
| **LayoutLMv3-base** | HF `microsoft/layoutlmv3-base` | ~0.5 GB | base weights to **fine-tune** (doc-type + KV extractor) |
| **PaddleOCR PP-OCRv4** (det+rec) | auto on first use / PaddleOCR repo | ~tens of MB | **pre-cache for offline** OCR (no runtime download) |
| **torchvision backbone** (EfficientNet-B0 / ResNet, ImageNet) | torchvision auto | small | forgery-CNN backbone |
| **DocTamper** (170k tampered images) | [github.com/qcf-568/DocTamper](https://github.com/qcf-568/DocTamper) → Baidu/Kaggle | large (multi-GB) | forgery-CNN training. **GATED — email an education address for the password; request on day 1.** Fallback if unavailable: heuristic **ELA / copy-move** (needs no dataset). |
| *(optional)* FUNSD | HF `nielsr/funsd` / guillaumejaume.github.io/FUNSD | ~17 MB | tiny KV reference for LayoutLM |
| *(skip)* RVL-CDIP | HF `aharley/rvl_cdip` | ~37 GB | **not needed** — doc-type trains on generator-v2's own classes |

All weights are pre-downloaded and baked into the local cache/images — **runtime makes no network call**
(preserves the local-only contract + `verify_local_only.py`).

---

## 8. Web app & roles (DONE — multi-page product with auth)

Turned the single-page investigator console into a routed product with **real auth** and **two roles**.

- **Backend (risk service, v7.0.0):** `app/db.py` (stdlib SQLite — users / cases / case_docs; gitignored;
  the audit trail = roadmap F1), `app/auth.py` (PBKDF2 password hashing + JWT; `/auth/register|login|me`;
  `current_user` + `require_admin` guards), `app/cases.py` (`POST /cases`: user uploads files + purpose →
  `ingest_document` per doc → synthesize a manifest with **neutral timestamps** → score via
  `aggregator.score_packet_dir` → persist; `GET /cases` user-own/admin-all; `GET /cases/{id}` owner/admin),
  `app/overlays.py` (shared §6.D3 tamper-overlay builder). Deps: PyJWT + python-multipart.
- **Frontend (react-router):** Home (project + 5-layer explainer), About/Team, Sign in/up,
  UserDashboard (purpose + upload → result + "My submissions"), AdminDashboard (review queue),
  CaseDetail (full analysis). `auth.jsx` (JWT context) + `ProtectedRoute`; reusable `DecisionView`
  refactored out of the old console.
- **Honesty:** real-upload scoring leans on forensic + semantic + KYC; the synthetic-only
  behavioural/velocity features are neutralized for uploads (the fraud model stays synthetic-trained).
- **Verified:** 165 tests pass (auth + cases + ingestion + existing); live HTTP smoke (register/login/
  guard/upload→score/admin-list); `npm run build` clean; `verify_local_only` passes (SQLite/JWT local).
- **Auth/case data is gitignored** (`services/risk/app_data/`, `services/risk/case_store/`).

> Order: web app first (done); **resume §7 Part B (generator-v2 + Person-2 GPU training)** next.

## 9. Real-document KYC + underwriting (DONE — verify the applicant, not just the file)

The pivot that makes TrustShield work like a bank: it now verifies **the applicant against the
process** (is the right document set present, is identity & address established, does income
reconcile, can the applicant afford the loan), not only "was this PDF edited." Two axes are kept
**separate**: *authenticity* (the trust score) and *eligibility* (FOIR/affordability). Genuine
documents can still be REFER/DECLINE on affordability — and that reads as such, never as "fraud."

**Final-product vision.** Given an applicant's documents for a stated purpose, return: (1) a
**completeness** verdict, (2) an **authenticity/trust** score (forensics, existing), (3) a **KYC**
verdict (identity & address established, names/PAN/Aadhaar consistent, no fraud-ring via the graph),
and for loans (4) an **underwriting** verdict (income reconciled, FOIR, max-eligible amount, LTV →
ELIGIBLE / REFER / DECLINE) — each with an evidence chain + recommended action.

### 9.1 Scope (locked)
KYC verification + **salaried** personal loan. Home-loan/LAP collateral (LTV is wired but its docs
aren't collected) and self-employed/business income are documented as **later tiers**.

### 9.2 Indian KYC / loan reference (what a bank actually requires)
- **KYC — Officially Valid Documents.** *POI* (proof of identity): PAN (mandatory for financial txns),
  Aadhaar, passport, voter ID, driving licence. *POA* (proof of address): Aadhaar, passport, voter ID,
  DL, utility bill ≤2 months, bank statement. KYC is **established** when a valid POI **and** a POA are
  present, the **name is consistent** across them, identifiers validate (PAN structure + holder-type;
  Aadhaar Verhoeff/masked-format), and there is no duplicate-identity signal (cross-application graph).
- **Salaried personal loan.** KYC set + **3 months salary slips** + **Form 16** + **6-month bank
  statement** (optional ITR/26AS/AIS). Underwriting we replicate deterministically:
  - **Income reconciliation:** Form 16 gross ↔ banked salary (×12) ↔ salary-slip — flag material
    divergence (inflated income / forged slip).
  - **Affordability / FOIR:** (existing + proposed EMI) / net monthly income ≤ 0.50 → ELIGIBLE;
    (0.50, 0.60] → REFER; > 0.60 → DECLINE. **Max-eligible** amount from net income, assumed rate
    (10.5% p.a.) and tenure (default 60 mo). **LTV** ≤ 0.80 only when collateral is present.
- **Honesty:** these KYC/underwriting verdicts are **deterministic rules (no ML)**, so they work on
  real documents on day one; the *forgery* model stays synthetic-trained (no real fraud labels exist).

### 9.3 What was built
- **Backend (risk):** `app/profiles.py` (purpose → required/optional slots; one source of truth for
  completeness **and** the upload form, served at `GET /cases/profiles`); `app/underwriting.py`
  (`check_completeness`, `verify_kyc`, `reconcile_income`, `assess_affordability`, `build_verification`
  — all constants documented); `aggregator.apply_verification` (folds completeness/KYC/income findings
  into the trust score by a **capped** penalty — never a tank; eligibility excluded). `POST /cases` now
  takes per-file `doc_types` slot hints + `tenure_months`/`existing_emi`, runs verification, persists a
  `verification_json` block, and returns it alongside the decision. `db.py` migrated additively.
- **Forensics ingest:** new `address_proof` doc type (classifier keywords + `_extract_address_proof`);
  schema gains `DocType.ADDRESS_PROOF`.
- **Frontend:** purpose-driven **named upload slots** (dynamic from `GET /cases/profiles`) + loan
  amount/tenure/existing-EMI; a **Verification panel** in `DecisionView` (completeness checklist, KYC
  card, income, eligibility/FOIR) shown on the user result and the admin CaseDetail.
- **Model store + seam:** downloads organized under gitignored **`models/`** with a committed registry
  (`REGISTRY.md` + `registry.json`); `ingest/model_registry.py` resolves local assets and **falls back
  to heuristics** when absent (no torch/transformers in the runtime; Docker unchanged).

### 9.4 Model & data file structure
```
models/   (gitignored; only REGISTRY.md + registry.json committed)
  layoutlmv3-base/         doc-type + KV extractor (Person-2 fine-tune)
  doctamper/{code,data}    forgery CNN: Swin + trained .pk checkpoints; 22 GB LMDB training data
  paddleocr/{src,weights}  optional OCR upgrade (weights absent → Tesseract is live)
data/reference/funsd/      tiny KV reference (parquet)
data/real/                 real applicant docs (gitignored) — see data/real/README.md, organized by
                           slot: kyc/{pan,aadhaar,address_proof}, salaried_loan/{salary_slip,form16,
                           bank_statement,itr}, _tampered/
```
> **torchvision backbone not needed** — DocTamper ships its own Swin backbone + checkpoints.
> **PaddleOCR weights** absent (Tesseract is the live OCR). **DocTamper dataset** already on disk
> (LMDB); its gated password was only needed to obtain it.

### 9.5 Improvements ledger
- **Done:** real-document ingestion (M1); web app + roles (§8); re-OCR + tamper localization (§6.D2/D3);
  **this** KYC + underwriting verification layer + purpose-driven upload + model registry/seams.
- **To-do (behind the seams / later tiers):** Person-2 GPU models wired behind the fallbacks
  (DocTamper forgery CNN, LayoutLMv3 doc-type + KV) — flips `live:true` in `registry.json`;
  PaddleOCR PP-OCRv4 weights pre-cache; scan/photo preprocessing (deskew/contrast) for phone photos;
  home-loan/LAP (collateral + LTV) and self-employed/business tiers; mock CIBIL/credit-bureau + richer
  dedup; generator-v2 (realistic layouts, bbox labels, splits, calibration + SHAP).

## 10. Hackathon sprint (7 days, SOLO) — edit-detection is the hero (ACTIVE)

After a Q&A with the organizers, the judges' problem is explicit and narrow: **users edit documents —
digital and scanned/photographed — and it's hard to tell IF a document was edited and WHAT was
edited.** Local LLMs are allowed; synthetic data is allowed. This section is the **single source of
truth for the remaining 7 days**, run by one person. It reprioritises the project around that problem.

### 10.0 Win condition (what the demo must do)
Upload a document (PDF **or** a phone photo/scan of, e.g., an Aadhaar/PAN), **edit a number yourself**
in any image editor, and TrustShield: (1) flags it as **edited**, (2) **localizes** the change (box/
heatmap on the exact region), (3) **explains** it in plain English — all **100% local**. Stretch:
a learned model corroborates. Floor (still a win per the judges): "at least a good idea" with a
working baseline on a doc the judge edits live.

### 10.1 Positioning / reframe
- **Hero = detect + localize + explain edits**, including scans/photos with no text layer. This is the
  defensible moat (forensics + cross-application graph), not the commodity layer.
- The existing **5 analysis layers stay as depth**; the demo *opens* with edit-detection.
- **De-emphasise underwriting (FOIR/KYC completeness)** — keep the §9 backend, but it is *not* the
  story. The **frontend was reverted** to the simple single-page investigator console (packets list +
  full result panel; commit `66d9165`'s multi-page app retired — recoverable from git). The live
  "upload & edit" panel is added to that simple console on Day 5.

### 10.2 How this maps to the existing plan (not new scope — the missing piece)
- This completes **§6.D1 (image/pixel forensics for scans)** + **§6.C4 (image-forgery model)** — the
  one forensic gap left. **§6.D2 (re-OCR cross-check)** and **§6.D3 (tamper localization)** are already
  done, but they only catch **PDF text-layer** edits. §10 adds the **image/photo** path (no text layer).

### 10.3 Decisions on the open questions
- **DocTamper models without the dataset → YES.** The dataset is only for *training*; inference needs
  just the model code + a pretrained checkpoint (`models/doctamper/code/` + `pks/*.pk`) + torch. We run
  **DTD inference** to produce a learned tamper mask. It lives **behind the `model_registry` seam**
  (no torch in the slim runtime images; runs on the 8 GB GPU or CPU). **Fallback:** classic image
  forensics (10.4) if it won't load in its time-box. *Risk:* JPEG-only input + a quantization table
  (`qt_table.pk`) need wrangling — budget ≤1 day, else ship the baseline.
- **Synthetic + hand-edited tamper dataset → YES, and it removes the DocTamper-access blocker.**
  *Programmatic* tampering (rasterise clean synthetic docs → edit pixels in code: digit-swap, copy-move,
  splice) yields a **ground-truth mask** → a measurable localization accuracy and hundreds of examples.
  *Hand-edited* (Photoshop/Paint) — a handful — proves generalisation and powers the **live demo**.
- **Local LLM → explainer/reader, NEVER the verdict.** Use a local model (Ollama) to (a) turn forensic
  findings into a plain-English "what changed & why we think so" narrative + investigator Q&A, and
  optionally (b) a local **VLM** (Qwen2-VL / MiniCPM-V / LLaVA) as a second reader for messy scans. The
  detector stays deterministic; the LLM explains and reads — it cannot produce the fraud verdict
  (LLMs hallucinate). *Local-only caveat:* Ollama is `localhost:11434` (allowed host), but
  `verify_local_only.py` flags any `httpx/requests/fetch` call pattern regardless of host — so either
  load the model **in-process** (llama-cpp/transformers) or add a **documented localhost allowance** to
  the scanner on Day 4 (decide then; default to in-process to keep the guard strict).

### 10.4 Architecture additions (where the code lands)
- **`services/forensics/app/image_forensics.py`** (NEW, pure-local, the always-works baseline):
  Error-Level Analysis (ELA), noise/variance residual map, **copy-move** (ORB/SIFT keypoint match),
  JPEG double-quantisation / ghost, resampling, and **EXIF/software-trace** ("Adobe Photoshop" in
  metadata). Output: a **per-region score + heatmap + bounding boxes** → emitted as `forensic`
  `EvidenceItem`s with `regions` (reuses the §6.D3 overlay renderer in `analyzer.render_tamper_overlay`
  / `overlays.py`). Deps: Pillow + numpy + opencv (CPU, fast).
- **Image intake (§6.A1):** accept `JPG/PNG/TIFF` + image-only PDFs in `ingest/loader.py`; route
  image-only pages to OCR (`app/ocr.py`, Tesseract) **and** to `image_forensics`. Light preprocessing
  (deskew/contrast/auto-crop) for phone photos.
- **DocTamper DTD adapter** (NEW, behind `ingest/model_registry.py`): `resolve_model("doctamper-code")`
  + a checkpoint → run DTD → tamper mask → same `EvidenceItem`/overlay shape. Absent/torch-missing →
  the baseline runs (the seam already degrades to heuristics).
- **`data/generator/` extension** (`tamper_image.py` + an eval harness): rasterise clean docs to images;
  programmatic pixel tampers with ground-truth masks; a small clean/tampered split + an IoU/detection
  metric in `tests/`.
- **Local LLM explainer** (NEW module, optional): findings → narrative + Q&A. In-process or localhost
  (see 10.3 caveat). Strictly explanation; verdict stays deterministic.
- **Frontend (simple console):** Day 5 adds an **"Upload & analyze" panel** to `App.jsx` — drop a file →
  POST to a forensics endpoint → render the **annotated heatmap/box image** + evidence + LLM
  explanation. No routing, no auth (keep it the simple console the judges see).

### 10.5 The 7-day plan (day-by-day; each day ends demoable)
| Day | Deliverable | Acceptance check |
|----|-------------|------------------|
| **1 ✅** | `image_forensics.py` baseline (ELA + copy-move + noise + JPEG-ghost + EXIF) → score + heatmap + boxes; accept JPG/PNG uploads through ingestion. | DONE — `POST /forensics/analyze-image` (v1.3.0); clean → CLEAN, edited → EDITED + boxed; 4 tests. |
| **2 ✅** | Synthetic **tamper-image dataset** (rasterise + scan-sim + programmatic edits + masks) + eval harness; results stored. | DONE — `results/image_forensics/`: **detection precision 1.0 (0 FP on clean)**, localization IoU 0.84–0.86 on paint/splice; dashboard image panel + examples; bind-mounted dashboard. |
| **3** | **DocTamper DTD inference** behind the `model_registry` seam (primary localizer if it loads; baseline fallback). Also closes the copy-move gap (deferred from Day 2). | DTD produces a mask on a sample image **or** the seam cleanly falls back to the baseline (no crash). |
| **4** | **Local LLM explainer** (Ollama or in-process) over findings + investigator Q&A; optional VLM reader; resolve the `verify_local_only` localhost decision. | Findings render as a plain-English paragraph; `verify_local_only.py` still passes. |
| **5** | **"Upload & analyze" panel** on the single-page console: upload → detect → **annotated overlay** + evidence + explanation. | End-to-end in the browser: upload an edited image → boxed region + explanation appear. |
| **6** | **Your real docs:** run your own (self-edited) Aadhaar/PAN; tune preprocessing for phone photos; reduce false positives (JPEG-recompression). | A digit you edit in your own Aadhaar is detected + localized; a clean copy passes. |
| **7** | **Story + slides + buffer:** problem → local multi-signal detection + localization + explanation → live demo → "and 4 more layers underneath (semantic / model / cross-application graph)." | A rehearsed 3–5 min demo + slide deck; fallbacks ready if a laptop/model misbehaves. |

**Priority if time slips:** Day 1–2 (baseline + accuracy) > Day 5 (upload UI) > Day 6 (own docs) >
Day 4 (LLM) > Day 3 (DTD). The first two days alone give a real, working, judge-facing prototype.

### 10.6 Degradation order (nothing is all-or-nothing)
`image_forensics` baseline (guaranteed, pure-Python) → re-OCR/D3 text-layer check (done) → DocTamper
DTD (if it loads) → LLM explanation (if Ollama/in-process model present). Each higher layer is additive
and optional; the demo stands on the baseline alone.

### 10.7 Honesty / risks to state in the pitch
- Image forensics has **false positives** on heavily recompressed/screenshotted images — the synthetic
  eval set is used to tune thresholds, and the LLM explanation hedges ("consistent with editing"
  vs "edited"). Be candid that production needs the labelled DocTamper training + on-prem retrain.
- The LLM **explains, never decides** — the verdict is the deterministic forensic score.
- Everything stays **100% local** — the entire pitch ("no document leaves the building") depends on it;
  any LLM runs on `localhost`/in-process and `verify_local_only.py` must keep passing.

### 10.8 Reconciliation with the earlier backlog (nothing is dropped — just resequenced)
§10 is a **focused slice** of the existing §6/§7/§9.5 roadmap, not a replacement. Mapping:

**Pulled INTO the 7 days (the judge-relevant subset):**
- **§6.D1** image/pixel forensics (ELA/copy-move/noise/JPEG-ghost) → Day 1.
- **§6.C4** image-forgery model (DocTamper DTD inference) → Day 3.
- **§6.A1/A2** image/scan intake + scan preprocessing → Days 1 & 6.
- **§6.B3/B6** scanned/tampered synthetic variants + region/mask labels → Day 2.
- **New (not previously planned):** local-LLM explainer/reader → Day 4.

**Deferred but STILL TRACKED (remain in §6/§7/§9.5; resume after the hackathon):**
- **§6.A3/A5** layout-aware OCR (PaddleOCR weights) + table extraction; **§6.C1/C2** LayoutLMv3
  doc-type + key-value extraction; **§6.C6** calibrated classifier + real SHAP; **§6.B1/B2**
  generator-v2 volume/layout variety + train/val/test splits.
- **§7** full real-document **collection drive** + the per-model training table + the 2-builder/GPU lane.
- **§9** later tiers: **home-loan/LAP** (collateral + LTV), **self-employed/business** income, **mock
  CIBIL/credit-bureau** + richer dedup. The §9 KYC/underwriting layer that *is* built stays in the
  backend (just not the demo's focus).

**Already DONE earlier (kept, used as depth in the demo):** §6.D2 re-OCR cross-check, §6.D3 tamper
localization + overlays, the 5-layer pipeline (forensic/semantic/model/aggregator/graph), §9 KYC +
underwriting backend. The §10 demo opens on edit-detection and shows these as the layers underneath.
