"""Tests for the synthetic data corpus: count, coverage, and ground-truth integrity."""

import json
from pathlib import Path

import pytest

from shared.schemas.models import ApplicationPacket

ROOT = Path(__file__).resolve().parents[1]
SYNTH = ROOT / "data" / "synthetic"
PACKETS = SYNTH / "packets"
LABELS = SYNTH / "labels.json"

# Every fraud category the demo relies on must appear in the corpus.
EXPECTED_FRAUD_TYPES = {
    # financial / forensic / behavioral
    "suspicious_metadata",
    "edited_income_figure",
    "font_inconsistency",
    "copy_paste",
    "incremental_update",
    "cross_document_inconsistency",
    "template_reuse",
    "timestamp_anomaly",
    "behavioral_velocity",
    # legal / land-record (collateral)
    "forged_title",
    "tampered_encumbrance",
    "valuation_inflation",
    "property_mismatch",
    "double_financing",
}


@pytest.fixture(scope="module")
def labels():
    if not LABELS.exists() or not any(PACKETS.glob("PKT-*")):
        # Regenerate on a fresh checkout if the corpus is missing.
        from data.generator.generate import main as generate_main
        generate_main()
    return json.loads(LABELS.read_text(encoding="utf-8"))


def test_at_least_20_packets(labels):
    assert len(labels) >= 20, f"expected >=20 packets, found {len(labels)}"


def test_has_clean_and_fraud(labels):
    clean = [k for k, v in labels.items() if v["label"] == "clean"]
    fraud = [k for k, v in labels.items() if v["label"] == "fraud"]
    assert clean, "no clean packets"
    assert fraud, "no fraud packets"


def test_all_fraud_types_present(labels):
    seen = {t for v in labels.values() for t in v["fraud_types"]}
    missing = EXPECTED_FRAUD_TYPES - seen
    assert not missing, f"missing fraud types: {sorted(missing)}"


def test_fraud_packets_have_reasons_and_affected_docs(labels):
    for pid, v in labels.items():
        if v["label"] == "fraud":
            assert v["reasons"], f"{pid} fraud packet missing reasons"
            assert v["affected_docs"], f"{pid} fraud packet missing affected_docs"


def test_every_packet_has_manifest_and_documents(labels):
    for pid in labels:
        pkt_dir = PACKETS / pid
        assert pkt_dir.is_dir(), f"missing packet dir {pid}"
        manifest_path = pkt_dir / "manifest.json"
        assert manifest_path.exists(), f"{pid} missing manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["documents"], f"{pid} has no documents"
        for doc in manifest["documents"]:
            assert (pkt_dir / doc["filename"]).exists(), f"{pid}: {doc['filename']} missing on disk"
            assert doc["sha256"], f"{pid}: {doc['filename']} missing sha256"


def test_manifest_loads_as_application_packet(labels):
    """The manifest (minus the generator-only ground_truth block) is a valid ApplicationPacket."""
    pid = next(iter(labels))
    manifest = json.loads((PACKETS / pid / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("ground_truth", None)
    packet = ApplicationPacket.model_validate(manifest)
    assert packet.id == pid
    assert packet.documents


def test_template_reuse_group_present(labels):
    groups = {v.get("template_group") for v in labels.values() if v.get("template_group")}
    assert groups, "no template_group set on any packet (Phase 5 clustering would have nothing)"
    # The ring should contain multiple applicants sharing one template group.
    for g in groups:
        members = [k for k, v in labels.items() if v.get("template_group") == g]
        assert len(members) >= 2, f"template group {g} has <2 members"


def test_double_financing_shares_one_property(labels):
    """The double-financing ring must be ≥2 distinct applicants pledging the SAME property —
    this is what the Phase 5 collateral graph clusters on."""
    df = {k: v for k, v in labels.items() if "double_financing" in v["fraud_types"]}
    assert len(df) >= 2, "need ≥2 double-financing packets to form a collateral cluster"
    property_ids = {v.get("property_id") for v in df.values()}
    assert len(property_ids) == 1, f"double-financing packets should share ONE property_id, got {property_ids}"
    pans = {v.get("applicant_pan") for v in df.values()}
    assert len(pans) == len(df), "double-financing packets should be distinct applicants"
    groups = {v.get("property_group") for v in df.values()}
    assert groups == {next(iter(groups))} and None not in groups, "all share one property_group"


def test_legal_land_documents_present(labels):
    """At least one packet carries the four land/legal collateral document types."""
    needed = {"sale_deed", "encumbrance_certificate", "property_valuation", "legal_opinion"}
    seen = set()
    for pid in labels:
        manifest = json.loads((PACKETS / pid / "manifest.json").read_text(encoding="utf-8"))
        seen |= {d["doc_type"] for d in manifest["documents"]}
    missing = needed - seen
    assert not missing, f"missing land/legal doc types in the corpus: {sorted(missing)}"
