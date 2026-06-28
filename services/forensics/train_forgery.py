#!/usr/bin/env python3
"""Train the v2 two-stream noise-aware forgery U-Net on NATIVE-RESOLUTION patches (plan §11.2).

Synthetic-only (real-doc transfer is out of scope). The win over v1: we sample real-resolution patches
from the 300-dpi dataset (so the seamless-edit noise signal survives), feed RGB + SRM/Bayar noise
residuals, and train a per-pixel mask head **and** a per-patch tamper classifier. Heavy clean
hard-negative mining (clean patches + clean regions of tampered pages) teaches the model to output
nothing on clean content — the fix for the 19% clean false-positive rate.

    pip install -r services/forensics/requirements-models.txt   # torch (cu128 for the 5060)
    # full run (≈ your 40 h budget; tune epochs/batch to taste):
    python services/forensics/train_forgery.py --epochs 12 --batch 8
    # then calibrate the operating point on the val split (writes calibration.json):
    python services/forensics/train_forgery.py --calibrate-only
    # then measure:  python scripts/eval_forgery_v2.py

torch-only; no jpegio/smp/timm; no network.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from services.forensics.app.ingest.forgery_unet import PATCH_RES, build_model, preprocess  # noqa: E402

IMAGES = REPO_ROOT / "data" / "synthetic" / "images"
WEIGHTS_OUT = REPO_ROOT / "models" / "forgery" / "unet" / "weights"


# ── patch dataset ────────────────────────────────────────────────────────────────────

class PatchForgery:
    """Native-resolution patches from the 300-dpi dataset. Each item → (CHW patch, 1×H×W mask, cls).
    Sample mix: positives centred on an edit; hard negatives = clean patches + clean regions of tampered
    pages (so the model learns a number-block is not inherently tampered)."""

    def __init__(self, images_dir: Path, split: str = "train", res: int = PATCH_RES, max_samples=None,
                 seed: int = 0):
        recs = json.loads((images_dir / "labels.json").read_text())["records"]
        self.root = images_dir
        self.res = res
        self.rng = np.random.default_rng(seed)
        recs = [r for r in recs if r.get("split") == split]
        tampered = [r for r in recs if r["label"] == "tampered" and r.get("mask") and r.get("boxes")]
        clean = [r for r in recs if r["label"] == "clean"]
        self.samples: list[dict] = []
        # tampered are stored as CROPS around the edit (the crop's clean surroundings give in-patch
        # negatives for the mask loss); positives are centred on a box.
        for r in tampered:
            for b in r["boxes"][:2]:
                self.samples.append({"img": r["file"], "mask": r["mask"], "box": b, "mode": "pos"})
        # heavy clean hard-negatives from full clean pages (incl. number-columns) → balances the classifier
        # and teaches "a number block is not inherently tampered".
        n_clean_crops = max(2, (2 * len(self.samples)) // max(1, len(clean)))
        for r in clean:
            for _ in range(n_clean_crops):
                self.samples.append({"img": r["file"], "mode": "neg"})
        self.rng.shuffle(self.samples)
        if max_samples:
            self.samples = self.samples[:max_samples]

    def __len__(self):
        return len(self.samples)

    def _crop_box(self, W, H, center=None, avoid=None):
        R = self.res
        if center is not None:
            cx, cy = center
            x = int(np.clip(cx - R // 2 + self.rng.integers(-R // 4, R // 4 + 1), 0, max(0, W - R)))
            y = int(np.clip(cy - R // 2 + self.rng.integers(-R // 4, R // 4 + 1), 0, max(0, H - R)))
            return x, y
        for _ in range(8):
            x = int(self.rng.integers(0, max(1, W - R)))
            y = int(self.rng.integers(0, max(1, H - R)))
            if not avoid:
                return x, y
            ok = True
            for bx0, by0, bx1, by1 in avoid:
                if not (x + R <= bx0 or x >= bx1 or y + R <= by0 or y >= by1):
                    ok = False
                    break
            if ok:
                return x, y
        return x, y

    def __getitem__(self, i):
        from PIL import Image
        s = self.samples[i]
        img = Image.open(self.root / s["img"]).convert("RGB")
        W, H = img.size
        R = self.res
        if s["mode"] == "pos":
            bx0, by0, bx1, by1 = s["box"]
            x, y = self._crop_box(W, H, center=((bx0 + bx1) // 2, (by0 + by1) // 2))
        elif s["mode"] == "neg_avoid":
            x, y = self._crop_box(W, H, avoid=s.get("boxes"))
        else:
            x, y = self._crop_box(W, H)
        crop = np.asarray(img.crop((x, y, x + R, y + R)).resize((R, R)))
        if crop.shape[:2] != (R, R):
            crop = np.pad(crop, ((0, R - crop.shape[0]), (0, R - crop.shape[1]), (0, 0)), mode="edge")
        if s["mode"] == "pos":
            import cv2
            m = cv2.imread(str(self.root / s["mask"]), 0)
            m = m[y:y + R, x:x + R]
            if m.shape != (R, R):
                m = np.pad(m, ((0, R - m.shape[0]), (0, R - m.shape[1])), mode="constant")
            mask = (m != 0).astype(np.float32)
        else:
            mask = np.zeros((R, R), np.float32)
        cls = np.float32(1.0 if mask.sum() > 0 else 0.0)
        return preprocess(crop), mask[None], cls


def _loss(mask_logits, mask_t, cls_logits, cls_t, lam=0.4):
    import torch.nn.functional as F
    bce = F.binary_cross_entropy_with_logits(mask_logits, mask_t)
    p = mask_logits.sigmoid()
    # Tversky (FN-weighted) — edited area is a small fraction of the patch
    a, b = 0.3, 0.7
    tp = (p * mask_t).sum((2, 3))
    fp = (p * (1 - mask_t)).sum((2, 3))
    fn = ((1 - p) * mask_t).sum((2, 3))
    tversky = (1.0 - ((tp + 1.0) / (tp + a * fp + b * fn + 1.0)).mean())
    clsl = F.binary_cross_entropy_with_logits(cls_logits.squeeze(1), cls_t)
    return bce + tversky + lam * clsl


def train(args) -> None:
    try:
        import torch
        from torch.utils.data import DataLoader
    except Exception:
        sys.exit("torch not installed — pip install -r services/forensics/requirements-models.txt")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} patch={PATCH_RES} epochs={args.epochs} batch={args.batch}")
    if device == "cpu":
        print("WARNING: no CUDA — patch training on CPU is very slow. Use the GPU rig.")
    images = Path(args.images_dir) if args.images_dir else IMAGES
    ckpt = Path(args.weights) if args.weights else (WEIGHTS_OUT / "forgery.pth")
    ckpt.parent.mkdir(parents=True, exist_ok=True)

    ds = PatchForgery(images, "train", max_samples=args.max_samples, seed=args.seed)
    if len(ds) == 0:
        sys.exit("no train patches — run python -m data.generator.build_image_dataset first")
    print(f"train patches: {len(ds)}")
    loader = DataLoader(ds, batch_size=args.batch, shuffle=True, num_workers=args.workers,
                        pin_memory=(device == "cuda"), drop_last=True, persistent_workers=bool(args.workers))

    model = build_model(base=args.base).to(device)
    if args.resume and ckpt.exists():
        model.load_state_dict(torch.load(ckpt, map_location=device))
        print(f"resumed {ckpt}")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scaler = torch.amp.GradScaler("cuda", enabled=(device == "cuda"))
    model.train()
    for ep in range(args.epochs):
        t0, running = time.time(), 0.0
        for it, (x, m, c) in enumerate(loader):
            x = x.to(device, non_blocking=True); m = m.to(device, non_blocking=True).float()
            c = c.to(device, non_blocking=True).float()
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=(device == "cuda")):
                ml, cl = model(x)
                loss = _loss(ml, m, cl, c)
            scaler.scale(loss).backward(); scaler.step(opt); scaler.update()
            running += float(loss.item())
            if it % 50 == 0:
                rate = (it + 1) * args.batch / max(1e-6, time.time() - t0)
                print(f"  ep{ep} it{it}/{len(loader)} loss {running/(it+1):.4f} ({rate:.0f} img/s)", flush=True)
        torch.save(model.state_dict(), ckpt)
        print(f"epoch {ep} done in {time.time()-t0:.0f}s -> {ckpt}", flush=True)
    print(f"\nDone -> {ckpt}\nCalibrate:  python services/forensics/train_forgery.py --calibrate-only")


def calibrate(args) -> None:
    """Pick (tau_cls, tau_mask, min_area_frac) on the VAL split so doc-level clean-FP ≤ target, maximizing
    tampered recall. Writes calibration.json next to the weights (loaded by forgery_unet.infer +
    forgery_model.mask_to_regions)."""
    import torch  # noqa: F401
    from services.forensics.app.ingest import forgery_unet as fu
    ckpt = WEIGHTS_OUT / "forgery.pth"
    if not ckpt.exists():
        sys.exit("no weights — train first")
    recs = json.loads((IMAGES / "labels.json").read_text())["records"]
    val = [r for r in recs if r.get("split") == "val"]
    clean = [r for r in val if r["label"] == "clean"][: args.cal_clean]
    tamp = [r for r in val if r["label"] == "tampered"][: args.cal_tampered]
    print(f"calibrating on {len(clean)} clean + {len(tamp)} tampered val docs ...")

    def doc_probs(recs_):
        out = []
        for j, r in enumerate(recs_):
            m = fu.infer(str(IMAGES / r["file"]), str(ckpt))
            out.append(np.zeros((4, 4), np.float32) if m is None else m)
            if j % 20 == 0:
                print(f"  infer {j}/{len(recs_)}", flush=True)
        return out

    clean_m = doc_probs(clean)
    tamp_m = doc_probs(tamp)
    target_fp = args.target_fp
    best = None
    # ABSOLUTE min-area px (page-size invariant — clean val = full pages, tampered val = crops; an absolute
    # floor judges both fairly and transfers to full-page uploads). An edit at 300 dpi is ~1-7k px.
    for tau_mask in (0.5, 0.6, 0.7, 0.8, 0.9):
        for min_area_px in (128, 256, 512, 1024, 2048):
            def flagged(m):
                binm = (m >= tau_mask)
                if binm.sum() == 0:
                    return False
                import cv2
                n, lab, stats, _ = cv2.connectedComponentsWithStats(binm.astype(np.uint8), 8)
                return any(stats[k, cv2.CC_STAT_AREA] >= min_area_px for k in range(1, n))
            fp = sum(flagged(m) for m in clean_m) / max(1, len(clean_m))
            rec = sum(flagged(m) for m in tamp_m) / max(1, len(tamp_m))
            # maximize recall within the FP budget; on a tie, prefer the more conservative (larger
            # min-area → lower clean-FP) operating point so it generalizes to the test/live set.
            if fp <= target_fp and (best is None or rec > best[0]
                                    or (rec == best[0] and min_area_px > best[2])):
                best = (rec, tau_mask, min_area_px, fp)
    if best is None:                       # nothing met the budget → take the lowest-FP point
        best = (0.0, 0.9, 2048, 1.0)
    rec, tau_mask, min_area_px, fp = best
    cal = {"tau_cls": args.tau_cls, "tau_mask": tau_mask, "min_area_px": min_area_px,
           "val_clean_fp": round(fp, 4), "val_recall": round(rec, 4), "target_fp": target_fp}
    (WEIGHTS_OUT / "calibration.json").write_text(json.dumps(cal, indent=2))
    fu._MODEL_CACHE.clear()
    print(f"calibration -> {cal}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Train/calibrate the v2 forgery U-Net (GPU).")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--base", type=int, default=32)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--max-samples", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--images-dir", default=None, help="override dataset dir (e.g. a sanity temp set)")
    ap.add_argument("--weights", default=None, help="override output weights path (e.g. a sanity temp)")
    ap.add_argument("--calibrate-only", action="store_true")
    ap.add_argument("--tau-cls", dest="tau_cls", type=float, default=0.5)
    ap.add_argument("--target-fp", dest="target_fp", type=float, default=0.015)
    ap.add_argument("--cal-clean", type=int, default=60)
    ap.add_argument("--cal-tampered", type=int, default=200)
    args = ap.parse_args()
    if args.calibrate_only:
        calibrate(args)
    else:
        train(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
