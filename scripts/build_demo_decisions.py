#!/usr/bin/env python3
"""Refresh the dashboard's baked packet decisions + overlays from the (now realistic) synthetic packets.

The dashboard's offline Demo mode for the Investigator packet view reads `src/data/demoDecisions.js`
(per-packet decision + cross-application subgraph + pre-rendered tamper-overlay PNGs in public/demo/).
Those were hand-captured from an earlier backend run on the OLD flat packets. After regenerating the
packets with the §11 realistic builders, this re-scores them in-process and re-renders the overlays so
packet mode shows the realistic documents with the edit boxed. No backend/network needed.

    python scripts/build_demo_decisions.py

Run from the repo root.
"""

from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path

import fitz
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from services.risk.app.aggregator import score_packet_dir          # noqa: E402
from services.risk.app.graph import ApplicationGraph               # noqa: E402
from services.forensics.app.analyzer import render_tamper_overlay  # noqa: E402

PACKETS = REPO / "data" / "synthetic" / "packets"
LABELS = REPO / "data" / "synthetic" / "labels.json"
PUB_DEMO = REPO / "services" / "dashboard" / "public" / "demo"
OUT_JS = REPO / "services" / "dashboard" / "src" / "data" / "demoDecisions.js"

# The packets the dashboard bakes for offline Demo mode (parity with the current demoDecisions.js).
PACKET_IDS = ["PKT-0001", "PKT-0002", "PKT-0004", "PKT-0009", "PKT-0010", "PKT-0012", "PKT-0017",
              "PKT-0025", "PKT-0026", "PKT-0027", "PKT-0028", "PKT-0029", "PKT-0031", "PKT-0032", "PKT-0033"]


def _render_overlays(pkt_dir: Path, decision) -> list[dict]:
    """[{doc, page, image_b64}] for evidence that localizes an edit (mirrors risk main._build_tamper_overlays)."""
    out: list[dict] = []
    try:
        manifest = json.loads((pkt_dir / "manifest.json").read_text())
        by_filename = {d["filename"]: d for d in manifest.get("documents", [])}
        grouped: dict[tuple, list[dict]] = {}
        for ev in decision.evidence_chain:
            regions = (ev.values or {}).get("regions")
            if not regions:
                continue
            hay = f"{ev.source_location or ''} {ev.description or ''}"
            filename = next((fn for fn in by_filename if fn in hay), None)
            if filename is None:
                continue
            for r in regions:
                grouped.setdefault((filename, int(r.get("page", 1))), []).append(r)
        for (filename, page), regions in sorted(grouped.items()):
            png = render_tamper_overlay(str(pkt_dir / filename), regions)
            if png:
                out.append({"doc": filename, "page": page, "image_b64": base64.b64encode(png).decode("ascii")})
    except Exception:
        return out
    return out


_RENDER_DPI = 150
_PT2PX = _RENDER_DPI / 72.0


def _method_for(ev) -> str:
    cat = getattr(ev, "category", None)
    det = (ev.values or {}).get("detector", "") if getattr(ev, "values", None) else ""
    if cat == "semantic" or str(det).startswith("qr"):
        return "semantic"
    return "pixel"      # forensic white-box / re-OCR / pixel signals


def _packet_documents(pkt_dir: Path, decision, pid: str) -> list[dict]:
    """Render every document in the packet (clean page) + the detection box(es) for the edited ones, so
    the dashboard can show the whole packet and toggle the marking (like the Examples viewer)."""
    try:
        manifest = json.loads((pkt_dir / "manifest.json").read_text())
    except Exception:
        return []
    docs = manifest.get("documents", [])
    # filename -> {page, boxes_pt:[(page,bbox)], ev}
    matched: dict[str, dict] = {}
    for ev in decision.evidence_chain:
        regions = (ev.values or {}).get("regions")
        if not regions:
            continue
        hay = f"{ev.source_location or ''} {ev.description or ''}"
        fn = next((d["filename"] for d in docs if d["filename"] in hay), None)
        if fn is None:
            continue
        m = matched.setdefault(fn, {"page": int(regions[0].get("page", 1)), "boxes_pt": [], "ev": ev})
        for r in regions:
            if r.get("bbox"):
                m["boxes_pt"].append((int(r.get("page", 1)), r["bbox"]))

    out: list[dict] = []
    for i, d in enumerate(docs):
        fn = d["filename"]
        info = matched.get(fn)
        page_no = info["page"] if info else 1
        try:
            with fitz.open(pkt_dir / fn) as doc:
                idx = max(0, min(page_no - 1, doc.page_count - 1))
                pix = doc[idx].get_pixmap(dpi=_RENDER_DPI)
                png, W, H = pix.tobytes("png"), pix.width, pix.height
        except Exception:
            continue
        img_name = f"{pid}_doc{i}.jpg"
        Image.open(io.BytesIO(png)).convert("RGB").save(PUB_DEMO / img_name, "JPEG", quality=85)
        boxes = [[int(b[0] * _PT2PX), int(b[1] * _PT2PX), int(b[2] * _PT2PX), int(b[3] * _PT2PX)]
                 for (pg, b) in (info["boxes_pt"] if info else []) if pg == page_no]
        edited = bool(boxes)
        out.append({
            "doc_type": d.get("doc_type", "document"), "filename": fn,
            "img": f"demo/{img_name}", "w": W, "h": H, "page": page_no,
            "edited": edited, "boxes": boxes, "verdict": "EDITED" if edited else "CLEAN",
            "method": _method_for(info["ev"]) if info else None,
            "finding": ({"title": info["ev"].title, "description": info["ev"].description} if info else None),
        })
    return out


def main() -> int:
    PUB_DEMO.mkdir(parents=True, exist_ok=True)
    for f in list(PUB_DEMO.glob("PKT-*.png")) + list(PUB_DEMO.glob("PKT-*_doc*.jpg")):
        f.unlink()
    labels = json.loads(LABELS.read_text())
    graph = ApplicationGraph.build_from_packets(PACKETS, labels)

    out: dict = {}
    for pid in PACKET_IDS:
        pkt = PACKETS / pid
        if not (pkt / "manifest.json").exists():
            print(f"  ! missing {pid}")
            continue
        subgraph = graph.subgraph_for(pid)
        decision = score_packet_dir(pkt, pid, graph=graph)
        overlays = []
        for i, o in enumerate(_render_overlays(pkt, decision)):
            (PUB_DEMO / f"{pid}_{i}.png").write_bytes(base64.b64decode(o["image_b64"]))
            overlays.append({"doc": o["doc"], "page": o["page"], "src": f"demo/{pid}_{i}.png"})
        documents = _packet_documents(pkt, decision, pid)
        dec = decision.model_dump(mode="json")
        out[pid] = {"decision": dec, "subgraph": subgraph, "overlays": overlays, "documents": documents}
        n_edit = sum(1 for d in documents if d["edited"])
        print(f"  {pid}: {dec['recommendation']['action']:14s} trust={dec['trust_score']['overall']:.1f} "
              f"overlays={len(overlays)} docs={len(documents)} (edited={n_edit})")

    header = ("// AUTO-GENERATED by scripts/build_demo_decisions.py — do not edit by hand.\n"
              "// Baked packet decisions + cross-application subgraphs + tamper-overlay paths for the\n"
              "// Investigator's offline Demo mode, scored on the realistic synthetic packets.\n\n"
              "export const DEMO_DECISIONS = ")
    OUT_JS.write_text(header + json.dumps(out, indent=2) + ";\n", encoding="utf-8")
    print(f"\nwrote {len(out)} packets -> {OUT_JS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
