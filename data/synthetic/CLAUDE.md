# CLAUDE.md — data/synthetic

## Purpose
The generated test corpus: synthetic loan packets plus the ground-truth labels every later phase
measures accuracy against. **This folder is produced by `data/generator/` — do not hand-edit it.**

## Key files / layout
- `packets/PKT-0001/ … PKT-0033/` — one folder per application packet. Financial packets contain
  `identity/form16/salary_slip/bank_statement.pdf`; **secured-loan packets also contain
  `sale_deed.pdf`, `encumbrance_certificate.pdf`, `property_valuation.pdf`, `legal_opinion.pdf`**.
  Each folder has a `manifest.json`.
- `manifest.json` (per packet) — an `ApplicationPacket`-shaped record (id, applicant, documents
  with sha256/page_count, created_at/submitted_at, source) plus a `ground_truth` block holding the
  claimed financials / property details. The PDFs are the real input; the manifest is convenience metadata.
- `labels.json` (this folder) — the ground truth: `PKT-id -> { label, fraud_types[], reasons[],
  affected_docs[], applicant_pan, employer, template_group, property_group, property_id }`. Use this
  to compute precision/recall.

## How it fits
Phase 1 reads the PDFs; Phase 2 OCRs them; Phases 3–5 train/score against `labels.json`. The
`template_group` (e.g. `ring_quickcash`) is the expected Phase-5 ring cluster; the `property_group`
(e.g. `prop_ring_sy911`, shared `property_id`) is the expected **double-financed-collateral** cluster.

## Local-only contract
Synthetic data only — no real PII, nothing leaves the machine.

## How to (re)generate
```bash
python -m data.generator.generate
```
Deterministic: a regenerated set matches the committed one.

## Gotchas
- Committed on purpose so a fresh clone can demo without running the generator (tiny PDFs).
- 33 packets: 10 clean + 23 fraud spanning all 14 fraud types (financial + legal/land). Counts and
  coverage (incl. the double-financing collateral cluster) are asserted by `tests/test_generator.py`.

## Status
- **Done (Phase 0):** corpus generated and committed; labels validated by tests.
