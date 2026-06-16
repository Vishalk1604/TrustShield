"""Single-document ingestion orchestrator (plan.md §7).

`ingest_document(path)` = load (any format) → classify doc-type → extract fields → run
KYC validators. This is the pure-Python core the `POST /forensics/ingest` endpoint and
the dashboard upload will wrap. No network; degrades gracefully (OCR/password issues
surface as flags rather than exceptions).
"""

from __future__ import annotations

from typing import Optional

from services.forensics.app.ingest import extract as _extract
from services.forensics.app.ingest.classify import classify_document, to_schema_doctype
from services.forensics.app.ingest.loader import load_text
from services.forensics.app.ingest.normalize import (
    validate_aadhaar,
    validate_ifsc,
    validate_pan,
)


def _run_kyc(fields: dict) -> dict:
    """Validate any identifiers present in the extracted fields."""
    kyc: dict = {}
    if fields.get("pan"):
        kyc["pan"] = validate_pan(fields["pan"])
    if fields.get("aadhaar"):
        kyc["aadhaar"] = validate_aadhaar(fields["aadhaar"])
    if fields.get("ifsc"):
        kyc["ifsc"] = validate_ifsc(fields["ifsc"])
    return kyc


def ingest_document(
    path: str, doc_type: Optional[str] = None, password: Optional[str] = None
) -> dict:
    """Ingest one document end-to-end (load → classify → extract → KYC).

    If `doc_type` is None it is inferred. Returns a dict with `ok=False` + an `error`/
    `needs_password` flag when the file can't be read, instead of raising.
    """
    loaded = load_text(path, password=password)
    if not loaded.ok:
        return {
            "ok": False, "needs_password": loaded.needs_password,
            "error": loaded.error, "kind": loaded.kind, "source": loaded.source,
        }

    classified = None
    if doc_type is None:
        classified = classify_document(loaded.text)
        doc_type = classified["doc_type"]

    fields = _extract.extract_fields(doc_type, loaded.text)
    kyc = _run_kyc(fields)

    return {
        "ok": True,
        "doc_type": doc_type,
        "doc_type_confidence": (classified or {}).get("confidence"),
        "schema_doc_type": to_schema_doctype(doc_type),
        "source": loaded.source,          # embedded | ocr | mixed | image-ocr
        "ocr_used": loaded.ocr_used,
        "page_count": loaded.page_count,
        "fields": fields,
        "kyc": kyc,
        "text_len": len(loaded.text),
    }
