"""PII redaction for logs — Phase 7.

The product rule: **never log raw PII** — PAN, account numbers, names,
and property/title IDs. Evidence items shown to the investigator legitimately contain
these values (that is the product), but anything written to a *log* must be scrubbed.

This module provides:
  - pattern maskers for the structured identifiers we can recognise without context
    (PAN, long account numbers, survey/property IDs);
  - field-aware redaction for dicts (keys like ``name`` / ``pan`` / ``property_id``);
  - a :class:`PIIRedactionFilter` and :func:`install_log_redaction` to scrub every
    record passing through a logger as a safety net.

Masks are format-preserving and partial where useful (keep a few characters for audit
correlation) so a redacted log is still debuggable without exposing the raw value.

Pure functions; no I/O, no network.
"""

from __future__ import annotations

import logging
import re
from typing import Any

# ── recognisable identifier patterns ────────────────────────────────────────────

# Indian PAN: 5 letters, 4 digits, 1 letter (e.g. ABMPS1234F).
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
# Bank account / long numeric identifiers: 9–18 digits (loan amounts are <= 8 digits).
_ACCOUNT_RE = re.compile(r"\b\d{9,18}\b")
# Survey / property IDs like SY-911/2C, SY-217/3B, SY-330/7.
_PROPERTY_RE = re.compile(r"\b([A-Z]{2})-\d{1,4}/\d{1,3}[A-Z]?\b")

#: Dict keys whose values are PII and must be masked whole.
PII_KEYS: frozenset[str] = frozenset({
    "name", "applicant_name", "owner_name", "borrower_name",
    "pan", "applicant_pan", "account_number", "account_numbers",
    "property_id", "address", "property_address",
})


def mask_pan(value: str) -> str:
    """ABMPS1234F -> AB*******F (keep first 2 + last 1 for correlation)."""
    return _PAN_RE.sub(lambda m: m.group(0)[:2] + "*" * 7 + m.group(0)[-1], value)


def mask_accounts(value: str) -> str:
    """Mask long numeric identifiers, keeping the last 4 digits."""
    def _m(m: re.Match) -> str:
        s = m.group(0)
        return "*" * (len(s) - 4) + s[-4:]
    return _ACCOUNT_RE.sub(_m, value)


def mask_property_ids(value: str) -> str:
    """SY-911/2C -> SY-*** (keep the 2-letter prefix, mask the identifying part)."""
    return _PROPERTY_RE.sub(lambda m: f"{m.group(1)}-***", value)


def redact_text(value: str) -> str:
    """Apply all pattern maskers to free text (PAN, accounts, property IDs)."""
    if not value:
        return value
    return mask_property_ids(mask_accounts(mask_pan(value)))


def _mask_whole(value: Any) -> Any:
    """Mask a value known to be PII (by its dict key), preserving rough shape."""
    if isinstance(value, str):
        if not value:
            return value
        if _PAN_RE.fullmatch(value):
            return mask_pan(value)
        # Generic name/address/id: keep first char, mask the rest.
        return value[0] + "*" * (len(value) - 1) if len(value) > 1 else "*"
    if isinstance(value, (list, tuple)):
        return type(value)(_mask_whole(v) for v in value)
    return "***"


def redact_mapping(data: Any) -> Any:
    """Recursively redact a dict/list: PII keys masked whole, other strings pattern-scrubbed."""
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            if isinstance(k, str) and k.lower() in PII_KEYS:
                out[k] = _mask_whole(v)
            else:
                out[k] = redact_mapping(v)
        return out
    if isinstance(data, list):
        return [redact_mapping(v) for v in data]
    if isinstance(data, str):
        return redact_text(data)
    return data


class PIIRedactionFilter(logging.Filter):
    """Logging filter that scrubs recognisable PII from every formatted record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (stdlib name)
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = redact_text(msg)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def install_log_redaction(logger: logging.Logger | None = None) -> None:
    """Attach the PII redaction filter to a logger (and common uvicorn loggers).

    Called at service startup. Idempotent — won't add the filter twice.
    """
    targets = [logger or logging.getLogger()]
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        targets.append(logging.getLogger(name))
    for lg in targets:
        if not any(isinstance(f, PIIRedactionFilter) for f in lg.filters):
            lg.addFilter(PIIRedactionFilter())
        for handler in lg.handlers:
            if not any(isinstance(f, PIIRedactionFilter) for f in handler.filters):
                handler.addFilter(PIIRedactionFilter())


__all__ = [
    "mask_pan",
    "mask_accounts",
    "mask_property_ids",
    "redact_text",
    "redact_mapping",
    "PII_KEYS",
    "PIIRedactionFilter",
    "install_log_redaction",
]
