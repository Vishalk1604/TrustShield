"""DigiLocker mock adapter — issued/verified document lookup.

Real service: DigiLocker, keyed by an Aadhaar-linked identity (here we key by PAN for the demo) —
returns government-issued documents whose authenticity is vouched by the issuer. REAL
IMPLEMENTATION: override `_fetch` with an authenticated HTTPS/OAuth call returning the same record
shape. Mock reads `fixtures/digilocker.json`. No network here.
"""

from __future__ import annotations

from typing import Any

from shared.mocks.base import ExternalVerificationAdapter, VerificationResult


class DigiLockerAdapter(ExternalVerificationAdapter):
    """List issuer-verified documents for an identity. Lookup key = PAN."""

    service_name = "digilocker"
    key_field = "pan"

    def issued_documents(self, pan: str) -> list[dict[str, Any]]:
        result: VerificationResult = self.verify(pan)
        return result.data.get("documents", []) if result.found else []
