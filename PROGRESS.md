# TrustShield — Progress

Resume protocol: read [`plan.md`](plan.md) then this file; continue from the first unchecked phase.

| ✓ | Phase | Title | Completed (date) | Commit |
|---|---|---|---|---|
| ☑ | 0 | Foundation, scaffolding, synthetic data | 2026-06-13 | `1d1f573` |
| ☑ | 1 | Document Integrity / Forensics | 2026-06-14 | `8c2f043` |
| ☑ | 2 | Semantic Consistency / Underwriting | 2026-06-14 | — |
| ☐ | 3 | Anomaly & Behavioral Scoring | — | — |
| ☐ | 4 | Trust Score Aggregation & Evidence Chain | — | — |
| ☐ | 5 | Cross-Application Graph | — | — |
| ☐ | 6 | Investigator Dashboard | — | — |
| ☐ | 7 | Privacy & trust layer | — | — |
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

### Phase 3 — Anomaly + Learned Risk Model
Next up. See `plan.md` §4.
