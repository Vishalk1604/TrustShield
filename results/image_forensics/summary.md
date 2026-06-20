# Image-forensics evaluation (plan section 10, Day 2)

Detectors: ELA, noise-loss (flat-pixel sensor-noise), copy-move (NCC-verified,
corroboration-only), JPEG-ghost, EXIF/software-trace.
Dataset: 12 clean + 48 tampered (synthetic, deterministic seed=7, 150 DPI, JPEG q90).

## Detection (clean vs tampered)
| precision | recall | F1 | accuracy | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|
| 1.0 | 0.729 | 0.843 | 0.783 | 35 | 0 | 12 | 13 |

## Localization (tampered images)
Overall hit-rate **0.729**, mean IoU **0.472**.

| tamper type | n | localization hit-rate | mean IoU |
|---|---|---|---|
| copy_move | 12 | 0.0 | 0.0 |
| number_edit | 12 | 1.0 | 0.841 |
| recompress | 12 | 0.917 | 0.189 |
| splice | 12 | 1.0 | 0.86 |

Note: copy-move (clone) detection on dense document text is corroboration-only here (repeated glyphs/amounts make standalone clone detection unreliable); it is the job of the learned DocTamper model (Day 3). The noise-loss + ELA detectors catch the realistic paint/splice/recompress edits with zero false positives on clean documents.

Sample annotated overlays: `results/image_forensics/samples/`.
