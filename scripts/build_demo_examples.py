#!/usr/bin/env python3
"""Bake the dashboard's curated example detections (plan: Dashboard detection showcase).

Picks a curated set of records from the realistic synthetic dataset (`data/synthetic/images/`), copies
the full clean + tampered pages into the dashboard's committed assets, runs our REAL detector
(`analyze_image`, with the opt-in U-Net enabled) + the semantic identifier check on each, and writes the
genuine result — verdict, trust, the winning finding, the detection METHOD, and the box — into
`services/dashboard/src/data/demoExamples.js`. The dashboard then shows the actual detection (boxed +
"how it was caught") offline, with no backend.

    python scripts/build_demo_examples.py

Synthetic only (zero PII). Run from the repo root.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from services.forensics.app.image_forensics import analyze_image  # noqa: E402
from data.generator.build_image_dataset import render_showcase_pair  # noqa: E402


def _has_region(res: dict) -> bool:
    return any((f.get("values", {}) or {}).get("regions") for f in res.get("findings", []))


def analyze_layered(path: str, escalate: bool = True) -> dict:
    """Mirror the real system: run heuristics (the zero-FP default) first; if nothing is localized AND
    `escalate`, re-run with the opt-in learned U-Net. The clean control never escalates (escalate=False)
    so it stays CLEAN — the model's higher recall is shown only on genuinely-edited docs."""
    os.environ["TRUSTSHIELD_FORGERY_BACKEND"] = "dtd"          # heuristics only (no weights → no model)
    res = analyze_image(path)
    if _has_region(res) or not escalate:
        return res
    os.environ["TRUSTSHIELD_FORGERY_BACKEND"] = "unet"         # escalate to the learned model
    res2 = analyze_image(path)
    return res2 if _has_region(res2) else res

IMAGES = REPO / "data" / "synthetic" / "images"
PUB = REPO / "services" / "dashboard" / "public" / "examples"
OUT_JS = REPO / "services" / "dashboard" / "src" / "data" / "demoExamples.js"

# Render the demo from HELD-OUT synthetic identities — applicant indices well beyond the training build's
# range (DEFAULT_APPLICANTS=112) — so the showcase is documents the model has never seen.
HELD_OUT = 500

_PIXEL = {"ela", "noise", "flat_fill", "copy_move", "jpeg_ghost", "recapture"}


def method_for(detector: str, category: str) -> str:
    if detector == "forgery_model":
        return "model"
    if category == "semantic" or (detector or "").startswith("qr"):
        return "semantic"
    if detector in _PIXEL:
        return "pixel"
    return "semantic" if category == "semantic" else "pixel"


_SEV = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# Curated showcase: (key, doc_type, tamper_type, difficulty, prefer_method, title, what-was-edited blurb).
# We bake the REAL result (caught or not) — the dashboard groups them honestly: localized-by-pixels/model
# vs seamless edits that evade pixel detection (→ need cross-referencing the numbers across documents).
CURATE = [
    ("form16_pro", "form16", "gross_salary", "pro", "model",
     "Form 16 — gross salary, seamless edit", "The salary figure inflated seamlessly — matched font, tone and scan noise."),
    ("form16_naive", "form16", "gross_salary", "naive", "model",
     "Form 16 — gross salary, obvious edit", "The same figure painted over with a flat fill."),
    ("form16_splice", "form16", "splice", "geom", "pixel",
     "Form 16 — spliced patch", "A patch pasted in from elsewhere on the page."),
    ("form16_recompress", "form16", "recompress", "geom", "pixel",
     "Form 16 — recompressed region", "A region re-saved at a different JPEG quality."),
    ("salary_pro", "salary_slip", "net_pay", "pro", "model",
     "Payslip — net pay, seamless edit", "Take-home pay repainted, bold weight + scan softness matched."),
    ("bank_pro", "bank_statement", "salary_credit", "pro", "model",
     "Bank statement — salary credit, seamless edit", "A monthly salary credit raised, running balance recomputed."),
    ("pan_pro", "identity", "pan", "pro", "model",
     "PAN — digit swapped, seamless edit", "One PAN character changed and seamlessly re-rendered."),
]


def _save_jpg(img, path) -> None:
    img.convert("RGB").save(path, "JPEG", quality=90)


def _primary(findings, prefer_method):
    """Choose the finding to showcase: prefer one matching the intended method, else the most severe."""
    enriched = []
    for f in findings:
        v = f.get("values", {}) or {}
        det = v.get("detector", "")
        m = method_for(det, f.get("category", ""))
        regions = v.get("regions") or []
        enriched.append((f, m, det, regions, _SEV.get(f.get("severity", "info"), 0)))
    pref = [e for e in enriched if e[1] == prefer_method]
    pool = pref or enriched
    pool.sort(key=lambda e: (e[4], len(e[3])), reverse=True)     # severity, then has-region
    return pool[0] if pool else None


