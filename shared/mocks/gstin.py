"""GSTIN mock adapter — GST registration lookup.

Real service: the GST Network (GSTN) public taxpayer API, keyed by GSTIN.
REAL IMPLEMENTATION: override `_fetch` with an authenticated HTTPS call to the GSTN endpoint
returning the same record shape. Mock reads `fixtures/gstin.json`. No network here.
"""

from __future__ import annotations

from shared.mocks.base import ExternalVerificationAdapter, VerificationResult


class GstinAdapter(ExternalVerificationAdapter):
    """Verify a business's GST registration. Lookup key = GSTIN."""

    service_name = "gstin"
    key_field = "gstin"

    def legal_name(self, gstin: str) -> str | None:
        result: VerificationResult = self.verify(gstin)
        return result.data.get("legal_name") if result.found else None
