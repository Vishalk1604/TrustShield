#!/usr/bin/env python3
"""Assemble the browsable, cross-verified `demo/` corpus (plan: demo/ corpus).

Pulls from the committed realistic synthetic corpus (`data/synthetic/images/` + `.../packets/` +
`labels.json`) — it does NOT tamper anything new — and lays out a human-browsable folder:

    demo/
      README.md
      documents/<doc_type>/  clean.jpg + {naive,blended,pro}_edited.jpg + {splice,recompress}_edited.jpg
                             + manifest.json   (per edit: old->new, ground-truth box, AND the
                                                cross-verified detector result: heuristics vs U-Net)
      packets/<PKT-id>/      the packet's docs + manifest.json (copied) + verification.json
                             (full-pipeline trust score, action, evidence chain incl. cross-document
                              reconciliation + cross-application graph findings)
      MANIFEST.json          index + a caught/missed summary across everything

It also bakes the Home "spot the edit" detection box into
`services/dashboard/src/data/homeReveal.js` (the model's box on the Home Form-16 pair) for the loupe.

Cross-verify = both: per-document detector output AND per-packet pipeline/graph reconciliation.
100% local, synthetic, zero PII. Run from the repo root:

    .venv/Scripts/python.exe scripts/build_demo_folder.py
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from services.forensics.app.image_forensics import analyze_image  # noqa: E402
from data.generator.build_image_dataset import render_showcase_pair  # noqa: E402


def _save_jpg(img, path) -> None:
    img.convert("RGB").save(path, "JPEG", quality=90)

IMAGES = REPO / "data" / "synthetic" / "images"
PACKETS_DIR = REPO / "data" / "synthetic" / "packets"
LABELS_PATH = REPO / "data" / "synthetic" / "labels.json"
DEMO = REPO / "demo"
HOME_CLEAN = REPO / "services" / "dashboard" / "public" / "examples" / "realistic_form16_clean.jpg"
HOME_EDITED = REPO / "services" / "dashboard" / "public" / "examples" / "realistic_form16_edited.jpg"
HOME_JS = REPO / "services" / "dashboard" / "src" / "data" / "homeReveal.js"

# What to showcase per doc type: the primary figure edit (across difficulties) + geometric edits.
DOC_PLAN = {
    "form16":         {"figure": "gross_salary",   "label": "Form 16"},
    "bank_statement": {"figure": "salary_credit",  "label": "Bank statement"},
    "salary_slip":    {"figure": "net_pay",        "label": "Salary slip"},
    "identity":       {"figure": "pan",            "label": "PAN card"},
    "aadhaar":        {"figure": "aadhaar_number", "label": "Aadhaar"},
}
FIGURE_DIFFS = ["naive", "blended", "pro"]
GEOM_TYPES = ["splice", "recompress"]

# Curated packets (the validated demo set from scripts/seed_demo.py): clean + one per fraud shape + ring.
DEMO_PACKETS = ["PKT-0001", "PKT-0010", "PKT-0014", "PKT-0028", "PKT-0031", "PKT-0032", "PKT-0033", "PKT-0018"]

_PIXEL = {"ela", "noise", "flat_fill", "copy_move", "jpeg_ghost", "recapture"}
_SEV = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def method_for(detector: str, category: str) -> str:
    """Same mapping the dashboard uses (build_demo_examples.method_for) — kept in sync deliberately."""
    if detector == "forgery_model":
        return "model"
    if category == "semantic" or (detector or "").startswith("qr"):
        return "semantic"
    if detector in _PIXEL:
        return "pixel"
    return "semantic" if category == "semantic" else "pixel"


def _primary_box_method(res: dict):
    """The most-severe localized finding's box + method (or None, 'none')."""
    best = None
    for f in res.get("findings", []):
        v = f.get("values", {}) or {}
        regions = v.get("regions") or []
        if not regions:
            continue
        sev = _SEV.get(f.get("severity", "info"), 0)
        if best is None or sev > best[0]:
            box = regions[0].get("bbox") if isinstance(regions[0], dict) else regions[0]
            best = (sev, list(map(int, box)), method_for(v.get("detector", ""), f.get("category", "")))
    if best is None:
        return None, "none"
    return best[1], best[2]


def verify_doc(path: Path) -> dict:
    """Cross-verify one document image: heuristics (zero-FP default) vs the opt-in learned U-Net."""
    heur = analyze_image(str(path), learned="off")
    model = analyze_image(str(path), learned="auto")
    m_box, m_method = _primary_box_method(model)
    return {
        "heuristics": {"verdict": heur["verdict"], "trust": round(heur["image_trust"])},
        "model": {"verdict": model["verdict"], "trust": round(model["image_trust"]),
                  "box": m_box, "available": bool((model.get("signals", {}).get("learned_model") or {}).get("available"))},
        "method": m_method if m_method != "none" else method_for(*_heur_method(heur)),
    }


def _heur_method(res: dict):
    for f in res.get("findings", []):
        v = f.get("values", {}) or {}
        if v.get("regions"):
            return v.get("detector", ""), f.get("category", "")
    return "", ""


