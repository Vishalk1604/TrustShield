#!/usr/bin/env python3
"""Synthetic->real anchor (plan §11 Upgrade 3).

Runs the image-forensics pipeline on the REAL PAN/Aadhaar original/edited pairs in data/real/kyc and
reports detection. This is the TRUE test of whether a model fine-tuned on SYNTHETIC documents transfers
to REAL ones — the synthetic-to-real gap. The real docs are PII (gitignored); this prints numbers only
and writes nothing containing image content.

    # heuristics only:
    python scripts/eval_real_anchor.py
    # with the fine-tuned forgery U-Net:
    TRUSTSHIELD_FORGERY_BACKEND=unet python scripts/eval_real_anchor.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from services.forensics.app.image_forensics import analyze_image  # noqa: E402

KYC = REPO / "data" / "real" / "kyc"
_EXTS = (".jpg", ".jpeg", ".png")


def _flagged(res: dict) -> bool:
    return any(f.get("values", {}).get("regions") for f in res.get("findings", []))


def _kind(name: str) -> str | None:
    n = name.lower()
    if "edited" in n:
        return "edited"
    if "original" in n or "oridinal" in n:   # the fixtures use both spellings
        return "original"
    return None


def main() -> int:
    if not KYC.exists():
        print(f"no real KYC docs at {KYC} — nothing to anchor against.")
        return 0
    print(f"backend: {os.environ.get('TRUSTSHIELD_FORGERY_BACKEND', 'dtd')}")
    agg = {"original": {"n": 0, "flagged": 0}, "edited": {"n": 0, "flagged": 0}}
    for p in sorted(KYC.rglob("*")):
        if p.suffix.lower() not in _EXTS:
            continue
        kind = _kind(p.name)
        if kind is None:
            continue
        res = analyze_image(str(p))
        fl = _flagged(res)
        agg[kind]["n"] += 1
        agg[kind]["flagged"] += int(fl)
        print(f"  {kind:8s} {p.parent.name}/{p.name:30s} -> {'FLAGGED' if fl else 'clean':8s} "
              f"(verdict {res.get('verdict')})")
    o, e = agg["original"], agg["edited"]
    print(f"\nORIGINALS (want clean): {o['flagged']}/{o['n']} flagged "
          f"-> real false-positive rate {o['flagged'] / max(1, o['n']):.2f}")
    print(f"EDITED    (want flag) : {e['flagged']}/{e['n']} flagged "
          f"-> real recall {e['flagged'] / max(1, e['n']):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
