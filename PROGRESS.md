# TrustShield — Progress

Resume protocol: read [`plan.md`](plan.md) then this file; continue from the first unchecked phase.

| ✓ | Phase | Title | Completed (date) | Commit |
|---|---|---|---|---|
| ☑ | 0 | Foundation, scaffolding, synthetic data | 2026-06-13 | `1d1f573` |
| ☑ | 1 | Document Integrity / Forensics | 2026-06-14 | `8c2f043` |
| ☑ | 2 | Semantic Consistency / Underwriting | 2026-06-14 | `75bcfc9` |
| ☑ | 3 | Anomaly & Behavioral Scoring | 2026-06-14 | `3889fa6` |
| ☑ | 4 | Trust Score Aggregation & Evidence Chain | 2026-06-14 | `b72d357` |
| ☑ | 5 | Cross-Application Graph | 2026-06-14 | `20a9cf4` |
| ☑ | 6 | Investigator Dashboard | 2026-06-14 | `6e5967b` |
| ☑ | 7 | Privacy & trust layer | 2026-06-14 | `23e3fd2` |
| ☑ | 8 | Demo script & narrative | 2026-06-14 | `5a9ef2c` |
| ☑ | 9 | Forensic/OCR depth — re-OCR cross-check + tamper localization (§6.D2/D3) | 2026-06-14 | `3e36c22` |

## Phase notes

### Phase 0 — Foundation, scaffolding, synthetic data ✅ (2026-06-13)
Delivered: full folder tree with CLAUDE.md everywhere; root docs (plan/README/PROGRESS/DECISIONS); docker-compose booting forensics+risk+dashboard with `/health`; shared Pydantic schemas; synthetic data generator (clean + every fraud type) + `labels.json`; mock external-verification adapters (zero network); `scripts/verify_local_only.py`; pytest suite.

**Verified checks:**
- `docker compose up` → all 3 containers report **(healthy)**; `/health` returns 200 on 8001 (forensics) & 8002 (risk); dashboard serves on 5173. Responses: `{"status":"ok","service":"forensics"...}`, `{"status":"ok","service":"risk"...}`.
- Generator produced **24 packets** (8 clean + 16 fraud) covering all 9 fraud types + valid `labels.json`.
- `verify_local_only.py` → **PASS** (31 source files scanned, 0 violations; negative-tested to confirm it bites).
- `pytest tests/` → **17 passed**.
- Every required folder has a non-empty CLAUDE.md.

### Phase 1 — Document Integrity / Forensics ✅ (2026-06-14)
Delivered: `services/forensics/app/analyzer.py` — DocumentAnalyzer with 5 forensic checks
(metadata/suspicious-producer/date anomalies, white-box edit detection, font inconsistency,
duplicate-image copy-paste, incremental-update / multiple-%%EOF); structural template fingerprint
hash (producer + fonts + image/drawing counts per page). `POST /forensics/analyze` (file upload) +
`POST /forensics/analyze/path` (local path). Updated requirements.txt (PyMuPDF). 12 new tests.

**Verified checks:**
- Precision/recall vs labels.json: **TP=10, FN=0, FP=0** across all 33 packets / per-document
  forensic signal types (suspicious_metadata, edited_income_figure, font_inconsistency,
  copy_paste, incremental_update, forged_title, tampered_encumbrance, timestamp_anomaly with
  future/reversed dates).
- Template fingerprint: 4 template-reuse ring packets share one fingerprint on form16.pdf;
  clean-packet fingerprints all differ (different producer key).
- `verify_local_only.py` → **PASS** (33 source files, 0 violations).
- `pytest tests/` → **33 passed**.

### Phase 2 — Semantic Consistency / Underwriting ✅ (2026-06-14)
Delivered:
- `services/forensics/app/extractor.py` — per-doc-type entity extraction (embedded text fast path,
  Tesseract OCR fallback). Extracts income, PAN, employer, property_id, owner_name, valuation, etc.
- `services/risk/app/rules.py` — cross-document rules engine: income vs bank vs salary slip,
  name/PAN consistency, owner vs applicant, property ID consistency, LTV sanity, valuation vs
  property registry, EC vs CERSAI charge cross-check.
- `services/risk/app/main.py` — `POST /risk/rules/check` orchestration endpoint.
- `shared/mocks/property_registry.py` + `fixtures/property_registry.json` — state property
  registry mock for valuation inflation detection.
