# CLAUDE.md — data/generator

## Purpose
Deterministically generate synthetic loan-application packets — clean ones and every fraud type —
as real PDFs, plus a ground-truth `labels.json`. This is the test corpus every later phase runs
against. All data is synthetic; there is no real PII.

## Key files
- `pdf_builder.py` — builds clean PDFs (PAN/identity, Form 16, salary slip, bank statement) with
  PyMuPDF; controls fonts and metadata; `make_seal_png()` for the copy-paste signal.
- `tamper.py` — forges specific, detectable signals into clean PDFs (see its table). Each maps to a
  Phase 1 forensic detector.
- `generate.py` — orchestrator. Holds the canonical `ROSTER`, the category builders
  (`build_clean / build_forensic / build_cross_doc / build_template_reuse / build_behavioral`),
  realizes packets to disk, and writes `labels.json`. Run: `python -m data.generator.generate`.
- `requirements.txt` — `PyMuPDF` (the only extra dep needed to generate).

## How it fits
Output lands in `../synthetic/`. Phase 1 forensics reads the PDFs; Phase 2 OCRs them; Phases 3–5
read `labels.json` to score accuracy. The `ROSTER` PANs/employers match `shared/mocks/fixtures/`
so external-verification cross-checks line up later.

## Local-only contract
Pure local file generation — no network. Synthetic identities only.

## How to run / test just this part
```bash
pip install -r data/generator/requirements.txt   # PyMuPDF
python -m data.generator.generate                 # writes ../synthetic/packets/* + labels.json
pytest tests/test_generator.py
```

## Fraud taxonomy produced (24 packets: 8 clean + 16 fraud)
- `suspicious_metadata` — producer = editing tool; modDate ≫ creationDate.
- `edited_income_figure` — white-box redaction; original value remains in the text layer.
- `font_inconsistency` — edited figure drawn in a serif font unlike the sans body.
- `copy_paste` — duplicated salary-credit row + duplicated seal image.
- `incremental_update` — incremental save → second xref / `%%EOF`.
- `cross_document_inconsistency` — Form 16 vs bank credits vs salary slip disagree.
- `template_reuse` — a ring of 4 identities built from one shared template (`template_group: ring_quickcash`).
- `behavioral_velocity` / `timestamp_anomaly` — identical/ future/ reversed timestamps; tight create→submit.

## Gotchas
- **Deterministic by design:** `SEED` + fixed `BASE_DATE`. Re-running reproduces identical content
  (sha256 may differ only if PyMuPDF's version changes byte layout). `main()` wipes
  `../synthetic/packets/` before rebuilding.
- The white-box income edit intentionally leaves the original number in the text layer — that *is*
  the forensic signal (`page.get_text()` shows two income values).
- For the incremental-update packet, the file is saved normally first, then `post_save` reopens it
  and does the incremental save — so the on-disk file (not the in-memory doc) carries the signal.
- Packet ids are sequential (`PKT-0001`…) and carry no label leakage; the category lives only in
  `labels.json` / `manifest.json`.

## Status
- **Done (Phase 0):** all five category builders; every fraud type present and spot-checked.
- TODO: add more volume/variety if Phase 3's model needs it.
