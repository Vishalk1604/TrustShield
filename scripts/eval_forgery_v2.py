#!/usr/bin/env python3
"""Evaluate the v2 forgery U-Net on the held-out TEST split (plan §11.2).

Runs the calibrated tiled inference (`forgery_unet.infer` + `forgery_model.mask_to_regions`, which loads
the val-chosen `calibration.json`) and reports, vs the recorded baseline:
  - doc-level CLEAN false-positive rate (target ≤ 1-2 %),
  - per-difficulty tampered recall (naive / blended / pro / geom),
  - localization IoU on caught edits,
  - a discrimination summary on Form 16 (clean form16 FP vs form16 `pro` recall) — the original failure.

Caps the number of docs (tiled inference on 300-dpi pages is heavy). Run from the repo root:
    python scripts/eval_forgery_v2.py            # after training + --calibrate-only
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from services.forensics.app.ingest import forgery_model as fm  # noqa: E402
from services.forensics.app.ingest import forgery_unet as fu  # noqa: E402

IMAGES = REPO / "data" / "synthetic" / "images"


def _flag_and_mask(path: str):
    """Run the calibrated unet path → (flagged: bool, predicted binary mask HxW or None)."""
    prob = fu.infer(path, str(fm.weights_path("unet")))
    if prob is None:
        return False, None
    res = fm.mask_to_regions(prob, path)
    cal = fm._calibration()
    binm = (prob >= float(cal.get("tau_mask", 0.5))).astype(np.uint8)
    return (res is not None), binm


def _iou(pred: np.ndarray, gt_path: Path) -> float:
    import cv2
    gt = cv2.imread(str(gt_path), 0)
    if gt is None:
        return 0.0
    if gt.shape != pred.shape:
        gt = cv2.resize(gt, (pred.shape[1], pred.shape[0]), interpolation=cv2.INTER_NEAREST)
    g = gt > 127
    p = pred > 0
    inter = np.logical_and(g, p).sum()
    union = np.logical_or(g, p).sum()
    return float(inter / union) if union else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", type=int, default=80, help="max clean test docs")
    ap.add_argument("--per-diff", type=int, default=120, help="max tampered test docs per difficulty")
    args = ap.parse_args()

    if fm.weights_path("unet") is None:
        sys.exit("no unet weights — train first (services/forensics/train_forgery.py)")
    recs = json.loads((IMAGES / "labels.json").read_text())["records"]
    test = [r for r in recs if r.get("split") == "test"]
    clean = [r for r in test if r["label"] == "clean"][: args.clean]
    by_diff: dict[str, list] = defaultdict(list)
    for r in test:
        if r["label"] == "tampered":
            by_diff[r["difficulty"]].append(r)
    for k in by_diff:
        by_diff[k] = by_diff[k][: args.per_diff]

    print(f"cal = {fm._calibration()}")
    print(f"eval: {len(clean)} clean + " + ", ".join(f"{k}:{len(v)}" for k, v in by_diff.items()))

    fp = sum(_flag_and_mask(str(IMAGES / r['file']))[0] for r in clean)
    clean_fp = fp / max(1, len(clean))
    print(f"\nCLEAN false positives: {fp}/{len(clean)} = {clean_fp:.3f}")

    print(f"\n{'difficulty':10} {'recall':7} {'IoU(caught)':11} n")
    for diff in ("naive", "blended", "pro", "geom"):
        rs = by_diff.get(diff, [])
        if not rs:
            continue
        caught, ious = 0, []
        for r in rs:
            flagged, binm = _flag_and_mask(str(IMAGES / r["file"]))
            if flagged:
                caught += 1
                if binm is not None and r.get("mask"):
                    ious.append(_iou(binm, IMAGES / r["mask"]))
        rec = caught / len(rs)
        iou = (sum(ious) / len(ious)) if ious else 0.0
        print(f"{diff:10} {rec:7.3f} {iou:11.3f} {len(rs)}")

    # discrimination on Form 16 (the original failure): clean form16 must NOT flag; form16 pro must.
    f16_clean = [r for r in clean if r["doc_type"] == "form16"]
    f16_pro = [r for r in test if r["label"] == "tampered" and r["doc_type"] == "form16"
               and r["difficulty"] == "pro"][:60]
    if f16_clean and f16_pro:
        cfp = sum(_flag_and_mask(str(IMAGES / r['file']))[0] for r in f16_clean) / len(f16_clean)
        crec = sum(_flag_and_mask(str(IMAGES / r['file']))[0] for r in f16_pro) / len(f16_pro)
        print(f"\nForm-16 discrimination: clean FP = {cfp:.3f} (want ~0)  |  pro recall = {crec:.3f} (want high)")
    print("\nBaseline to beat (recorded): heuristics R=0.18 (pro 0.0); old U-Net R=0.49 (pro 0.29), ~13-19% clean FP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