- 20 new tests in `tests/test_rules.py`.

**Verified checks:**
- Entity extraction spot-checked on ≥5 packets per doc type: form16, bank_statement,
  sale_deed, encumbrance_certificate, property_valuation.
- Every cross_document_inconsistency packet → ≥1 semantic finding.
- Every tampered_encumbrance → EC-vs-CERSAI critical finding.
- Every valuation_inflation → registry cross-check + LTV-vs-market critical findings.
- Every property_mismatch → property ID inconsistency finding.
- All 10 clean packets → 0 semantic findings.
- `verify_local_only.py` → **PASS** (37 source files, 0 violations).
- `pytest tests/` → **53 passed**.

### Phase 3 — Anomaly + Learned Risk Model ✅ (2026-06-14)
Delivered:
- `services/risk/app/features.py` — 16-feature vector from Phase 1 forensics + Phase 2 semantic
  rules + behavioral/temporal PDF metadata signals (velocity, timestamp spread, doc count).
- `services/risk/train.py` — offline training: Isolation Forest (clean-only, novelty detection) +
  GradientBoostingClassifier (supervised, all 33 packets). Saves models + metrics to
  `services/risk/models/`.
- `services/risk/app/scorer.py` — lazy-loading inference wrapper: `score_packet(pkt_dir)` returns
  `anomaly_score`, `fraud_probability`, `feature_vector`, `feature_attributions`.
- 22 new tests in `tests/test_anomaly.py`.

**Verified checks:**
- Feature extraction: 33 packets × 16 features, no NaN/Inf.
- Clean packets: 0 forensic, 0 semantic, velocity ~168h, all_docs_same_timestamp=0.
- Behavioral-velocity ring (PKT-0018): velocity=0.33h, all_docs_same_timestamp=1 ✓.
- Future-date packet (PKT-0023): creation_before_submission=0 ✓.
- GBC ROC-AUC (5-fold CV): **0.9696** (target >= 0.80) ✓.
- Confusion matrix: TN=10, FP=0, FN=1, TP=22.
- FN=1 is a double_financing packet (no per-packet signal; Phase 5 graph closes the gap).
- Top feature: `submit_velocity_hours` (0.49) → behavioral ring detected by velocity alone.
- `verify_local_only.py` → **PASS** (41 source files, 0 violations).
- `pytest tests/` → **75 passed**.

### Phase 4 — Trust Score Aggregation & Evidence Chain ✅ (2026-06-14)
Delivered:
- `services/risk/app/aggregator.py` — blends forensic + semantic + learned-model signals into a
  0–100 `TrustScore` with explicit documented weights (model 0.55 / forensic 0.25 / semantic 0.15
  / IF 0.05). Assembles an ordered, deduplicated evidence chain (incl. the model verdict + feature
  attributions) and a `Recommendation` with documented thresholds.
- `services/risk/app/main.py` — `POST /risk/score` main orchestration endpoint (Phase 1→4) +
  VERSION 4.0.0.
- `compute_features()` refactored to accept an in-memory manifest (API path, no manifest.json).
- 21 new tests in `tests/test_scoring.py`.

**Verified checks:**
- End-to-end vs labels.json: **TP=23, FP=0, TN=10, FN=0** (every clean approves, every fraud flagged).
- Recommendation bands: per-document fraud (forensic/semantic evidence) → **FREEZE** (trust 18–39);
  behavioral-only & double_financing (no document evidence) → **MANUAL_REVIEW** (trust ≈ 43), routed
  to the Phase 5 graph; clean → **APPROVE** (trust 97–99).
- CRITICAL findings (tampered EC vs CERSAI, valuation inflation) cap trust at 25 → freeze.
- "No freeze without document evidence" safeguard verified (double_financing → review, not freeze).
- Every decision carries a non-empty evidence chain (contract enforced).
- `verify_local_only.py` → **PASS** (43 source files, 0 violations).
- `pytest tests/` → **96 passed**.

### Phase 5 — Cross-Application Graph ✅ (2026-06-14)
Delivered:
- `services/risk/app/graph.py` — `ApplicationGraph` (NetworkX): per-packet upsert of app/pan/
  employer/property/template nodes; hub suppression; `collateral_clusters()`, `employer_rings()`,
  `graph_evidence_for()`, `subgraph_for()`, pickle persistence, `build_from_packets()`.
