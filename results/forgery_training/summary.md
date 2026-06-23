# Forgery-localization model — training result (plan §10 → §11 + upgrades)

We train **our own** forgery-localization U-Net (the published DocTamper checkpoint is gated). This is
the honest arc: cross-domain failure → realistic domain data works → upgrades + the synthetic→real gap.

## 1. §10 — DocTamper-only → cross-domain failure
Trained on the DocTamper LMDB (Chinese-document tampering), evaluated on our docs: **no uplift** — the
model didn't discriminate tampered vs clean on our document types (DocForge-Bench). Need domain data.

## 2. §11 — realistic dataset + domain fine-tune → it works (on synthetic)
Base = DocTamper LMDB (12k×3); fine-tune = the **train split** of the realistic v2 dataset (§11) —
field-targeted seamless edits (naive/blended/pro) + geometric on realistic Form 16 / bank / salary /
PAN / Aadhaar; eval on the **held-out test split** (disjoint sources). RTX 5060, torch 2.11+cu128.

First fine-tune lifted recall **0.17 → 0.915** and caught the seamless `pro` edits at 0.83 (heuristics
0.0) — proving the realistic dataset is good training data. **But** it false-fired on ~50% of clean docs.

## 3. Upgrades — what helped, what backfired (measured)
- **Clean negatives (the key fix).** The trainer only fed *tampered* images, so the model never learned
  to output nothing → it over-fired. Adding clean images as empty-mask negatives (~30% of the set) cut
  the clean-FP rate sharply.
- **Scale + mild scan variety.** 10→19 synthetic applicants; per-source blur/noise/JPEG variety (a
  *narrow* band — an aggressive band with rotation tripped the ELA/noise heuristics on clean docs and
  was reverted).
- **Patch-crop training + tiled native-res inference — tried and REVERTED.** Running ~70 overlapping
  tiles compounds the per-tile false-positive rate into ~100% clean FPs. Whole-image inference (one
  prediction per page) is correct here.

## 4. Final result (test split: 15 clean, 139 tampered)

| | precision | recall | naive | blended | pro | geom | loc IoU |
|---|---|---|---|---|---|---|---|
| heuristics          | **1.0**  | 0.18 | 0.0  | 0.0  | 0.0  | 0.6  | 0.11 |
| + fine-tuned U-Net  | 0.97 | 0.49 | 0.37 | 0.23 | 0.29 | 0.89 | 0.30 |

On synthetic the U-Net is a clear uplift over the heuristics (recall 0.49 vs 0.18; catches the seamless
`pro` edits at 0.29 vs 0.0) at ~13% clean FP, with whole-image inference + clean negatives. An earlier
run with aggressive scan variety scored higher on the model (recall ~0.79) but tripped the heuristics on
clean docs — reverted, because the **heuristic precision-1.0 / zero-false-positive guarantee on clean is
the priority** (confirmed on the full 95-clean set: **FP = 0/95**). So the **default runtime stays
heuristic** and the U-Net is the **opt-in** higher-recall mode (`TRUSTSHIELD_FORGERY_BACKEND=unet`).

## 5. The decisive finding — synthetic→real gap (Upgrade 3, `scripts/eval_real_anchor.py`)
Run on the **real** PAN/Aadhaar original/edited pairs in `data/real/kyc` (PII; local only):

| backend | real originals flagged (want 0) | real edited flagged (want all) |
|---|---|---|
| heuristics | **0 / 7** ✅ | 1 / 7 |
| + U-Net    | **7 / 7** ❌ | 7 / 7 |

The U-Net flags **every** real document — originals and edited alike. It learned the synthetic
generator's fingerprint (clean rasterized PDFs + simulated scan) and treats any real phone-photo of a
colored ID card as out-of-distribution → "tampered everywhere." It is strong *within* the synthetic
domain but **does not transfer to real documents.** On real docs the **heuristics are the only reliable
layer** (0 false positives, low recall). This is the hardest case for our B&W doc-style synthetic — the
real anchors are colored ID-card photos (we deliberately kept PAN/Aadhaar doc-style).

## 6. Honest bottom line + path forward
The §11 realistic dataset is **good enough** to (a) prove realistic edits defeat the heuristics, (b)
provide a clean difficulty-tagged eval, and (c) train a model that detects edits **on synthetic docs**.
It is **not yet good enough** to make a model that works on **real** documents — the synthetic→real gap
dominates. Closing it needs: **real tampered training data** (a few labelled real edits), and/or
**photo-realistic ID synthesis** (colored PAN/Aadhaar cards + phone-photo capture sim: perspective,
lighting, real fonts, camera noise), plus domain-adaptation. Until then the model is a synthetic-domain
tool; heuristics + semantic + QR remain the guaranteed-local real-doc layer.

_Reproduce:_ `python -m data.generator.build_image_dataset` →
`python services/forensics/train_forgery.py --max-samples 12000 --epochs 3` (base) →
`python services/forensics/train_forgery.py --finetune --epochs 30` →
`TRUSTSHIELD_FORGERY_BACKEND=unet TRUSTSHIELD_EVAL_SPLIT=test python scripts/eval_image_forensics.py`
and `TRUSTSHIELD_FORGERY_BACKEND=unet python scripts/eval_real_anchor.py`.
