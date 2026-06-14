"""Property registry mock adapter — state registered market value lookup.

Real service: the state sub-registrar's property registry (accessed via the DORIS portal or
equivalent state-level API) — provides the last registered market/guideline value for a survey
number. REAL IMPLEMENTATION: override `_fetch` with an authenticated API call returning the same
record shape. Mock reads `fixtures/property_registry.json`. No network here.
"""

from __future__ import annotations

from typing import Any, Optional

from shared.mocks.base import ExternalVerificationAdapter, VerificationResult


class PropertyRegistryAdapter(ExternalVerificationAdapter):
    """Surface registered market value for a property survey number. Lookup key = property_id."""

    service_name = "property_registry"
    key_field = "property_id"

    def registered_market_value(self, property_id: str) -> Optional[float]:
        """Return the registry's registered market value (INR) for the property, or None."""
        result: VerificationResult = self.verify(property_id)
        if result.found:
            v = result.data.get("registered_market_value")
            return float(v) if v is not None else None
        return None