- `services/risk/app/aggregator.py` — graph evidence folded in as an additive risk overlay
  (`GRAPH_OVERLAY_WEIGHT=0.5`) + CRITICAL graph escalation; `score_packet_dir(graph=…)`.
- `services/risk/app/main.py` — `POST /risk/graph/upsert`, `GET /risk/graph/clusters`,
  `GET /risk/graph/subgraph/{id}`, and `use_graph` on `POST /risk/score`. VERSION 5.0.0.
- 21 new tests in `tests/test_graph.py`.

**Verified checks:**
- Template/employer-reuse ring: QuickCash → 4 distinct PANs + shared template, exactly PKT-0018–21.
- Double-financed collateral: SY-911/2C → cluster across PKT-0029/31/32/33.
- Unrelated packets stay unlinked: the 25-packet default template is hub-suppressed; clean PKT-0001
  gets only an INFO repeat-applicant note.
- Subgraphs small (5–7 nodes) + fast.
- Graph-informed scoring: ring (PKT-0018–21) and double-financing (PKT-0031–33) escalate from Phase-4
  manual_review → **FREEZE** (trust ~13); all 10 clean packets stay **APPROVE**.
- `verify_local_only.py` → **PASS** (45 source files, 0 violations).
- `pytest tests/` → **117 passed**.

