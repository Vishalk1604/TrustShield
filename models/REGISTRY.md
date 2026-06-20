# models/ — local model & dataset store

This directory holds the large ML assets TrustShield can use to upgrade its heuristics with trained
models. **Everything here is gitignored except this `REGISTRY.md` and `registry.json`.** The repo
ships and runs without any of these present — they are *upgrades behind seams*, not dependencies.

## Contract
- **No runtime network.** Nothing here is auto-downloaded at request time. Assets are placed here at
  dev time (by a teammate) and loaded from local disk. `scripts/verify_local_only.py` excludes this
  folder from its scan (it contains vendored upstream code that references networks for *training*).
- **Seam, with fallback.** Code resolves assets through
  [`services/forensics/app/ingest/model_registry.py`](../services/forensics/app/ingest/model_registry.py):
  `resolve_model(name)` returns a local path or `None`; `model_available(name)` is a bool. Every
  consumer **must** degrade to the documented heuristic fallback when the asset is absent. So a fresh
  clone with an empty `models/` runs fine on heuristics.
- Override the location with the `TRUSTSHIELD_MODEL_DIR` env var (default: this folder).

## Layout
```
models/
  REGISTRY.md            (committed)  ← this file
  registry.json          (committed)  ← machine-readable manifest consumed by model_registry.py
  layoutlmv3-base/                    HF model — doc-type + KV extractor fine-tune target
  doctamper/
    code/                             DocTamper repo: models/ (DTD + Swin) + pks/ (trained checkpoints)
    data/                             DocTamperV1 LMDB (22 GB) — forgery-CNN training data
  paddleocr/
    src/                              PaddleOCR repo (code only)
    weights/                          PP-OCRv4 weights — pre-cache here (currently absent)
data/reference/funsd/                 tiny FUNSD parquet (KV reference)   ← note: under data/, not models/
```

## Status (see `registry.json` for the source of truth)

| Asset | Status | Live now? | Fallback when absent |
|---|---|---|---|
| `layoutlmv3-base` | present | no (seam) | heuristic classifier + regex extractors |
| `doctamper/code` (model source + quant tables) | present | no (seam) | heuristic image forensics |
| `doctamper/weights` (trained DTD `.pth`) | **absent (gated)** | no | heuristic image forensics — drop a checkpoint here + torch to enable |
| `doctamper/data` (LMDB) | present | n/a (training only) | — |
| `paddleocr/src` | present | no | Tesseract |
| `paddleocr/weights` | **absent** | no | Tesseract |
| `funsd` (in `data/reference/`) | present | n/a (reference) | — |

## Notes
- **DocTamper ships code, NOT weights.** The `pks/*.pk` files are per-image JPEG **quantisation
  tables** (dicts of 2k–30k entries), not a trained model. The DTD checkpoint is gated — request it
  from the authors (education email) like the dataset, then place it under `doctamper/weights/`. The
  seam (`services/forensics/app/ingest/doctamper.py`) enables the learned model automatically when a
  checkpoint + torch are present; until then the heuristics in `image_forensics.py` are the live path.
- **torchvision backbone not required** — the DTD model brings its own Swin backbone definition.
- **DocTamper dataset is on disk in LMDB form**; the gated password was only needed to obtain it.
  Reading it needs the `lmdb` Python lib (a Person-2 / training-time dependency, not a runtime one).
- Enabling the deep models (loading LayoutLMv3 / the forgery CNN into the live pipeline) is the
  **Person-2 GPU step** — it flips `live: true` in `registry.json` and adds torch/transformers to the
  *training* environment, not to the slim runtime images. Until then the seams return `None` and the
  heuristics run.