def _records():
    return json.loads((IMAGES / "labels.json").read_text())["records"]


def _pick_source(records, doc_type, figure):
    """A source applicant that covers the most figure-edit difficulties (so clean vs edited compare)."""
    by_src = defaultdict(set)
    for r in records:
        if r["label"] == "tampered" and r["doc_type"] == doc_type and r["tamper_type"] == figure:
            by_src[r["source"]].add(r["difficulty"])
    if not by_src:
        return None
    for pref in ("rahul", "priya", "amit"):
        cand = [s for s in by_src if s.startswith(pref)]
        if cand:
            return max(cand, key=lambda s: len(by_src[s]))
    return max(by_src, key=lambda s: len(by_src[s]))


def _find(records, doc_type, tamper_type, difficulty, source=None):
    for r in records:
        if (r["label"] == "tampered" and r["doc_type"] == doc_type and r["tamper_type"] == tamper_type
                and r["difficulty"] == difficulty and (source is None or r["source"] == source)):
            return r
    if source is not None:   # fall back to any source at this difficulty
        return _find(records, doc_type, tamper_type, difficulty, None)
    return None


# distinct procedural applicant per doc type → varied, judge-friendly showcase documents
_DOC_APPLICANT = {"form16": 0, "salary_slip": 1, "bank_statement": 2, "identity": 3, "aadhaar": 4}


def build_documents() -> list[dict]:
    """Render matched **full-page** clean+edited pairs at 300 dpi (judges open the whole document, not a
    crop), each cross-verified by the detector. Uses render_showcase_pair so the showcase matches the
    trained-on distribution exactly; the clean page is the shared base for every edited variant."""
    out = []
    docs_root = DEMO / "documents"
    for doc_type, plan in DOC_PLAN.items():
        idx = _DOC_APPLICANT.get(doc_type, 0)
        d = docs_root / doc_type
        d.mkdir(parents=True, exist_ok=True)
        base = render_showcase_pair(doc_type, field=None, dpi=300, applicant_idx=idx)
        _save_jpg(base["clean"], d / "clean.jpg")              # full page
        clean_v = verify_doc(d / "clean.jpg")
        edits = {}
        variants = [(diff, plan["figure"], diff, None) for diff in FIGURE_DIFFS]
        variants += [(g, None, "geom", g) for g in GEOM_TYPES]
        for out_key, field, diff, geom in variants:
            pair = render_showcase_pair(doc_type, field=field, difficulty=diff, geom=geom,
                                        dpi=300, applicant_idx=idx)
            if pair["edited"] is None:
                continue
            fname = f"{out_key}_edited.jpg"
            _save_jpg(pair["edited"], d / fname)               # full page (matches clean.jpg)
            v = verify_doc(d / fname)
            edits[out_key] = {
                "file": fname, "tamper_type": (geom or field), "difficulty": diff,
                "old_value": pair.get("old"), "new_value": pair.get("new"),
                "ground_truth_box": pair.get("box"),
                "cross_verified": v,
            }
        manifest = {
            "doc_type": doc_type, "label": plan["label"], "applicant_idx": idx,
            "clean": {"file": "clean.jpg", "cross_verified": clean_v},
            "edits": edits,
        }
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        out.append(manifest)
        caught = sum(1 for e in edits.values() if e["cross_verified"]["model"]["verdict"] != "CLEAN")
        print(f"  documents/{doc_type:14s} full-page edits={len(edits)} model-caught={caught} "
              f"clean-model={clean_v['model']['verdict']}")
    return out


def build_packets(labels) -> list[dict]:
    from services.risk.app.aggregator import score_packet_dir
    from services.risk.app.graph import ApplicationGraph

    graph = ApplicationGraph.build_from_packets(PACKETS_DIR, labels)
    pk_root = DEMO / "packets"
    out = []
    for pid in DEMO_PACKETS:
        src = PACKETS_DIR / pid
        if not src.exists():
            print(f"  ! packet {pid} missing")
            continue
        dst = pk_root / pid
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file():
                shutil.copy(f, dst / f.name)
        decision = score_packet_dir(src, pid, graph=graph).model_dump(mode="json")
        chain = sorted(decision["evidence_chain"], key=lambda e: _SEV.get(e["severity"], 9), reverse=True)
        verification = {
            "packet_id": pid,
            "ground_truth": labels.get(pid, {}),
            "trust_score": round(decision["trust_score"]["overall"], 1),
            "action": decision["recommendation"]["action"],
            "evidence_chain": [{"severity": e["severity"], "category": e["category"], "title": e["title"]}
                               for e in chain],
        }
        (dst / "verification.json").write_text(json.dumps(verification, indent=2))
        out.append(verification)
        print(f"  packets/{pid}  trust={verification['trust_score']:5.1f}  action={verification['action']:13s} "
              f"gt={labels.get(pid, {}).get('label')}")
    return out


