# CLAUDE.md — data/generator

## Purpose
Deterministically generate synthetic loan-application packets — clean ones and every fraud type —
as real PDFs, plus a ground-truth `labels.json`. This is the test corpus every later phase runs
against. All data is synthetic; there is no real PII.

## Key files
- `pdf_builder.py` — builds clean PDFs with PyMuPDF. **§11 generator v2:** realistic layouts —
  `build_form16` (TRACES Part A/B + quarterly-TDS table), `build_bank_statement` (running-balance
  transaction table), `build_salary_slip` (balancing earnings/deductions), doc-style `build_identity`
  (PAN) + new `build_aadhaar` (marked SYNTHETIC); plus the land/legal collateral builders. Income/KYC
  builders take an optional **`fields` out-dict** (the *field map*: each editable value's rect in PDF
  points + its realistic fraud direction) and a `template` variant. **Backward-compatible** — the
  `fields`/`template` args are keyword-only, so legacy positional callers + the PDF-level tampers still
  work (gross is still drawn as `_money(...)`). `make_seal_png()` for the copy-paste signal.
- `seamless_edit.py` (**§11**) — the no-hard-edge edit engine. `edit_field(img, box, new_text,
  difficulty=…)` on a **naive→blended→pro** spectrum: `pro` = cv2.inpaint → font/colour/**bold**-matched
  render → page-matched sensor noise → single recompress. Pure PIL/numpy; cv2 optional (pro→blended).
- `tamper.py` — PDF-level forensic signals (white-box edit / font / duplicate / incremental). Unchanged.
- `build_image_dataset.py` (**§11 v2**) — builds docs **in-process** (to hold exact field boxes),
  rasterises → `_simulate_scan`, applies field-targeted seamless edits across the difficulty spectrum +
  the geometric pixel tampers, with ground-truth masks and a deterministic **train/val/test split by
  source id**. Writes `data/synthetic/images/{clean,tampered,masks}/` + `labels.json`.
- `_preview_form16.py` — throwaway QA gate (renders clean + a pro edit; not a test). Output gitignored.
- `generate.py` — PDF-packet orchestrator (`ROSTER` + category builders → `data/synthetic/packets/` +
  `labels.json`). Run: `python -m data.generator.generate`. (Separate corpus from the image dataset.)
- `requirements.txt` — `PyMuPDF`. The image pipeline also uses `numpy`/`Pillow`/`opencv` (cv2 optional).

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

## Fraud taxonomy produced (33 packets: 10 clean + 23 fraud)
**Financial / forensic / behavioral**
- `suspicious_metadata` — producer = editing tool; modDate ≫ creationDate.
- `edited_income_figure` — white-box redaction; original value remains in the text layer.
- `font_inconsistency` — edited figure drawn in a serif font unlike the sans body.
- `copy_paste` — duplicated salary-credit row + duplicated seal image.
- `incremental_update` — incremental save → second xref / `%%EOF`.
- `cross_document_inconsistency` — Form 16 vs bank credits vs salary slip disagree.
- `template_reuse` — a ring of 4 identities built from one shared template (`template_group: ring_quickcash`).
- `behavioral_velocity` / `timestamp_anomaly` — identical/ future/ reversed timestamps; tight create→submit.

**Legal / land-record (collateral)** — secured-loan packets carry sale deed + EC + valuation + legal opinion
- `forged_title` — sale-deed owner name altered (≠ applicant); original name left in the text layer.
- `tampered_encumbrance` — EC white-boxed to read "NIL" while CERSAI records an active charge; charge residue survives.
- `valuation_inflation` — valuation ≫ market value; requested loan exceeds market value (abnormal LTV).
- `property_mismatch` — sale deed and valuation reference different survey numbers.
- `double_financing` — **3 applicants pledge the SAME property** (`property_group: prop_ring_sy911`,
  shared `property_id: SY-911/2C`) — the Phase 5 collateral-graph "wow."

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
- **Done (Phase 0):** all six category builders; every fraud type present and spot-checked,
  including land/legal collateral docs + the double-financing ring.
- TODO (generator v2 — see `plan.md` §6.B): scale to hundreds–thousands of randomised packets with a
  train/val/test split; multiple document layouts (fixes the 25-packet fingerprint collision); scanned
  & image (JPG/PNG) variants to exercise the OCR pipeline; realistic multi-page transaction streams;
  normalise double-financing velocity (remove the leakage artifact); region/bounding-box labels.
