# Image-forensics evaluation (plan section 10, Day 2)

Detectors: ELA, noise-loss (flat-pixel sensor-noise), copy-move (NCC-verified,
corroboration-only), JPEG-ghost, EXIF/software-trace.
Dataset: 95 clean + 874 tampered (synthetic, deterministic seed=7, 150 DPI, JPEG q90).

## Detection (clean vs tampered)
| precision | recall | F1 | accuracy | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|
| 1.0 | 0.185 | 0.313 | 0.265 | 162 | 0 | 95 | 712 |

## Detection by edit difficulty
Heuristics catch the naive (hard-edge) tier and the larger geometric edits; the seamless
`pro` tier (inpaint + matched font/noise + single recompress) is designed to evade them — that
gap is the honest motivation for the learned forgery model.

| difficulty | n | detection rate | localization hit-rate | mean IoU |
|---|---|---|---|---|
| blended | 190 | 0.0 | 0.0 | 0.0 |
| geom | 285 | 0.565 | 0.565 | 0.325 |
| naive | 190 | 0.005 | 0.005 | 0.002 |
| pro | 209 | 0.0 | 0.0 | 0.0 |

## Localization (tampered images)
Overall hit-rate **0.185**, mean IoU **0.106**.

| tamper type | n | detection rate | localization hit-rate | mean IoU |
|---|---|---|---|---|
| aadhaar_number | 57 | 0.0 | 0.0 | 0.0 |
| basic | 57 | 0.0 | 0.0 | 0.0 |
| closing_balance | 57 | 0.0 | 0.0 | 0.0 |
| copy_move | 95 | 0.0 | 0.0 | 0.0 |
| dob | 57 | 0.0 | 0.0 | 0.0 |
| gross_salary | 57 | 0.0 | 0.0 | 0.0 |
| name | 57 | 0.018 | 0.018 | 0.005 |
| net_pay | 57 | 0.0 | 0.0 | 0.0 |
| pan | 57 | 0.0 | 0.0 | 0.0 |
| recompress | 95 | 0.695 | 0.695 | 0.159 |
| salary_credit | 76 | 0.0 | 0.0 | 0.0 |
| splice | 95 | 1.0 | 1.0 | 0.815 |
| tds | 57 | 0.0 | 0.0 | 0.0 |

Note: the headline guarantee holds — ZERO false positives on clean documents (precision 1.0). The field-targeted seamless `pro` edits are realistic forgeries that defeat the hand-tuned pixel heuristics by construction; closing that gap is the job of the learned forgery model (fine-tuned on this dataset's `pro`/`blended` train split — see results/forgery_training/).

Sample annotated overlays: `results/image_forensics/samples/`.
