"""Heuristic document-type classifier (plan.md §7, Week-1 baseline).

Infers `doc_type` from a document's text (embedded or OCR'd) using weighted keyword
evidence — so a user can drop an unsorted folder instead of tagging each file. Pure
Python, no model/deps. The LayoutLMv3 classifier (Week 2, Person 2 GPU) swaps in behind
this as the primary, with this as the always-available fallback.

Returns fine-grained types: financial (`form16`, `salary_slip`, `bank_statement`, `itr`),
KYC (`pan`, `aadhaar`), legal/land, or `other`. KYC types map to DocType.IDENTITY.
"""

from __future__ import annotations

# (keyword, weight) per doc type. Weights: 4 = title/near-unique, 1 = weak corroboration.
_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "pan": [
        ("permanent account number", 4), ("income tax department", 2),
        ("govt. of india", 1), ("pan", 1),
    ],
    "aadhaar": [
        ("aadhaar", 4), ("unique identification authority", 4), ("uidai", 4),
        ("आधार", 3), ("mera aadhaar", 2), ("government of india", 1), ("vid", 1),
    ],
    "form16": [
        ("form no. 16", 4), ("form 16", 4), ("certificate under section 203", 3),
        ("gross salary", 2), ("tax deducted at source", 2), ("part b", 1), ("tds", 1),
        ("traces", 2),
    ],
    "salary_slip": [
        ("salary slip", 4), ("pay slip", 4), ("payslip", 4), ("net pay", 2),
        ("basic pay", 2), ("earnings", 1), ("deductions", 1), ("hra", 1), ("ctc", 1),
    ],
    "bank_statement": [
        ("statement of account", 4), ("bank statement", 4), ("account statement", 3),
        ("closing balance", 2), ("ifsc", 2), ("salary credit", 2), ("withdrawal", 1),
        ("deposit", 1), ("upi", 1), ("transaction", 1),
    ],
    "itr": [
        ("indian income tax return", 4), ("itr-v", 4), ("itr v", 3),
        ("acknowledgement number", 2), ("assessment year", 1),
    ],
    "sale_deed": [
        ("sale deed", 4), ("sub-registrar", 2), ("vendee", 1), ("vendor", 1),
        ("consideration", 1),
    ],
    "encumbrance_certificate": [
        ("encumbrance certificate", 4), ("nil encumbrances", 2),
        ("registered transactions", 1),
    ],
    "property_valuation": [
        ("valuation report", 4), ("assessed market value", 3), ("approved valuer", 2),
    ],
    "legal_opinion": [
        ("legal opinion", 4), ("title search", 2), ("title is clear", 2), ("advocate", 1),
    ],
}

# Minimum winning score below which we don't trust the classification.
_MIN_SCORE = 2


def classify_document(text: str) -> dict:
    """Classify document text. Returns {doc_type, confidence (0-1), scores}.

    confidence reflects both the absolute evidence and the margin over the runner-up;
    a winning score below `_MIN_SCORE` returns doc_type 'other'.
    """
    low = (text or "").lower()
    scores = {
        dt: sum(w for kw, w in kws if kw in low)
        for dt, kws in _KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    best_score = scores[best]
    if best_score < _MIN_SCORE:
        return {"doc_type": "other", "confidence": 0.0, "scores": scores}

    ranked = sorted(scores.values(), reverse=True)
    runner_up = ranked[1] if len(ranked) > 1 else 0
    # Saturating absolute strength, tempered by the margin over the runner-up.
    strength = best_score / (best_score + 3.0)
    margin = (best_score - runner_up) / best_score
    confidence = round(min(1.0, strength * (0.5 + 0.5 * margin)), 3)
    return {"doc_type": best, "confidence": confidence, "scores": scores}


# KYC fine-types collapse to the schema's IDENTITY DocType.
_TO_DOCTYPE = {"pan": "identity", "aadhaar": "identity"}


def to_schema_doctype(fine_type: str) -> str:
    """Map a fine-grained classifier type to a `DocType` value string."""
    return _TO_DOCTYPE.get(fine_type, fine_type)
