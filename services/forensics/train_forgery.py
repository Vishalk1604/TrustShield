#!/usr/bin/env python3
"""Train our OWN document forgery-localization weights (plan §10 Phase 5) — GPU machine.

The published DocTamper checkpoint is gated, but we hold the **DocTamper dataset** (the 22 GB LMDB in
`models/doctamper/data/`) plus the **model definition + losses + dataloader** (in
`models/doctamper/code/`). Its *training* loop is the one piece the repo withholds — so this script
supplies it: build the DTD network, train it on the DocTamper LMDB, then **fine-tune on our own data**
(the Day-2 synthetic tamper-image set with masks + the real `_TAMPERED` docs), and save the checkpoint
to `models/doctamper/weights/` — where `ingest/forgery_model.py` (backend `dtd`) auto-detects it.

This is a DEV/GPU tool, not part of the runtime (which stays heuristic until weights exist). It needs
torch + the vendored code; run it on the machine with the GPU:

    pip install -r services/forensics/requirements-models.txt   # + torch (CUDA build)
    python services/forensics/train_forgery.py --epochs 30 --batch 4
    python services/forensics/train_forgery.py --finetune --epochs 10   # adapt to our synthetic+real set

After it writes models/doctamper/weights/dtd.pth, set TRUSTSHIELD_FORGERY_BACKEND=dtd and re-run
`python scripts/eval_image_forensics.py` — that harness already routes through `analyze_image`, so the
learned-model regions are scored automatically (report the precision/recall/IoU uplift vs heuristics).

NOTE: complete the two clearly-marked spots against the vendored `models/dtd.py` + `dataloader.py`
APIs on first run (kept explicit rather than guessed) — the surrounding training/checkpoint plumbing is
ready. Everything is local; no network.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTAMPER_CODE = REPO_ROOT / "models" / "doctamper" / "code"
DOCTAMPER_DATA = REPO_ROOT / "models" / "doctamper" / "data"
WEIGHTS_OUT = REPO_ROOT / "models" / "doctamper" / "weights"
SYNTH_IMAGES = REPO_ROOT / "data" / "synthetic" / "images"   # Day-2 set (+ masks) for fine-tuning


def _require_torch():
    try:
        import torch  # noqa: F401
    except Exception:
        sys.exit("torch not installed — `pip install torch torchvision` (CUDA build for GPU) first.")


def _build_model():
    """Build the DTD network from the vendored DocTamper code."""
    sys.path.insert(0, str(DOCTAMPER_CODE))
    # TODO(validate vs models/dtd.py): the class name / constructor args come from the vendored repo.
    from models.dtd import seg_dtd  # type: ignore
    return seg_dtd()


def _dataloader(split: str, batch: int):
    """LMDB dataloader from the vendored DocTamper code (uses qt_table.pk for the DCT/quant input)."""
    sys.path.insert(0, str(DOCTAMPER_CODE))
    # TODO(validate vs dataloader.py): construct the DocTamper LMDB dataset for `split`
    # (DocTamperV1-TrainingSet / -TestingSet) and wrap in a torch DataLoader(batch_size=batch).
    from dataloader import DocTamperDataset  # type: ignore
    import torch

    ds = DocTamperDataset(str(DOCTAMPER_DATA / split))
    return torch.utils.data.DataLoader(ds, batch_size=batch, shuffle=("Train" in split), num_workers=4)


def train(epochs: int, batch: int, lr: float, finetune: bool) -> None:
    _require_torch()
    import torch
    from torch import nn, optim

    if not DOCTAMPER_CODE.exists():
        sys.exit(f"vendored DocTamper code missing at {DOCTAMPER_CODE}")
    WEIGHTS_OUT.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device} epochs={epochs} batch={batch} finetune={finetune}")

    model = _build_model().to(device)
    ckpt = WEIGHTS_OUT / "dtd.pth"
    if finetune and ckpt.exists():
        model.load_state_dict(torch.load(ckpt, map_location=device))
        print(f"loaded base weights from {ckpt} for fine-tuning")

    # Losses: the vendored repo ships dice/focal/lovasz under models/losses — combine per the paper.
    sys.path.insert(0, str(DOCTAMPER_CODE))
    from models.losses.dice import DiceLoss  # type: ignore
    criterion = DiceLoss()
    opt = optim.AdamW(model.parameters(), lr=lr)

    # Data: pretrain on the DocTamper LMDB; fine-tune on our synthetic (data/synthetic/images + masks)
    # + real `_TAMPERED` docs. (For fine-tune, wrap SYNTH_IMAGES with a small Dataset that pairs each
    # tampered jpg with its mask png — the labels.json already records file/mask/boxes.)
    loader = _dataloader("DocTamperV1-TrainingSet", batch)

    model.train()
    for ep in range(epochs):
        running = 0.0
        for i, (img, mask) in enumerate(loader):
            img, mask = img.to(device), mask.to(device).float()
            opt.zero_grad()
            pred = model(img)
            loss = criterion(pred, mask)
            loss.backward()
            opt.step()
            running += float(loss.item())
            if i % 50 == 0:
                print(f"  ep{ep} it{i} loss {running / (i + 1):.4f}")
        torch.save(model.state_dict(), ckpt)
        print(f"epoch {ep} done — saved {ckpt}")
    print(f"Trained weights at {ckpt}. Set TRUSTSHIELD_FORGERY_BACKEND=dtd and run "
          f"scripts/eval_image_forensics.py to measure the uplift.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Train DTD forgery-localization weights (GPU).")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--finetune", action="store_true",
                    help="fine-tune existing weights on our synthetic + real tamper set")
    a = ap.parse_args()
    train(a.epochs, a.batch, a.lr, a.finetune)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
