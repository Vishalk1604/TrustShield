"""Self-contained forgery-localization U-Net (plan §10 Phase 5) — torch-only.

The published DocTamper DTD checkpoint is gated, and the exact DTD pipeline needs `jpegio` (a JPEG-DCT
reader that is very hard to build on Windows). So instead of forcing that, we train **our own** compact
forgery-localization network on the data we *do* hold — the DocTamper LMDB (120k RGB document images +
tamper masks) — using only **torch** (no jpegio, no segmentation-models, no timm). It's a standard U-Net
that maps an RGB document image to a per-pixel tamper-probability mask.

This module is shared by the trainer (`services/forensics/train_forgery.py`) and the inference seam
(`ingest/forgery_model.py`, backend `unet`). **torch is OPTIONAL**: the module imports without it (the
model class is built inside `build_unet()`); only `build_unet()`/`infer()` require torch. The seam stays
heuristic until `models/forgery/unet/weights/*.pth` exists. No network at runtime.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

TRAIN_RES = 256                          # train/infer at 256x256 (fits an 8 GB GPU comfortably)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def build_unet(base: int = 32):
    """Construct the U-Net (requires torch). Defined inside the fn so the module imports without torch."""
    import torch
    import torch.nn as nn

    class DoubleConv(nn.Module):
        def __init__(self, cin, cout):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
            )

        def forward(self, x):
            return self.net(x)

    class UNet(nn.Module):
        def __init__(self, base=32):
            super().__init__()
            self.d1 = DoubleConv(3, base)
            self.d2 = DoubleConv(base, base * 2)
            self.d3 = DoubleConv(base * 2, base * 4)
            self.d4 = DoubleConv(base * 4, base * 8)
            self.bott = DoubleConv(base * 8, base * 16)
            self.pool = nn.MaxPool2d(2)
            self.up4 = nn.ConvTranspose2d(base * 16, base * 8, 2, stride=2)
            self.u4 = DoubleConv(base * 16, base * 8)
            self.up3 = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
            self.u3 = DoubleConv(base * 8, base * 4)
            self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
            self.u2 = DoubleConv(base * 4, base * 2)
            self.up1 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
            self.u1 = DoubleConv(base * 2, base)
            self.out = nn.Conv2d(base, 1, 1)

        def forward(self, x):
            c1 = self.d1(x)
            c2 = self.d2(self.pool(c1))
            c3 = self.d3(self.pool(c2))
            c4 = self.d4(self.pool(c3))
            b = self.bott(self.pool(c4))
            x = self.u4(torch.cat([self.up4(b), c4], 1))
            x = self.u3(torch.cat([self.up3(x), c3], 1))
            x = self.u2(torch.cat([self.up2(x), c2], 1))
            x = self.u1(torch.cat([self.up1(x), c1], 1))
            return self.out(x)             # raw logits (HxW); apply sigmoid for probability

    return UNet(base)


def preprocess(img_rgb: np.ndarray):
    """HxWx3 uint8 → normalized CHW float32 tensor-ready array (numpy)."""
    a = img_rgb.astype(np.float32) / 255.0
    a = (a - _MEAN) / _STD
    return a.transpose(2, 0, 1)


_MODEL_CACHE: dict = {}


def infer(image_path: str, weights_path: str) -> Optional[np.ndarray]:
    """Load the U-Net (cached) + run it on one image → HxW tamper-probability mask (at TRAIN_RES).
    Returns None on any failure. The seam's `mask_to_regions` upscales + boxes it."""
    try:
        import torch
        from PIL import Image

        key = str(weights_path)
        model = _MODEL_CACHE.get(key)
        if model is None:
            model = build_unet()
            sd = torch.load(weights_path, map_location="cpu")
            model.load_state_dict(sd.get("model", sd) if isinstance(sd, dict) else sd)
            model.eval()
            _MODEL_CACHE[key] = model
        img = Image.open(image_path).convert("RGB").resize((TRAIN_RES, TRAIN_RES), Image.BILINEAR)
        x = torch.from_numpy(preprocess(np.asarray(img))).unsqueeze(0)
        with torch.no_grad():
            prob = torch.sigmoid(model(x))[0, 0].cpu().numpy()
        return prob
    except Exception:
        return None
