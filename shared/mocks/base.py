"""Base class for TrustShield's mock external-verification adapters.

WHY THIS EXISTS
---------------
A real underwriting system would call external registries — GSTIN, MCA21, CERSAI, the Income
Tax AIS, DigiLocker — to verify an applicant's claims. TrustShield runs 100% locally for the
hackathon, so each adapter instead reads a synthetic JSON fixture from `shared/mocks/fixtures/`.

The interface is deliberately shaped like a production client (`verify(key) -> VerificationResult`)
so the only thing that changes when we "go live" is the body of `_fetch` in a subclass:

    REAL IMPLEMENTATION (illustrative — DO NOT add at hackathon time):
        def _fetch(self, key: str) -> dict | None:
            # resp = httpx.get(f"{self.BASE_URL}/lookup/{key}", headers=self._auth())
            # resp.raise_for_status()
            # return resp.json()
            ...
    The return *shape* stays identical, so nothing downstream changes.

HARD RULE: this module and its subclasses make ZERO network calls. `scripts/verify_local_only.py`
enforces it. The commented "real" code above is illustrative only and never executed.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


class VerificationResult(BaseModel):
    """Uniform result returned by every adapter, real or mock."""

    service: str = Field(description="Adapter name, e.g. 'gstin'.")
    query: str = Field(description="The key that was looked up (e.g. a PAN or GSTIN).")
    found: bool = Field(description="Whether a record existed for the query.")
    status: str = Field(
        default="unknown",
        description="Record-level status, e.g. 'active', 'not_found', 'struck_off'.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="The record payload (shape varies per service)."
    )
    source: str = Field(
        default="local_mock_fixture",
        description="Provenance. Always 'local_mock_fixture' here — never a live API.",
    )
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExternalVerificationAdapter(ABC):
    """Abstract adapter. Subclasses set `service_name` and `key_field`.

    Lookups are keyed by a single string (`key_field` documents what it means — usually a PAN
    or a registry id). Fixtures live at `fixtures/<service_name>.json` as `{ key: record }`.
    """

    #: Short service identifier; also the fixture filename stem.
    service_name: str = "base"
    #: Human note describing what the lookup key is (PAN, GSTIN, CIN, ...).
    key_field: str = "key"

    def __init__(self, fixtures_dir: Optional[Path] = None) -> None:
        self._fixtures_dir = Path(fixtures_dir) if fixtures_dir else _FIXTURES_DIR
        self._cache: Optional[dict[str, Any]] = None

    # -- public API ---------------------------------------------------------------------
    def verify(self, key: str) -> VerificationResult:
        """Look up `key` and return a uniform result. Never raises on a missing record."""
        record = self._fetch(key)
        if record is None:
            return VerificationResult(
                service=self.service_name, query=key, found=False, status="not_found"
            )
        return VerificationResult(
            service=self.service_name,
            query=key,
            found=True,
            status=str(record.get("status", "active")),
            data=record,
        )

    # -- overridable data source --------------------------------------------------------
    def _fetch(self, key: str) -> Optional[dict[str, Any]]:
        """Return the raw record for `key`, or None. THIS is the seam for a real API later.

        Mock behavior: read the local fixture file. A production subclass would replace this
        body with an authenticated HTTPS call returning the same dict shape (see module docstring).
        """
        return self._load_fixture().get(key)

    # -- helpers ------------------------------------------------------------------------
    def _load_fixture(self) -> dict[str, Any]:
        if self._cache is None:
            path = self._fixtures_dir / f"{self.service_name}.json"
            if not path.exists():
                self._cache = {}
            else:
                self._cache = json.loads(path.read_text(encoding="utf-8"))
        return self._cache

    def available_keys(self) -> list[str]:
        """All keys present in the fixture (handy for tests/demos)."""
        return list(self._load_fixture().keys())
