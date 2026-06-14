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

    def charges_for_property(self, property_id: str) -> list[dict[str, Any]]:
        """All registered charges against a given property/survey id, across every borrower.

        Real CERSAI is asset-keyed; this scans the fixture's per-PAN records for matching
        `property_id`. Two uses: (1) the **EC-vs-registry cross-check** — if a packet's encumbrance
        certificate claims NIL for a property that CERSAI shows as charged, that's a forged EC;
        (2) **double-financing by asset** — the same property charged to more than one lender.
        Returns `[{"pan": ..., **charge}, ...]`.
        """
        hits: list[dict[str, Any]] = []
        for pan, record in self._load_fixture().items():
            for charge in record.get("charges", []):
                if charge.get("property_id") == property_id:
                    hits.append({"pan": pan, **charge})
        return hits
