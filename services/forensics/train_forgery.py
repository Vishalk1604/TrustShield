#!/usr/bin/env python3
"""Train our OWN forgery-localization weights (plan §10 Phase 5) — GPU machine, torch-only.

The published DocTamper checkpoint is gated, and the exact DTD pipeline needs `jpegio` (a JPEG-DCT
reader that is painful to build on Windows). So we train our own compact **U-Net** (defined in
`services/forensics/app/ingest/forgery_unet.py`) on the data we DO hold — the **DocTamper LMDB**
(120k RGB document images + tamper masks in `models/doctamper/data/`) — then optionally fine-tune on
our Day-2 synthetic tamper set. Output → `models/forgery/unet/weights/forgery.pth`, which the seam
(`ingest/forgery_model.py`, backend `unet`) auto-detects. torch only; no jpegio/smp/timm; no network.

    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128   # Blackwell GPU
    pip install lmdb six                                                                # LMDB reader
    # quick run (subset, proves the pipeline + a usable baseline):
    python services/forensics/train_forgery.py --max-samples 12000 --epochs 3 --batch 16
    # then measure the uplift:
    TRUSTSHIELD_FORGERY_BACKEND=unet python scripts/eval_image_forensics.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from services.forensics.app.ingest.forgery_unet import TRAIN_RES, build_unet, preprocess  # noqa: E402

DOC_DATA = REPO_ROOT / "models" / "doctamper" / "data"
WEIGHTS_OUT = REPO_ROOT / "models" / "forgery" / "unet" / "weights"


# ── datasets ──────────────────────────────────────────────────────────────────────

class LmdbForgery:
    """DocTamper LMDB → (CHW float image, 1xHxW float mask) at TRAIN_RES. RGB only (no jpegio)."""

    def __init__(self, root: Path, max_samples=None):
        import lmdb
        self.env = lmdb.open(str(root), readonly=True, lock=False, readahead=False, meminit=False)
        with self.env.begin() as txn:
            n = int(txn.get(b"num-samples"))
        self.n = min(n, max_samples) if max_samples else n

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        import io

        import cv2
        from PIL import Image
        with self.env.begin() as txn:
            buf = io.BytesIO(txn.get(b"image-%09d" % i))
            im = Image.open(buf).convert("RGB").resize((TRAIN_RES, TRAIN_RES), Image.BILINEAR)
            m = cv2.imdecode(np.frombuffer(txn.get(b"label-%09d" % i), np.uint8), 0)
        mask = (m != 0).astype(np.float32)
        mask = cv2.resize(mask, (TRAIN_RES, TRAIN_RES), interpolation=cv2.INTER_NEAREST)
        return preprocess(np.asarray(im)), mask[None, :, :]


class SynthForgery:
    """Our Day-2 synthetic tamper set (tampered jpg + mask png from labels.json) for fine-tuning."""

    def __init__(self, images_dir: Path):
        import json
        recs = json.loads((images_dir / "labels.json").read_text())["records"]
        self.items = [(images_dir / r["file"], images_dir / r["mask"])
                      for r in recs if r["label"] == "tampered" and r.get("mask")]
        self.root = images_dir

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        import cv2
        from PIL import Image
        fp, mp = self.items[i]
        im = Image.open(fp).convert("RGB").resize((TRAIN_RES, TRAIN_RES), Image.BILINEAR)
        m = cv2.imread(str(mp), 0)
        mask = (m != 0).astype(np.float32)
        mask = cv2.resize(mask, (TRAIN_RES, TRAIN_RES), interpolation=cv2.INTER_NEAREST)
        return preprocess(np.asarray(im)), mask[None, :, :]


def _dice_bce(logits, target):
    import torch.nn.functional as F
    bce = F.binary_cross_entropy_with_logits(logits, target)
    p = logits.sigmoid()
    inter = (p * target).sum((2, 3))
    union = p.sum((2, 3)) + target.sum((2, 3))
    dice = 1.0 - ((2 * inter + 1.0) / (union + 1.0)).mean()
    return bce + dice


def train(args) -> None:
    try:
        import torch
        from torch.utils.data import DataLoader
    except Exception:
        sys.exit("torch not installed — pip install torch torchvision (cu128 for a Blackwell GPU).")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} res={TRAIN_RES} epochs={args.epochs} batch={args.batch} "
          f"max_samples={args.max_samples} finetune={args.finetune}")
    if device == "cpu":
        print("WARNING: no CUDA — training on CPU will be very slow. Use a GPU machine.")

    WEIGHTS_OUT.mkdir(parents=True, exist_ok=True)
    ckpt = WEIGHTS_OUT / "forgery.pth"

    if args.finetune:
        ds = SynthForgery(REPO_ROOT / "data" / "synthetic" / "images")
    else:
        split = DOC_DATA / "DocTamperV1-TrainingSet"
        if not split.exists():
            sys.exit(f"DocTamper LMDB missing at {split}")
        ds = LmdbForgery(split, max_samples=args.max_samples)
    print(f"dataset: {len(ds)} samples")
    loader = DataLoader(ds, batch_size=args.batch, shuffle=True, num_workers=args.workers,
                        pin_memory=(device == "cuda"), drop_last=True)

    model = build_unet(base=args.base).to(device)
    if args.finetune and ckpt.exists():
        model.load_state_dict(torch.load(ckpt, map_location=device))
        print(f"loaded base weights from {ckpt} for fine-tuning")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scaler = torch.amp.GradScaler("cuda", enabled=(device == "cuda"))

    model.train()
    for ep in range(args.epochs):
        t0, running = time.time(), 0.0
        for it, (x, y) in enumerate(loader):
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True).float()
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=(device == "cuda")):
                loss = _dice_bce(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            running += float(loss.item())
            if it % 50 == 0:
                rate = (it + 1) * args.batch / max(1e-6, time.time() - t0)
                print(f"  ep{ep} it{it}/{len(loader)} loss {running / (it + 1):.4f} "
                      f"({rate:.0f} img/s)", flush=True)
        torch.save(model.state_dict(), ckpt)
        print(f"epoch {ep} done in {time.time() - t0:.0f}s — saved {ckpt}", flush=True)

    print(f"\nDone. Weights at {ckpt}\n"
          f"Enable + measure:  TRUSTSHIELD_FORGERY_BACKEND=unet python scripts/eval_image_forensics.py")


def main() -> int:
    ap = argparse.ArgumentParser(description="Train forgery-localization U-Net (GPU).")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--base", type=int, default=32, help="U-Net base channels (memory/quality knob)")
    ap.add_argument("--max-samples", type=int, default=None, help="subset of the DocTamper LMDB")
    ap.add_argument("--workers", type=int, default=0, help="DataLoader workers (0 is safest on Windows)")
    ap.add_argument("--finetune", action="store_true", help="fine-tune existing weights on our synthetic set")
    train(ap.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
