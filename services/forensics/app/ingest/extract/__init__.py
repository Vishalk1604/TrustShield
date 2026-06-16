"""Per-doc-type field extraction over document text (plan.md §7).

Week-1 heuristic: label-anchored / regex extraction. KYC types (PAN/Aadhaar) get new
extractors here; the financial/legal types reuse the existing text extractors in
`services/forensics/app/extractor.py` (the text-PDF fast path). Week-2 (Person 2 GPU)
swaps a LayoutLMv3 key-value model in behind this, with these as the fallback.

All extractors take already-loaded text (from `ingest.loader`) and return a plain dict.
"""

from __future__ import annotations

from services.forensics.app.extractor import _EXTRACTORS as _FINANCIAL_EXTRACTORS
from services.forensics.app.ingest.extract.aadhaar import extract_aadhaar
from services.forensics.app.ingest.extract.pan import extract_pan

# KYC text extractors (financial/legal reuse extractor._EXTRACTORS).
_KYC_EXTRACTORS = {"pan": extract_pan, "aadhaar": extract_aadhaar}


def extract_fields(doc_type: str, text: str) -> dict:
    """Extract fields for `doc_type` from `text`. Returns a dict (doc_type always present)."""
    if doc_type in _KYC_EXTRACTORS:
        return _KYC_EXTRACTORS[doc_type](text)
    fn = _FINANCIAL_EXTRACTORS.get(doc_type)
    if fn is not None:
        return fn(text)
    return {"doc_type": doc_type or "other"}
