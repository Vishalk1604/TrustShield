# Forgery-localization model — training result (plan §10 Phase 5)

We trained **our own** forgery-localization network to fill the gap left by DocTamper's **gated**
weights, using the data we *do* hold (the DocTamper LMDB) + our own pipeline. This documents the run
and the **honest** outcome.

## Setup
- **Model:** compact U-Net (`services/forensics/app/ingest/forgery_unet.py`), torch-only — no `jpegio`
  (the exact DocTamper DTD needs JPEG-DCT via jpegio, which is impractical on Windows).
- **Data:** DocTamper **LMDB** (`models/doctamper/data/DocTamperV1-TrainingSet`) — 120k RGB 512×512
  document images + tamper masks; trained on a **12,000-image subset** at 256×256.
- **Train:** Dice+BCE, AdamW lr 2e-4, AMP, **3 epochs**, batch 16.
- **Hardware:** NVIDIA RTX 5060 Laptop (Blackwell, sm_120), torch 2.11+cu128. ~**72 img/s**, ~165 s/epoch.
- **Loss:** 1.49 → 1.02 (converging). Weights → `models/forgery/unet/weights/forgery.pth` (31 MB).

## Result — measured, not assumed

**Eval (`scripts/eval_image_forensics.py`) — heuristics-only vs +U-Net, on the synthetic eval set:**

| | precision | recall | F1 | number_edit IoU | splice IoU | copy_move hit |
|---|---|---|---|---|---|---|
| heuristics only | 1.0 | 0.729 | 0.843 | 0.841 | 0.86 | 0.0 |
| + U-Net (unet)  | 1.0 | 0.729 | 0.843 | 0.837 | 0.86 | 0.0 |

**No uplift.** Raw model probabilities cluster at **0.45–0.59 regardless of tampered vs clean**, on both
the synthetic eval *and* the real PAN/Aadhaar photos — i.e. the model does not discriminate edited from
genuine on our document types. This is **cross-domain failure**: DocTamper is Chinese-document text
tampering; it does not transfer to our synthetic Indian-style forms or to real Indian ID cards. It
matches the published **DocForge-Bench (2025)** finding that forgery models do not work out-of-the-box
across document domains.

## Decision (honest)
- **Heuristics + semantic identifier check + QR cross-check remain the default** — they are reliable on
  our documents (precision 1.0). The learned model is **trained, integrated behind the seam, and opt-in**
  (`TRUSTSHIELD_FORGERY_BACKEND=unet`) but is **not auto-enabled** (it adds latency without benefit here).
- **What was proven:** the full GPU training + inference pipeline works end-to-end on the Blackwell GPU,
  and we *can* train our own forgery weights from the DocTamper data — the gated-checkpoint blocker is
  removed.
- **Path to value:** fine-tune on **domain data** — our Day-2 synthetic tamper set + a labelled set of
  real Indian-document edits (with masks). `python services/forensics/train_forgery.py --finetune` is
  wired for exactly this; re-run the eval (on a held-out split, to avoid train-on-test) to measure.

_Reproduce:_ `python services/forensics/train_forgery.py --max-samples 12000 --epochs 3 --batch 16`
then `TRUSTSHIELD_FORGERY_BACKEND=unet python scripts/eval_image_forensics.py`.