def bake_home_reveal():
    """Run the learned model on the Home Form-16 pair → its detection box for the loupe."""
    res = analyze_image(str(HOME_EDITED), learned="auto")
    box, method = _primary_box_method(res)
    if box is None:   # fall back to heuristics if the model finds nothing on this particular asset
        res = analyze_image(str(HOME_EDITED), learned="env")
        box, method = _primary_box_method(res)
    data = {
        "clean_img": "examples/realistic_form16_clean.jpg",
        "edited_img": "examples/realistic_form16_edited.jpg",
        "w": res.get("width"), "h": res.get("height"),
        "box": box, "method": method if box else "none",
    }
    HOME_JS.write_text(
        "// AUTO-GENERATED by scripts/build_demo_folder.py — do not edit by hand.\n"
        "// The learned model's detection box on the Home 'spot the edit' Form-16 pair (for the loupe).\n\n"
        "export const HOME_REVEAL = " + json.dumps(data, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"  homeReveal.js  box={box} method={data['method']} ({data['w']}x{data['h']})")
    return data


def main() -> int:
    if not LABELS_PATH.exists():
        print("ERROR: synthetic corpus missing. Run:  python -m data.generator.generate")
        return 1
    if DEMO.exists():
        shutil.rmtree(DEMO)
    DEMO.mkdir(parents=True)
    labels = json.loads(LABELS_PATH.read_text())

    print("[1/4] Building demo/documents (full-page pairs, cross-verified) ...")
    docs = build_documents()
    print("\n[2/4] Building demo/packets (full-pipeline + graph reconciliation) ...")
    packets = build_packets(labels)
    print("\n[3/4] Baking Home reveal box ...")
    home = bake_home_reveal()

    print("\n[4/4] Writing demo/MANIFEST.json + README.md ...")
    doc_rows = []
    for m in docs:
        for k, e in m["edits"].items():
            mv = e["cross_verified"]["model"]
            doc_rows.append({"doc_type": m["doc_type"], "variant": k, "difficulty": e["difficulty"],
                             "model_verdict": mv["verdict"], "model_trust": mv["trust"],
                             "heuristics_verdict": e["cross_verified"]["heuristics"]["verdict"],
                             "method": e["cross_verified"]["method"]})
    manifest = {
        "about": "Cross-verified TrustShield demo corpus (synthetic, zero PII).",
        "counts": {"doc_types": len(docs), "document_edits": len(doc_rows), "packets": len(packets)},
        "documents": doc_rows,
        "packets": [{"packet_id": p["packet_id"], "action": p["action"], "trust": p["trust_score"],
                     "ground_truth": p["ground_truth"].get("label")} for p in packets],
        "home_reveal": home,
    }
    (DEMO / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    _write_readme(docs, packets)

    caught = sum(1 for r in doc_rows if r["model_verdict"] != "CLEAN")
    heur_caught = sum(1 for r in doc_rows if r["heuristics_verdict"] != "CLEAN")
    print(f"\nDONE -> {DEMO.relative_to(REPO)}")
    print(f"  documents: {len(doc_rows)} edits across {len(docs)} doc types "
          f"(heuristics caught {heur_caught}, +U-Net deep scan caught {caught})")
    print(f"  packets:   {len(packets)} ("
          f"{sum(1 for p in packets if p['action'] == 'approve')} approve / "
          f"{sum(1 for p in packets if p['action'] == 'freeze')} freeze)")
    return 0


def _write_readme(docs, packets):
    lines = [
        "# TrustShield — demo corpus",
        "",
        "A small, **browsable, cross-verified** slice of the synthetic corpus for demos and judging.",
        "Everything here is synthetic (zero PII) and is rebuilt by:",
        "",
        "```bash",
        ".venv/Scripts/python.exe scripts/build_demo_folder.py",
        "```",
        "",
        "## `documents/<doc_type>/`",
        "Each folder holds a genuine `clean.jpg` and edited variants at different difficulty levels —",
        "`naive` (obvious flat fill) → `blended` (feathered) → `pro` (seamless: matched font, tone, scan",
        "noise) — plus geometric edits (`splice`, `recompress`). `manifest.json` records, per edit, the",
        "old→new value, the ground-truth box, and the **cross-verified detector result**: the zero-FP",
        "pixel **heuristics** vs the opt-in learned **U-Net** (the deep scan). Seamless `pro` edits",
        "typically evade the heuristics and are only caught by the model.",
        "",
        "## `packets/<PKT-id>/`",
        "A curated set of full loan packets (1 clean + one per fraud shape + the 3-application",
        "double-financing ring). The packet's documents are copied alongside a `verification.json`",
        "holding the **full-pipeline** result — trust score, recommended action, and the evidence chain",
        "(including cross-document income reconciliation and cross-application graph findings).",
        "",
        "## `MANIFEST.json`",
        "An index of everything plus a caught/missed summary.",
        "",
        "> Honest note: on held-out **synthetic** docs the v2 learned U-Net scores **~100% recall** at a",
        "> **~2-3% clean false-positive** rate, but it is not yet validated on real phone-photos — so it is",
        "> opt-in (the deep scan), never the default. The heuristics hold a 0 clean false-positive rate.",
    ]
    (DEMO / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
