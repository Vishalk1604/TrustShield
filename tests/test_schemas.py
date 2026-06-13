"""Contract tests for the shared Pydantic schemas."""

import pytest

from shared.schemas.models import (
    Action,
    ApplicationPacket,
    Document,
    DocType,
    EvidenceCategory,
    EvidenceItem,
    ExtractedEntities,
    PacketDecision,
    Recommendation,
    Severity,
    TrustScore,
)


def _evidence(severity=Severity.HIGH):
    return EvidenceItem(
        category=EvidenceCategory.FORENSIC,
        severity=severity,
        title="Edited income figure",
        description="Form 16 income figure appears white-boxed and redrawn.",
        source_doc_id="form16",
        source_location="page 1, gross income row",
        values={"original": 970000, "displayed": 1840000},
        confidence=0.9,
    )


def test_every_model_instantiates_and_roundtrips():
    doc = Document(filename="form16.pdf", doc_type=DocType.FORM16, page_count=1, sha256="abc")
    ent = ExtractedEntities(pan="ABMPS1234F", declared_income=1820000.0, salary_credits=[151000.0])
    ev = _evidence()
    ts = TrustScore(overall=42.0, forensic_subscore=30.0, semantic_subscore=55.0, anomaly_subscore=60.0)
    rec = Recommendation(action=Action.MANUAL_REVIEW, rationale="High-severity forensic finding.",
                         thresholds_used={"approve_above": 75, "freeze_below": 40})
    packet = ApplicationPacket(applicant_name="Rahul Sharma", documents=[doc], extracted=ent)
    decision = PacketDecision(packet_id=packet.id, trust_score=ts, evidence_chain=[ev], recommendation=rec)

    for model in (doc, ent, ev, ts, rec, packet, decision):
        restored = type(model).model_validate_json(model.model_dump_json())
        assert restored == model


def test_packet_decision_requires_evidence():
    ts = TrustScore(overall=88.0)
    rec = Recommendation(action=Action.APPROVE, rationale="Clean.")
    with pytest.raises(Exception):
        PacketDecision(packet_id="x", trust_score=ts, evidence_chain=[], recommendation=rec)


def test_evidence_chain_is_sorted_by_severity():
    ts = TrustScore(overall=20.0)
    rec = Recommendation(action=Action.FREEZE, rationale="Multiple findings.")
    chain = [_evidence(Severity.LOW), _evidence(Severity.CRITICAL), _evidence(Severity.MEDIUM)]
    decision = PacketDecision(packet_id="x", trust_score=ts, evidence_chain=chain, recommendation=rec)
    severities = [e.severity for e in decision.sorted_evidence()]
    assert severities[0] == Severity.CRITICAL
    assert severities[-1] == Severity.LOW


def test_trust_score_bounds_enforced():
    with pytest.raises(Exception):
        TrustScore(overall=120.0)
    with pytest.raises(Exception):
        EvidenceItem(category=EvidenceCategory.ANOMALY, severity=Severity.INFO,
                     title="t", description="d", confidence=1.5)


def test_severity_rank_is_monotonic():
    order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
    ranks = [s.rank for s in order]
    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)
