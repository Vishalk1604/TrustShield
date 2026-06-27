# TrustShield — demo corpus

A small, **browsable, cross-verified** slice of the synthetic corpus for demos and judging.
Everything here is synthetic (zero PII) and is rebuilt by:

```bash
.venv/Scripts/python.exe scripts/build_demo_folder.py
```

## `documents/<doc_type>/`
Each folder holds a genuine `clean.jpg` and edited variants at different difficulty levels —
`naive` (obvious flat fill) → `blended` (feathered) → `pro` (seamless: matched font, tone, scan
noise) — plus geometric edits (`splice`, `recompress`). `manifest.json` records, per edit, the
old→new value, the ground-truth box, and the **cross-verified detector result**: the zero-FP
pixel **heuristics** vs the opt-in learned **U-Net** (the deep scan). Seamless `pro` edits
typically evade the heuristics and are only caught by the model.

## `packets/<PKT-id>/`
A curated set of full loan packets (1 clean + one per fraud shape + the 3-application
double-financing ring). The packet's documents are copied alongside a `verification.json`
holding the **full-pipeline** result — trust score, recommended action, and the evidence chain
(including cross-document income reconciliation and cross-application graph findings).

## `MANIFEST.json`
An index of everything plus a caught/missed summary.

> Honest note: the learned U-Net has a measured **~19% false-positive rate on clean documents**
> (it over-flags the Form-16 salary region), which is why it is opt-in (the deep scan) and never
> the default detection path. The heuristics hold a 0/95 clean false-positive rate.