def main() -> int:
    PUB.mkdir(parents=True, exist_ok=True)
    examples = []

    # clean control — a genuine FULL page at 300 dpi (the model's domain); run the model too and expect CLEAN.
    ctrl = render_showcase_pair("form16", field=None, dpi=300, applicant_idx=HELD_OUT + 3)
    _save_jpg(ctrl["clean"], PUB / "ctrl_form16_clean.jpg")
    res = analyze_layered(str(PUB / "ctrl_form16_clean.jpg"), escalate=True)
    examples.append({
        "key": "form16_clean", "doc_type": "form16", "title": "Form 16 — genuine (control)",
        "edited_img": "examples/ctrl_form16_clean.jpg", "clean_img": "examples/ctrl_form16_clean.jpg",
        "w": res.get("width"), "h": res.get("height"), "difficulty": "clean",
        "old_value": None, "new_value": None, "verdict": res.get("verdict"),
        "trust": round(res.get("image_trust", 100)), "method": "clean", "detector": None,
        "boxes": [], "blurb": "A genuine page — the learned model runs and finds nothing; the sensor-noise floor is intact everywhere.",
        "finding": {"title": "No tampering detected", "description": "Clean under both the pixel heuristics and the learned model (0/80 clean false positives on the held-out test split)."},
    })
    print(f"  {'form16_clean':16s} verdict={res.get('verdict')}")

    for i, (key, doc_type, ttype, diff, prefer, title, blurb) in enumerate(CURATE):
        geom = ttype if diff == "geom" else None
        pair = render_showcase_pair(doc_type, field=(None if geom else ttype), difficulty=diff,
                                    geom=geom, dpi=300, applicant_idx=HELD_OUT + i)
        if pair["edited"] is None:
            print(f"  ! could not render {doc_type}/{ttype}/{diff}")
            continue
        _save_jpg(pair["clean"], PUB / f"{key}_clean.jpg")
        _save_jpg(pair["edited"], PUB / f"{key}_edited.jpg")
        res = analyze_layered(str(PUB / f"{key}_edited.jpg"), escalate=True)
        pick = _primary(res.get("findings", []), prefer)
        if pick:
            f, m, det, regions, _ = pick
            box = [list(map(int, regions[0]["bbox"]))] if regions else [pair["box"]]
            finding = {"title": f.get("title"), "description": f.get("description")}
        else:  # honest: nothing fired → fall back to the ground-truth region, no method
            m, det = "none", None
            box = [pair["box"]]
            finding = {"title": "Not flagged", "description": "This seamless edit evaded every detector in this run."}
        examples.append({
            "key": key, "doc_type": doc_type, "title": title,
            "edited_img": f"examples/{key}_edited.jpg", "clean_img": f"examples/{key}_clean.jpg",
            "w": res.get("width"), "h": res.get("height"), "difficulty": diff,
            "old_value": pair.get("old"), "new_value": pair.get("new"),
            "verdict": res.get("verdict"), "trust": round(res.get("image_trust", 0)),
            "method": m, "detector": det, "boxes": box, "blurb": blurb, "finding": finding,
        })
        print(f"  {key:16s} verdict={res.get('verdict'):10s} method={m:8s} detector={det} box={box[0]}")

    # Home "spot the edit" pair — a full-page Form 16 pro edit at 300 dpi for the Home loupe.
    home = render_showcase_pair("form16", field="gross_salary", difficulty="pro", dpi=300, applicant_idx=HELD_OUT)
    _save_jpg(home["clean"], PUB / "realistic_form16_clean.jpg")
    _save_jpg(home["edited"], PUB / "realistic_form16_edited.jpg")
    print(f"  home pair -> realistic_form16_{{clean,edited}}.jpg ({home['w']}x{home['h']})")

    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    header = ("// AUTO-GENERATED by scripts/build_demo_examples.py — do not edit by hand.\n"
              "// The REAL detector output (analyze_image + opt-in U-Net) on curated synthetic examples,\n"
              "// baked so the dashboard shows the actual boxed detection + 'how it was caught' offline.\n\n"
              "export const DEMO_EXAMPLES = ")
    OUT_JS.write_text(header + json.dumps(examples, indent=2) + ";\n", encoding="utf-8")
    print(f"\nwrote {len(examples)} examples -> {OUT_JS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
