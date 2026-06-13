# CLAUDE.md — data/synthetic

## Purpose
The generated test corpus: synthetic loan packets plus the ground-truth labels every later phase
measures accuracy against. **This folder is produced by `data/generator/` — do not hand-edit it.**

## Key files / layout
- `packets/PKT-0001/ … PKT-0024/` — one folder per application packet. Each contains the PDFs
  (`identity.pdf`, `form16.pdf`, `salary_slip.pdf`, `bank_statement.pdf`) and a `manifest.json`.
- `manifest.json` (per packet) — an `ApplicationPacket`-shaped record (id, applicant, documents
  with sha256/page_count, created_at/submitted_at, source) plus a `ground_truth` block holding the
  claimed financials. The PDFs are the real input; the manifest is convenience metadata.
- `labels.json` (this folder) — the ground truth: `PKT-id -> { label, fraud_types[], reasons[],
  affected_docs[], applicant_pan, employer, template_group }`. Use this to compute precision/recall.

## How it fits
Phase 1 reads the PDFs; Phase 2 OCRs them; Phases 3–5 train/score against `labels.json`. The
`template_group` field (e.g. `ring_quickcash`) is the expected cluster for the Phase 5 graph.

## Local-only contract
Synthetic data only — no real PII, nothing leaves the machine.

## How to (re)generate
```bash
python -m data.generator.generate
```
Deterministic: a regenerated set matches the committed one.

## Gotchas
- Committed on purpose so a fresh clone can demo without running the generator (tiny PDFs).
- 24 packets: 8 clean + 16 fraud spanning all nine fraud types. Counts/coverage are asserted by
  `tests/test_generator.py`.

## Status
- **Done (Phase 0):** corpus generated and committed; labels validated by tests.
