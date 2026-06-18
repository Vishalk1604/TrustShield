"""Tamper-overlay rendering (§6.D3) shared by the demo endpoint and the case flow.

For each forensic finding that localizes an edit (carries `values.regions`), render the
affected page with the regions boxed (PyMuPDF, no Tesseract). Returned OUTSIDE the decision
payload so exported reports stay lean. Never raises.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path


def build_tamper_overlays(pkt_dir, decision) -> list[dict]:
    """Return [{doc, page, image_b64}] — one merged annotated image per (doc, page)."""
    from services.forensics.app.analyzer import render_tamper_overlay

    pkt_dir = Path(pkt_dir)
    overlays: list[dict] = []
    try:
        manifest = json.loads((pkt_dir / "manifest.json").read_text())
        by_filename = {d["filename"]: d for d in manifest.get("documents", [])}

        grouped: dict[tuple[str, int], list[dict]] = {}
        for ev in decision.evidence_chain:
            regions = (ev.values or {}).get("regions")
            if not regions:
                continue
            haystack = f"{ev.source_location or ''} {ev.description or ''}"
            filename = next((fn for fn in by_filename if fn in haystack), None)
            if filename is None:
                continue
            for r in regions:
                grouped.setdefault((filename, int(r.get("page", 1))), []).append(r)

        for (filename, page), page_regions in sorted(grouped.items()):
            doc_rec = by_filename[filename]
            doc_path = doc_rec.get("abspath") or str(pkt_dir / filename)
            png = render_tamper_overlay(doc_path, page_regions)
            if not png:
                continue
            overlays.append({
                "doc": filename, "page": page,
                "image_b64": base64.b64encode(png).decode("ascii"),
            })
    except Exception:
        return overlays
    return overlays
