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
| ☐ | 8 | Demo script & narrative | — | — |

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

### Phase 8 — Demo Script & Narrative
Next up. See `plan.md` §4.