### Phase 6 — Investigator Dashboard ✅ (2026-06-14)
Delivered:
- Backend demo endpoints (`services/risk/app/main.py`): `GET /risk/demo/packets`,
  `POST /risk/demo/seed`, `POST /risk/demo/score/{id}` — score the committed synthetic packets by id
  (the browser can't hand local file paths to the backend) and return decision + subgraph.
- React investigator console (`services/dashboard/src/App.jsx` + `api.js` + `GraphView.jsx`):
  packet picker with ground-truth chips, trust gauge, recommendation badge + rationale, forensic/
  semantic/model sub-score bars, severity-colored evidence chain, cross-application graph SVG viz,
  and an "export evidence report (JSON)" button. Keeps the live service-health + on-premise banner.
- 6 new backend tests in `tests/test_demo_api.py`.

**Verified checks:**
- `npm run build` compiles clean (34 modules, ~50 kB gzipped).
- Demo endpoints over real HTTP (uvicorn :8002): 33 packets listed; seed → 1 ring + 3 collateral
  clusters; PKT-0031 → trust 12.9 FREEZE with a 7-node subgraph; PKT-0001 → approve.
- `verify_local_only.py` → **PASS** (47 source files — now includes the dashboard JS).
- `pytest tests/` → **123 passed**.

### Phase 7 — Privacy & Trust Layer ✅ (2026-06-14)
Delivered:
- `shared/privacy.py` — PII redaction: PAN / account / property-ID maskers, field-aware
  `redact_mapping`, and a `PIIRedactionFilter` + `install_log_redaction()` installed at both
  services' startup (forensics v1.1.0, risk v6.0.0).
- `PRIVACY.md` — root privacy statement (on-premise posture, log redaction, data retention,
  evidence-chain auditability, honest limitations).
- The on-premise statement is surfaced in the dashboard (Phase 6 banner).
- 11 new tests in `tests/test_privacy.py`.

**Verified checks:**
- Maskers + dict redaction + the logging filter all strip PAN / account / property IDs
  ("grep a demo run's logs → no raw PII").
- Income/loan amounts (≤ 8 digits) are intentionally preserved in logs.
- `verify_local_only.py` → **PASS** (50 source files, 0 violations).
- `pytest tests/` → **134 passed**.

### Phase 8 — Demo Script & Narrative ✅ (2026-06-14)
Delivered:
- `scripts/seed_demo.py` — rebuilds the cross-application graph, scores 8 staged demo packets,
  self-checks each lands on its expected action, and prints the model-metrics slide.
- `DEMO.md` — root 3-minute narrative: setup, exact packet order + expected results, the
  double-financing graph reveal (PKT-0031→32→33 on SY-911/2C), scoring explanation, model metrics,
  and honest real-vs-mocked / trained-on-synthetic Q&A.
- 1 new test in `tests/test_demo_replay.py`.

**Verified checks:**
- `python scripts/seed_demo.py` → "Demo replay OK" (all 8 staged packets match: clean approves;
  tampered/inconsistent/forged-EC freeze; double-financing + identity ring freeze via the graph).
- Reproduces identically from a clean state (graph store is rebuilt deterministically).
- `verify_local_only.py` → **PASS** (52 source files, 0 violations).
- `pytest tests/` → **135 passed**.

### Phase 9 — Forensic/OCR depth (re-OCR cross-check + tamper localization) ✅ (2026-06-14)
First slice off the `plan.md` §6 production roadmap (D2 + D3). No new heavy deps; no model retrain.
Delivered:
- `services/forensics/app/ocr.py` — shared local-OCR helpers (`tesseract_available`, `render_page_png`,
  `ocr_page`, `ocr_pdf`); `extractor.py` now reuses them (its previously-dead Tesseract path).
- `services/forensics/app/analyzer.py` — `_check_reocr_mismatch` (§6.D2): render → OCR → compare visible
  currency amounts / PANs against the embedded text layer; flags text-layer values not visible on the
  page (whiteout/overlay edits). Precision guards: currency-prefixed amounts only + an "explained-away"
  rule that tells an OCR misread apart from a genuine hide. White-box + re-OCR findings now carry
  `values.regions=[{page,bbox}]` (§6.D3); `render_tamper_overlay()` draws red boxes on the page (pure
  PyMuPDF). `analyze(enable_reocr=…)` lets the model path skip OCR.
- `services/risk/app/features.py` — re-OCR excluded from the learned-model feature vector (tagged
  `check=reocr`; model pass calls `analyze_pdf(enable_reocr=False)`), so model inputs are byte-identical
  → no retrain.
- `services/risk/app/main.py` — `POST /risk/demo/score/{id}` now also returns
  `tamper_overlays:[{doc,page,image_b64}]` (outside the decision payload).
- `services/dashboard/src/App.jsx` — "Tamper localization" panel (annotated page images) + per-finding
  region badges in the evidence chain.
- Deps/containers: `pytesseract`+`Pillow` in both services' requirements; `tesseract-ocr` in both
  Dockerfiles. Without Tesseract, the re-OCR check no-ops (everything else unaffected).
- 9 new tests in `tests/test_reocr.py`.

**Verified checks:**
- Re-OCR fires on PKT-0010/0011 (hidden original income) and PKT-0028 (EC shows NIL, hides a
  Rs. 4,200,000 charge); **0 findings on all 10 clean packets**; PKT-0012's OCR digit-drop does not
  false-fire (explained-away guard).
- White-box findings carry valid `regions`; `render_tamper_overlay` returns a valid PNG.
- Model feature vectors unchanged (re-OCR excluded) → committed model artifacts untouched, no retrain.
- `python scripts/seed_demo.py` → "Demo replay OK" (actions unchanged; re-OCR adds corroborating
  evidence to already-frozen packets).
- `verify_local_only.py` → **PASS** (54 source files; Tesseract is a local subprocess, not network).
- `pytest tests/` → **144 passed** (135 + 9).

### Real-document pipeline (plan §7 M1, Person 1) — in progress
- `services/forensics/app/ingest/` — multi-format loader (PDF text/scan, images, password PDFs),
  OCR engine (Tesseract; PaddleOCR later), heuristic doc-type classifier, Indian normalizer + KYC
  validators (PAN structure, Aadhaar Verhoeff, IFSC), per-doc extractors (financial + PAN/Aadhaar),
  `ingest_document` orchestrator. `POST /forensics/ingest` upload endpoint. 18 tests.

### Web app (plan §8) — multi-page product with auth + two roles ✅
- Backend (risk v7.0.0): SQLite users/cases store + JWT auth (`app/db.py`, `app/auth.py`,
  `app/cases.py`, `app/overlays.py`); `POST /cases` ingests→scores→persists user uploads; admin review.
- Frontend (react-router): Home/About/Sign-in/Sign-up + User upload dashboard + Admin review queue +
  Case detail (reusable `DecisionView`); JWT auth context + route guards.
- **Verified:** `pytest tests/` → **165 passed**; live HTTP smoke (register/login/upload→score/admin);
  `npm run build` clean; `verify_local_only` passes. Auth/case data gitignored.

### Real-document KYC + underwriting (plan §9) — verify the applicant, not just the file ✅
- **Backend (risk):** `app/profiles.py` (purpose → required document slots; one source of truth for
  completeness + the upload form via `GET /cases/profiles`); `app/underwriting.py` (completeness, KYC
  identity/address/name-consistency, income reconciliation across Form 16 ↔ bank ↔ salary slip,
  affordability = FOIR + max-eligible + LTV → ELIGIBLE/REFER/DECLINE — all constants documented);
  `aggregator.apply_verification` folds completeness/KYC/income findings into the trust score by a
  **capped** penalty (eligibility kept off the trust axis). `POST /cases` takes per-file `doc_types`
  hints + `tenure_months`/`existing_emi`, persists a `verification` block. `db.py` migrated additively.
- **Forensics:** new `address_proof` doc type (classifier + extractor); `DocType.ADDRESS_PROOF`.
- **Frontend:** purpose-driven **named upload slots** + loan terms; **Verification panel** (completeness
  / KYC / income / eligibility-FOIR) in `DecisionView`, on the user result + admin CaseDetail.
- **Model store + seam:** downloads organized under gitignored `models/` (LayoutLMv3, DocTamper code+
  data, PaddleOCR src) + committed `models/{REGISTRY.md,registry.json}`; `ingest/model_registry.py`
  resolves local assets and **falls back to heuristics** when absent (no torch in the runtime).
- **Real-data kit** reorganized by purpose (`data/real/kyc/*`, `data/real/salaried_loan/*`, `_tampered/`)
  + address-proof slot (`data/real/README.md`).
- **Verified:** `pytest` → **177 passed** (165 + 12 new: underwriting/profiles/affordability/
  address-proof + salaried-loan flow + verification round-trip); `npm run build` clean;
  `verify_local_only` passes (`models/` excluded — vendored upstream code, gitignored).

### Hackathon sprint (plan §10) — Day 1: image / pixel forensics ✅
The hero capability for the judges' problem (edits in scanned/photographed documents — no text layer).
- **`services/forensics/app/image_forensics.py`** (NEW) — `analyze_image()` runs the standard toolkit:
  **ELA** (error-level analysis), **noise-residual** inconsistency, **copy-move/clone** (ORB keypoints
  + consistent-offset clustering **verified by pixel NCC** so repeated glyphs don't false-fire),
  **JPEG-ghost** (corroboration only), and **EXIF/software-trace** (editor in metadata). Robust
  thresholds (median + k·MAD), contiguous-cluster regions, and corroboration logic → EvidenceItem-shaped
  findings with `values.regions` boxes + an **annotated overlay** and **ELA heatmap** (base64 PNG) +
  a graduated 0–100 `image_trust` and `EDITED/SUSPICIOUS/CLEAN` verdict. Degrades gracefully (cv2 absent
  → copy-move skipped; any detector error is isolated).
- **`services/forensics/app/main.py`** (v1.3.0) — `POST /forensics/analyze-image` (single image →
  findings + overlay + signals + verdict); `/forensics/ingest` now routes **image** uploads to pixel
  forensics (PDFs still get structural/text-layer forensics). Deps: `numpy` + `opencv-python-headless`.
- **Frontend reverted** to the simple single-page investigator console (plan §10 decision; the §8/§9
  multi-page app retired to git history `66d9165`). The §9 KYC/underwriting **backend** remains.
- 4 new tests in `tests/test_image_forensics.py`.

**Verified checks:**
- Clean textured JPEG → no high-severity finding (`verdict != EDITED`); spliced patch → HIGH noise +
  JPEG-ghost corroboration **localized to the edit box**; exact clone → copy-move HIGH localized; garbage
  input → graceful `ok:false`.
- **Live container smoke** (`POST :8001/forensics/analyze-image`, forensics v1.3.0, cv2 active in image):
  spliced image → `verdict EDITED`, annotated overlay + ELA heatmap returned.
- `pytest` → **182 passed** (178 + 4); `verify_local_only` passes; `npm run build` clean (console, 34 modules).

### Hackathon sprint (plan §10) — Day 2: tamper-image dataset + eval + dashboard panel ✅
Turned the detectors into a *measured* capability and made them robust on real documents.
- **`data/generator/tamper_image.py` + `build_image_dataset.py`** (NEW) — rasterize the synthetic PDFs,
  add a realistic **scan simulation** (lighting gradient + optical blur + sensor-noise floor), then forge
  pixel edits with **ground-truth masks**: `copy_move`, `splice`, `recompress`, `number_edit`.
  Deterministic; output under gitignored `data/synthetic/images/`.
- **`scripts/eval_image_forensics.py`** (NEW) — runs `analyze_image` over the dataset and scores
  detection (P/R/F1) + localization (hit-rate / IoU) per tamper type; writes committed
  **`results/image_forensics/{metrics.json,summary.md,samples/*.png}`** (the showcase artifact).
- **Detector redesign for documents** (the hard part — documents are mostly white paper + sparse ink):
  noise is now estimated on **flat (non-text) pixels**, flagging regions that **lost the page's
  sensor-noise floor** (paint/splice/recompress); copy-move is **corroboration-only** (repeated
  glyphs/amounts make standalone clone detection unreliable → deferred to the Day-3 learned model).
- **Dashboard image panel** — the single-page console gains an **"Image edit detection"** section:
  example images + upload → `POST /forensics/analyze-image` → **annotated overlay + ELA heatmap +
  verdict + findings**. Curated examples in `services/dashboard/public/examples/`. Dashboard source is
  now **bind-mounted** (compose) with Vite polling, so frontend edits hot-reload without a rebuild.
- 2 new tests in `tests/test_image_dataset.py` (+ the 4 image-forensics tests rewritten for noisy scans).

**Results (committed → `results/image_forensics/`):** on 12 clean + 48 tampered synthetic documents —
**Detection precision 1.0 (ZERO false positives on clean), recall 0.73, F1 0.84**; localization
**number_edit hit 1.0 / IoU 0.84**, **splice hit 1.0 / IoU 0.86**, recompress hit 0.92; copy_move
deferred (0, by design). **Live container smoke:** clean example → CLEAN/100, edited-number → EDITED/0
localized, splice → EDITED/15. `pytest` → **184 passed**; `verify_local_only` passes; build clean.

### Hackathon sprint (plan §10) — Day 3: digital paint-over detector + DocTamper seam ✅
Triggered by real feedback: a PAN edited in a drawing app (flat paint over the number) came back CLEAN.
Diagnosed: the noise/ELA detectors need a sensor-noise/JPEG trace — a **pristine digital** edit has
none. (A **photographed** edit *is* caught — verified: photo+paint → EDITED.)
- **`image_forensics._flat_fill_regions`** (NEW detector) — flags a **solid mid-tone colour fill**
  embedded in the document (excludes near-black text/lines + near-white paper, ignores textured
  photos/logos). Catches the Sketchbook-style paint-over on clean/PNG images that the noise/ELA
  detectors miss. MEDIUM on its own (a fill *can* be a legit field), HIGH when corroborated.
- **`services/forensics/app/ingest/doctamper.py`** (NEW seam) — the learned DTD model is the deeper
  fix for digital edits, but **DocTamper ships code + JPEG quant tables, NOT trained weights** (gated —
  the `pks/*.pk` are quantisation dicts, not a checkpoint). The adapter reports UNAVAILABLE and the
  heuristics stay live; dropping a `.pth` under `models/doctamper/weights/` (+ torch) auto-enables it.
  Status is surfaced in every analysis (`signals.learned_model`). Registry/REGISTRY.md corrected.
- Dashboard: added a **"Digital paint-over"** example (the user's case) to the image panel.
- 2 new tests (digital paint-over caught; clean digital not flagged).

**Verified:** reproduction (clean digital PAN + flat paint, PNG **and** JPG) → now **EDITED + localized**;
clean digital → **CLEAN** (no false positive); **eval precision stays 1.0** (the new detector adds zero
clean false positives). Live container smoke: digital paint-over → EDITED/15. `pytest` → **186 passed**.

---

## All phases complete (0–8) + Phase 9 forensic/OCR depth + real-doc ingestion + web app
## + real-document KYC & underwriting (§9) + §10 Day 1–3 image-pixel forensics + eval. 🎉
Synthetic demo: `python scripts/seed_demo.py` then `DEMO.md`. Run: `docker compose up -d --build`
→ console at http://localhost:5173; image edit-detection at `POST :8001/forensics/analyze-image`.
