"""MCA21 mock adapter — company / director registry lookup.

Real service: the Ministry of Corporate Affairs MCA21 portal, keyed by CIN (company) or
director PAN/DIN. REAL IMPLEMENTATION: override `_fetch` with an authenticated HTTPS call to
the MCA21 endpoint returning the same record shape. Mock reads `fixtures/mca21.json`. No network.
"""

from __future__ import annotations

from shared.mocks.base import ExternalVerificationAdapter, VerificationResult


class Mca21Adapter(ExternalVerificationAdapter):
    """Verify a company's registration / director status. Lookup key = CIN."""

    service_name = "mca21"
    key_field = "cin"

    def is_active(self, cin: str) -> bool:
        result: VerificationResult = self.verify(cin)
        return result.found and result.status.lower() == "active"
