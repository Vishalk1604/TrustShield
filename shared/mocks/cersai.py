"""CERSAI mock adapter — registered security-interest (charge) lookup.

Real service: the Central Registry of Securitisation Asset Reconstruction and Security Interest
of India, keyed by asset id or borrower PAN — reveals existing charges/loans against an asset.
REAL IMPLEMENTATION: override `_fetch` with an authenticated HTTPS call returning the same record
shape. Mock reads `fixtures/cersai.json`. No network here.
"""

from __future__ import annotations

from typing import Any

from shared.mocks.base import ExternalVerificationAdapter, VerificationResult


class CersaiAdapter(ExternalVerificationAdapter):
    """Surface existing security interests for a borrower. Lookup key = PAN."""

    service_name = "cersai"
    key_field = "pan"

    def existing_charges(self, pan: str) -> list[dict[str, Any]]:
        result: VerificationResult = self.verify(pan)
        return result.data.get("charges", []) if result.found else []
