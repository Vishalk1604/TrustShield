# Forgery-localization model — training result (plan §10 → §11)

We train **our own** forgery-localization U-Net (the published DocTamper checkpoint is gated). This
records the arc from the §10 cross-domain failure to the §11 result on **domain-matched realistic data**.

## §10 (earlier): DocTamper-only → cross-domain failure
Trained on the DocTamper LMDB (Chinese-document tampering) and evaluated on our docs: **no uplift** —
the model's probabilities didn't discriminate tampered vs clean on our document types. Forgery models
don't transfer out-of-domain (DocForge-Bench). The path forward was domain-matched training data.

## §11: realistic dataset + domain fine-tune → it works
- **Base:** DocTamper LMDB, 12k images × 3 epochs (general tamper features).
- **Fine-tune:** the **train split** of the realistic v2 dataset (§11) — field-targeted seamless edits
  (naive/blended/pro) + geometric, on realistic Form 16 / bank / salary / PAN / Aadhaar — 25 epochs.
- **Eval:** the **held-out test split** (disjoint sources — no leakage), heuristics vs +U-Net.
- Hardware: RTX 5060 Laptop (Blackwell), torch 2.11+cu128, ~88 img/s.

**Test split (10 clean, 94 tampered) — detection rate by difficulty:**

| | precision | recall | F1 | naive | blended | pro | geom | loc. IoU |
|---|---|---|---|---|---|---|---|---|
| heuristics       | 1.0   | 0.17  | 0.29 | 0.0 | 0.0  | 0.0  | 0.53 | 0.10 |
| + fine-tuned U-Net | 0.945 | 0.915 | 0.93 | 1.0 | 0.95 | 0.83 | 0.90 | 0.48 |

**Headline:** domain-matched realistic data turns the model from useless (cross-domain) into the primary
detector — it catches the **seamless `pro` edits at 0.83** (heuristics: 0.0), naive/blended near-perfect,
localization IoU ~0.48. This validates the §11 dataset as training data. (It also corrected an overly
pessimistic prediction that the small edits would vanish at 256px — the fine-tune learned the edit
signature even at that resolution.)

**Honest caveat — clean false positives.** Precision is 0.945, but that is flattered by the
tampered-heavy split: the model **false-fires on 5 of 10 clean test docs (~50% FP on clean)**, which
violates the "no false positives" bar. So the default runtime stays **heuristic** (precision 1.0); the
U-Net is the **opt-in** high-recall mode (`TRUSTSHIELD_FORGERY_BACKEND=unet`). Reducing the clean-FP rate
is the headline target for the upgrades.

## Validity + open gaps (honest)
- This is **within-synthetic-domain** generalization: train/test are disjoint *sources* but share the
  same generator, fonts, edit method and scan model. It is **not** yet a synthetic→real result — a model
  can still be learning "this generator's fingerprint." The real PAN/Aadhaar eval anchor (Upgrade 3) is
  the true test of transfer.
- Upgrades in progress: (1) scale applicants/templates + vary scan/edit conditions (less overfitting,
  more clean data → fewer clean FP); (2) tamper-centered crop training + tiled native-res inference
  (tighter localization); (3) real-doc eval anchor; plus threshold/reliability calibration to kill the
  clean FPs.

_Reproduce:_ `python services/forensics/train_forgery.py --max-samples 12000 --epochs 3` (base) →
`python services/forensics/train_forgery.py --finetune --epochs 25` → `TRUSTSHIELD_FORGERY_BACKEND=unet
TRUSTSHIELD_EVAL_SPLIT=test python scripts/eval_image_forensics.py`.
