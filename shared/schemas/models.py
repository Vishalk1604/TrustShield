"""TrustShield shared schema contract (Pydantic v2).

These models are the single contract every service depends on. The forensics and risk
services import them; the dashboard mirrors them in TypeScript. Keep changes backward-compatible
and update `shared/schemas/CLAUDE.md` when the contract changes.

Local-only note: nothing here makes a network call. Models are pure data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    """Timezone-aware UTC now (avoids naive-datetime ambiguity in evidence timestamps)."""
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


# --------------------------------------------------------------------------------------
# Enums — the controlled vocabularies shared across services
# --------------------------------------------------------------------------------------
class DocType(str, Enum):
    """Type of a document inside a loan application packet."""

    IDENTITY = "identity"            # PAN card, Aadhaar, etc.
    ITR = "itr"                      # Income Tax Return
    FORM16 = "form16"                # Employer TDS certificate
    BANK_STATEMENT = "bank_statement"
    SALARY_SLIP = "salary_slip"
    PROPERTY_LEGAL = "property_legal"
    OTHER = "other"


class EvidenceCategory(str, Enum):
    """Which analysis produced an evidence item."""

    FORENSIC = "forensic"    # Service A: tamper/metadata/template signals
    SEMANTIC = "semantic"    # Service B: cross-document rule violations
    ANOMALY = "anomaly"      # Service B: behavioral/statistical anomaly
    GRAPH = "graph"          # Service B: cross-application graph linkage


class Severity(str, Enum):
    """Severity of a single evidence item. Drives ordering and UI color-coding."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        """Numeric rank (higher = more severe) for sorting evidence chains."""
        return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]


class Action(str, Enum):
    """Recommended underwriting action."""

    APPROVE = "approve"
    MANUAL_REVIEW = "manual_review"
    FREEZE = "freeze"


# --------------------------------------------------------------------------------------
# Core contract models
# --------------------------------------------------------------------------------------
class Document(BaseModel):
    """A single file within an application packet."""

    id: str = Field(default_factory=lambda: _new_id("doc"))
    filename: str
    doc_type: DocType = DocType.OTHER
    path: Optional[str] = Field(
        default=None, description="Local filesystem path. Never a remote URL."
    )
    mime_type: str = "application/pdf"
    page_count: Optional[int] = None
    sha256: Optional[str] = Field(
        default=None, description="Content hash for integrity / dedup."
    )


class ExtractedEntities(BaseModel):
    """Entities pulled out of a packet by OCR + extraction (populated in Phase 2).

    All fields Optional: in Phase 0 packets carry ground-truth values via the generator,
    but the extraction pipeline that fills this in does not exist yet.
    """

    name: Optional[str] = None
    pan: Optional[str] = None
    employer_name: Optional[str] = None
    declared_income: Optional[float] = Field(
        default=None, description="Annual income as declared on ITR/Form 16 (INR)."
    )
    salary_credits: list[float] = Field(
        default_factory=list, description="Individual salary credit amounts from bank statement (INR)."
    )
    salary_credit_total: Optional[float] = Field(
        default=None, description="Sum/annualized implied income from bank credits (INR)."
    )
    tax_paid: Optional[float] = Field(default=None, description="Tax paid per ITR/Form 16 (INR).")
    account_numbers: list[str] = Field(default_factory=list)
    dates: dict[str, str] = Field(
        default_factory=dict, description="Named dates, e.g. {'itr_filing': '2024-07-15'}."
    )
    raw: dict[str, Any] = Field(
        default_factory=dict, description="Anything extracted but not yet modeled."
    )


class EvidenceItem(BaseModel):
    """One human-readable finding. The atom of explainability.

    Rule: a score is never emitted without a list of these. Each item must read as a
    plain-English sentence a non-technical underwriter can understand, and must attribute
    its source so the claim is auditable.
    """

    id: str = Field(default_factory=lambda: _new_id("ev"))
    category: EvidenceCategory
    severity: Severity
    title: str = Field(description="Short headline, e.g. 'Income figure edited'.")
    description: str = Field(
        description="Plain-English explanation a non-technical reviewer can read."
    )
    source_doc_id: Optional[str] = Field(
        default=None, description="Document.id this finding came from, if any."
    )
    source_location: Optional[str] = Field(
        default=None, description="Where in the source, e.g. 'page 1, income row' or 'PDF metadata'."
    )
    values: dict[str, Any] = Field(
        default_factory=dict,
        description="The concrete values behind the finding, e.g. "
        "{'form16_income': 1840000, 'bank_implied_income': 970000}.",
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="0–1 confidence in this finding."
    )
    created_at: datetime = Field(default_factory=_utcnow)


class TrustScore(BaseModel):
    """Aggregate trust score with its sub-scores. 0 = certainly fraudulent, 100 = clean."""

    overall: float = Field(ge=0.0, le=100.0)
    forensic_subscore: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    semantic_subscore: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    anomaly_subscore: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    version: str = Field(default="0.0.0", description="Scoring-model version for auditability.")
    computed_at: datetime = Field(default_factory=_utcnow)


class Recommendation(BaseModel):
    """Recommended action plus the rationale and the thresholds that produced it."""

    action: Action
    rationale: str = Field(description="Why this action, in plain English.")
    thresholds_used: dict[str, Any] = Field(
        default_factory=dict,
        description="The cutoffs applied, e.g. {'approve_above': 75, 'freeze_below': 40}.",
    )


class ApplicationPacket(BaseModel):
    """A full loan application: the applicant plus their submitted documents."""

    id: str = Field(default_factory=lambda: _new_id("pkt"))
    applicant_name: Optional[str] = Field(
        default=None, description="Applicant display name. PII — redact in logs (Phase 7)."
    )
    documents: list[Document] = Field(default_factory=list)
    extracted: Optional[ExtractedEntities] = None
    created_at: Optional[datetime] = Field(
        default=None, description="When the packet's documents were created (for velocity features)."
    )
    submitted_at: Optional[datetime] = Field(
        default=None, description="When the packet was submitted (for create→submit velocity)."
    )
    source: Optional[str] = Field(
        default=None, description="Origin channel, e.g. 'branch_upload', 'synthetic_generator'."
    )

    @field_validator("documents")
    @classmethod
    def _at_least_typed(cls, docs: list[Document]) -> list[Document]:
        # A packet can be empty during construction, but warn-by-contract: no validation error,
        # just a hook point. Kept permissive so the generator can build incrementally.
        return docs


class PacketDecision(BaseModel):
    """The full result for a packet: score + ordered evidence chain + recommendation.

    This is the envelope Service B returns and the dashboard renders. Defined now so the
    contract is whole even though scoring lands in Phase 4.
    """

    packet_id: str
    trust_score: TrustScore
    evidence_chain: list[EvidenceItem] = Field(default_factory=list)
    recommendation: Recommendation

    @field_validator("evidence_chain")
    @classmethod
    def _no_score_without_evidence(cls, chain: list[EvidenceItem]) -> list[EvidenceItem]:
        # Enforce the product rule at the type boundary: a decision must carry evidence.
        if not chain:
            raise ValueError(
                "A PacketDecision must include a non-empty evidence_chain — "
                "never emit a score without explainable evidence."
            )
        return chain

    def sorted_evidence(self) -> list[EvidenceItem]:
        """Evidence ordered by severity (most severe first), then confidence."""
        return sorted(
            self.evidence_chain,
            key=lambda e: (e.severity.rank, e.confidence),
            reverse=True,
        )


__all__ = [
    "DocType",
    "EvidenceCategory",
    "Severity",
    "Action",
    "Document",
    "ExtractedEntities",
    "EvidenceItem",
    "TrustScore",
    "Recommendation",
    "ApplicationPacket",
    "PacketDecision",
]
