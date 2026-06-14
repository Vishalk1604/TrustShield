"""Mock external-verification adapters for TrustShield.

All adapters read local JSON fixtures and make ZERO network calls. The interface mirrors a
production client so a real implementation can slot in by overriding `_fetch` (see base.py).
"""

from shared.mocks.ais import AisAdapter
from shared.mocks.base import ExternalVerificationAdapter, VerificationResult
from shared.mocks.cersai import CersaiAdapter
from shared.mocks.digilocker import DigiLockerAdapter
from shared.mocks.gstin import GstinAdapter
from shared.mocks.mca21 import Mca21Adapter
from shared.mocks.property_registry import PropertyRegistryAdapter

#: Registry so callers can grab an adapter by name, e.g. ADAPTERS["ais"]().
ADAPTERS: dict[str, type[ExternalVerificationAdapter]] = {
    "gstin": GstinAdapter,
    "mca21": Mca21Adapter,
    "cersai": CersaiAdapter,
    "ais": AisAdapter,
    "digilocker": DigiLockerAdapter,
    "property_registry": PropertyRegistryAdapter,
}

__all__ = [
    "ExternalVerificationAdapter",
    "VerificationResult",
    "GstinAdapter",
    "Mca21Adapter",
    "CersaiAdapter",
    "AisAdapter",
    "DigiLockerAdapter",
    "PropertyRegistryAdapter",
    "ADAPTERS",
]
