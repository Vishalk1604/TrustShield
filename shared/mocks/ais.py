"""AIS mock adapter — Income Tax Annual Information Statement lookup.

Real service: the Income Tax Department's AIS/TIS, keyed by PAN — the authoritative record of
reported income, TDS, and high-value transactions. This is the strongest cross-check against a
packet's declared income. REAL IMPLEMENTATION: override `_fetch` with an authenticated HTTPS call
returning the same record shape. Mock reads `fixtures/ais.json`. No network here.
"""

from __future__ import annotations

from shared.mocks.base import ExternalVerificationAdapter, VerificationResult


class AisAdapter(ExternalVerificationAdapter):
    """Pull the tax-department income-of-record for a PAN. Lookup key = PAN."""

    service_name = "ais"
    key_field = "pan"

    def reported_income(self, pan: str) -> float | None:
        """Income on record with the tax department for the latest year, in INR."""
        result: VerificationResult = self.verify(pan)
        return result.data.get("reported_income") if result.found else None
