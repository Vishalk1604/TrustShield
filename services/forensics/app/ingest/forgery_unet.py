"""Two-stream noise-aware forgery-localization U-Net v2 (plan §11.2) — torch-only.

Why v2: v1 ran the *whole page downscaled to 256²*, which erases the sub-pixel sensor-noise mismatch that
betrays a seamless edit — so it could only learn content/position and over-fired on clean Form 16s. v2
fixes this with:
  - **Native-resolution patches** (`PATCH_RES`): train + tile at real resolution so the noise signal survives.
  - **A noise-residual stream**: fixed **SRM** high-pass kernels + a learnable **BayarConv** (constrained,
    content-suppressing) concatenated with RGB → the encoder keys on noise statistics, not document layout.
  - **A per-patch tamper-classifier head**: gates the mask at inference so clean patches don't leak blobs
    (the FP control that the earlier patch attempt lacked).

Shared by the trainer (`services/forensics/train_forgery.py`) and the inference seam
(`ingest/forgery_model.py`, backend `unet`). **torch is OPTIONAL**: the module imports without it; only
`build_model()`/`infer()` need it. No network at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

PATCH_RES = 384                          # native patch / tile size (fits an 8 GB GPU with the 2-stream net)
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Classic SRM high-pass residual kernels (RGB-N / CAT-Net family) — fixed, content-suppressing.
_SRM = [
    (np.array([[0, 0, 0, 0, 0], [0, -1, 2, -1, 0], [0, 2, -4, 2, 0], [0, -1, 2, -1, 0], [0, 0, 0, 0, 0]],
              dtype=np.float32) / 4.0),
    (np.array([[-1, 2, -2, 2, -1], [2, -6, 8, -6, 2], [-2, 8, -12, 8, -2], [2, -6, 8, -6, 2],
               [-1, 2, -2, 2, -1]], dtype=np.float32) / 12.0),
    (np.array([[0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 1, -2, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0]],
              dtype=np.float32) / 2.0),
]


def build_model(base: int = 32):
    """Construct the two-stream noise-aware U-Net + classifier head (requires torch). Defined inside the
    fn so the module imports without torch. Input: B×3×H×W normalized RGB. Output: (mask_logits B×1×H×W,
    cls_logits B×1)."""
    import torch
    import torch.nn as nn

    class BayarConv(nn.Module):
        """Constrained high-pass conv (Bayar & Stamm): centre tap = -1, the rest sum to +1 → suppresses
        content, exposes tampering residuals. Re-normalized every forward."""
        def __init__(self, cin=3, cout=3, k=5):
            super().__init__()
            self.k = k
            self.w = nn.Parameter(torch.randn(cout, cin, k, k) * 0.01)

        def forward(self, x):
            w = self.w.clone()
            c = self.k // 2
            w[:, :, c, c] = 0.0
            w = w / (w.sum(dim=(2, 3), keepdim=True) + 1e-6)
            w[:, :, c, c] = -1.0
            return torch.nn.functional.conv2d(x, w, padding=c)

    class NoiseStem(nn.Module):
        """RGB (3) ⊕ SRM residuals (3) ⊕ BayarConv residuals (3) → 9-channel input."""
        def __init__(self):
            super().__init__()
            srm = torch.zeros(3, 3, 5, 5)
            for i, k in enumerate(_SRM):
                srm[i] = torch.from_numpy(k)            # same kernel summed over the 3 RGB channels
            self.register_buffer("srm", srm)
            self.bayar = BayarConv(3, 3, 5)

        def forward(self, x):
            srm = torch.nn.functional.conv2d(x, self.srm, padding=2)
            bay = self.bayar(x)
            return torch.cat([x, srm, bay], dim=1)

    class DoubleConv(nn.Module):
        def __init__(self, cin, cout):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
            )

        def forward(self, x):
            return self.net(x)

    class UNet2(nn.Module):
        def __init__(self, base=32):
            super().__init__()
            self.stem = NoiseStem()
            self.d1 = DoubleConv(9, base)
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
            self.cls = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(),
                                     nn.Linear(base * 16, base * 4), nn.ReLU(inplace=True),
                                     nn.Linear(base * 4, 1))

        def forward(self, x):
            x = self.stem(x)
            c1 = self.d1(x)
            c2 = self.d2(self.pool(c1))
            c3 = self.d3(self.pool(c2))
            c4 = self.d4(self.pool(c3))
            b = self.bott(self.pool(c4))
            cls = self.cls(b)                              # B×1 — "is this patch tampered?"
            x = self.u4(torch.cat([self.up4(b), c4], 1))
            x = self.u3(torch.cat([self.up3(x), c3], 1))
            x = self.u2(torch.cat([self.up2(x), c2], 1))
            x = self.u1(torch.cat([self.up1(x), c1], 1))
            return self.out(x), cls                        # mask logits, cls logit

    return UNet2(base)


# Back-compat alias (the old name) so any caller importing build_unet still works.
def build_unet(base: int = 32):
    return build_model(base)


def preprocess(img_rgb: np.ndarray):
    """HxWx3 uint8 → normalized CHW float32 (numpy)."""
    a = img_rgb.astype(np.float32) / 255.0
    a = (a - _MEAN) / _STD
    return a.transpose(2, 0, 1)


_MODEL_CACHE: dict = {}
_DEFAULT_CAL = {"tau_cls": 0.5, "tau_mask": 0.5, "min_area_frac": 0.0008}


def _load(weights_path: str):
    import torch
    key = str(weights_path)
    cached = _MODEL_CACHE.get(key)
    if cached is None:
        model = build_model()
        sd = torch.load(weights_path, map_location="cpu")
        model.load_state_dict(sd.get("model", sd) if isinstance(sd, dict) else sd)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(device).eval()
        cal_path = Path(weights_path).with_name("calibration.json")
        cal = json.loads(cal_path.read_text()) if cal_path.exists() else dict(_DEFAULT_CAL)
        cached = (model, device, cal)
        _MODEL_CACHE[key] = cached
    return cached


def infer(image_path: str, weights_path: str) -> Optional[np.ndarray]:
    """Calibrated **tiled** inference → a full-resolution tamper-probability mask (or None).

    Overlapping native tiles (PATCH_RES, 25% overlap); per tile the classifier head gates the mask
    (clean patches contribute nothing) and logits are *averaged* in overlaps (not OR-ed) — this is what
    controls the false-positive compounding that sank v1's tiled attempt. Thresholds + min-area are
    applied by the caller (`forgery_model.mask_to_regions`) from the same `calibration.json`."""
    try:
        import torch
        from PIL import Image

        model, device, cal = _load(weights_path)
        tau_cls = float(cal.get("tau_cls", 0.5))
        img = Image.open(image_path).convert("RGB")
        W, H = img.size
        arr = np.asarray(img)
        R = PATCH_RES
        stride = int(R * 0.75)
        prob = np.zeros((H, W), np.float32)
        wsum = np.zeros((H, W), np.float32)
        xs = list(range(0, max(1, W - R + 1), stride)) or [0]
        ys = list(range(0, max(1, H - R + 1), stride)) or [0]
        if xs[-1] != max(0, W - R):
            xs.append(max(0, W - R))
        if ys[-1] != max(0, H - R):
            ys.append(max(0, H - R))
        with torch.no_grad():
            for yy in ys:
                for xx in xs:
                    crop = arr[yy:yy + R, xx:xx + R]
                    ph, pw = crop.shape[:2]
                    if (ph, pw) != (R, R):              # pad edge tiles
                        crop = np.pad(crop, ((0, R - ph), (0, R - pw), (0, 0)), mode="edge")
                    x = torch.from_numpy(preprocess(crop)).unsqueeze(0).to(device)
                    mlog, clog = model(x)
                    cls_p = float(torch.sigmoid(clog)[0, 0])
                    m = torch.sigmoid(mlog)[0, 0].cpu().numpy()
                    if cls_p < tau_cls:                  # classifier gate → clean tile contributes 0
                        m = m * 0.0
                    prob[yy:yy + ph, xx:xx + pw] += m[:ph, :pw]
                    wsum[yy:yy + ph, xx:xx + pw] += 1.0
        wsum[wsum == 0] = 1.0
        return prob / wsum
    except Exception:
        return None
