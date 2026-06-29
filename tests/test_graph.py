"""Phase 5 tests — cross-application graph: rings, collateral clusters, scoring.

Covers the plan's checks:
  - template/employer-reuse packets form the correct ring (QuickCash)
  - a property reused across packets forms a collateral cluster (SY-911/2C)
  - unrelated packets stay unlinked (no false ring from the shared default template)
  - subgraphs are small + fast
  - graph evidence escalates relational fraud (double-financing / ring) to FREEZE
  - the graph endpoints
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.risk.app.graph import ApplicationGraph
from shared.schemas import EvidenceCategory, Severity

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKETS_DIR = REPO_ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = REPO_ROOT / "data" / "synthetic" / "labels.json"
MODELS_DIR = REPO_ROOT / "services" / "risk" / "models"
MODELS_EXIST = (MODELS_DIR / "gradient_boosting.joblib").exists()


def _labels() -> dict:
    return json.loads(LABELS_PATH.read_text())


@pytest.fixture(scope="module")
def graph() -> ApplicationGraph:
    return ApplicationGraph.build_from_packets(PACKETS_DIR, _labels())


# ── cluster detection ────────────────────────────────────────────────────────────


class TestClusters:
    def test_double_financing_collateral_cluster(self, graph):
        """SY-911/2C must surface as a collateral cluster across 4 applications."""
        clusters = graph.collateral_clusters()
        sy911 = [c for c in clusters if c["property_id"] == "SY-911/2C"]
        assert len(sy911) == 1, "SY-911/2C collateral cluster not found"
        apps = set(sy911[0]["applications"])
        assert {"PKT-0029", "PKT-0031", "PKT-0032", "PKT-0033"} <= apps
        assert sy911[0]["distinct_applicants"] >= 3

    def test_quickcash_employer_ring(self, graph):
        """QuickCash must surface as an application-fraud ring of 4 distinct applicants."""
        rings = graph.employer_rings()
        qc = [r for r in rings if r["employer"] == "QuickCash Finance Pvt Ltd"]
        assert len(qc) == 1, "QuickCash ring not found"
        assert qc[0]["distinct_applicants"] == 4
        assert set(qc[0]["applications"]) == {"PKT-0018", "PKT-0019", "PKT-0020", "PKT-0021"}
        assert qc[0]["shared_template"] is True

    def test_legit_employers_are_not_rings(self, graph):
        """Employers with a single distinct applicant (same person re-applying) are not rings."""
        rings = graph.employer_rings()
        ring_employers = {r["employer"] for r in rings}
        for legit in ("Infosys Limited", "Wipro Limited", "Accenture", "HDFC Bank"):
            assert legit not in ring_employers, f"{legit} wrongly flagged as a ring"

    def test_default_template_is_hub_suppressed(self, graph):
        """The generator's default template (shared by 25 packets) must not form a ring.

        If it weren't hub-suppressed, every clean packet would link into one giant cluster.
        """
        # No collateral/employer cluster should contain a clean financial-only packet
        # like PKT-0001 (it shares only the default template + its own PAN).
        clusters = graph.collateral_clusters() + graph.employer_rings()
        for c in clusters:
            assert "PKT-0001" not in c["applications"], "clean packet linked via default template hub"

    def test_clusters_payload_shape(self, graph):
        c = graph.clusters()
        assert "collateral_clusters" in c
        assert "employer_rings" in c
        assert c["n_applications"] == 36


# ── graph evidence ────────────────────────────────────────────────────────────────


class TestGraphEvidence:
    def test_double_financing_gets_critical_collateral_evidence(self, graph):
        items = graph.graph_evidence_for("PKT-0031")
        collateral = [i for i in items if i.title.startswith("Collateral pledged")]
        assert len(collateral) == 1
        assert collateral[0].severity == Severity.CRITICAL
        assert collateral[0].category == EvidenceCategory.GRAPH
        assert "SY-911/2C" in collateral[0].description

    def test_ring_member_gets_critical_ring_evidence(self, graph):
        items = graph.graph_evidence_for("PKT-0018")
        ring = [i for i in items if i.title == "Application-fraud ring"]
        assert len(ring) == 1
        assert ring[0].severity == Severity.CRITICAL
        assert "QuickCash" in ring[0].description

    def test_clean_financial_packet_only_info_evidence(self, graph):
        """PKT-0001 (clean) should only have an INFO repeat-applicant note, nothing escalating."""
        items = graph.graph_evidence_for("PKT-0001")
        assert all(i.severity == Severity.INFO for i in items), (
            "clean financial packet should not get escalating graph evidence"
        )

    def test_two_app_cluster_is_medium(self, graph):
        """SY-217/3B (2 apps) gets MEDIUM collateral evidence, not CRITICAL."""
        items = graph.graph_evidence_for("PKT-0025")
        collateral = [i for i in items if i.title.startswith("Collateral pledged")]
        assert len(collateral) == 1
        assert collateral[0].severity == Severity.MEDIUM


# ── subgraph ──────────────────────────────────────────────────────────────────────


class TestSubgraph:
    def test_subgraph_small(self, graph):
        sg = graph.subgraph_for("PKT-0031")
        assert 0 < len(sg["nodes"]) <= 30
        assert len(sg["edges"]) >= 1
        # must include the app itself
        assert any(n["id"] == "app:PKT-0031" for n in sg["nodes"])

    def test_subgraph_unknown_packet_empty(self, graph):
        sg = graph.subgraph_for("PKT-9999")
        assert sg == {"nodes": [], "edges": []}

    def test_subgraph_excludes_default_template_hub(self, graph):
        """A clean packet's subgraph must stay tiny (no 25-app default-template explosion)."""
        sg = graph.subgraph_for("PKT-0001")
        assert len(sg["nodes"]) <= 8, "subgraph exploded via the default-template hub"


# ── persistence ───────────────────────────────────────────────────────────────────


class TestPersistence:
    def test_save_and_load_roundtrip(self, graph, tmp_path):
        store = tmp_path / "g.pkl"
        graph.save(store)
        assert store.exists()
        reloaded = ApplicationGraph.load(store)
        assert len(reloaded._app_nodes()) == 36
        # clusters survive the roundtrip
        assert len(reloaded.collateral_clusters()) == len(graph.collateral_clusters())

    def test_load_missing_returns_empty(self, tmp_path):
        g = ApplicationGraph.load(tmp_path / "nope.pkl")
        assert len(g._app_nodes()) == 0

    def test_upsert_is_idempotent(self):
        g = ApplicationGraph()
        for _ in range(3):
            g.upsert_application("PKT-A", applicant_pan="P1", employer="E1",
                                 property_ids=["PR1"])
        # re-upsert must not create duplicate edges
        assert g.G.degree("app:PKT-A") == 3  # pan + employer + property


# ── graph-informed scoring ────────────────────────────────────────────────────────


@pytest.mark.skipif(not MODELS_EXIST, reason="models not trained yet")
class TestGraphInformedScoring:
    def test_double_financing_escalates_to_freeze(self, graph):
        """Graph evidence turns Phase 4 'manual_review' into FREEZE for double-financing."""
        from services.risk.app.aggregator import score_packet_dir
        from shared.schemas import Action

        for pid in ("PKT-0031", "PKT-0032", "PKT-0033"):
            no_graph = score_packet_dir(PACKETS_DIR / pid, pid)
            with_graph = score_packet_dir(PACKETS_DIR / pid, pid, graph=graph)
            assert no_graph.recommendation.action == Action.MANUAL_REVIEW
            assert with_graph.recommendation.action == Action.FREEZE
            assert with_graph.trust_score.overall < no_graph.trust_score.overall

    def test_quickcash_ring_escalates_to_freeze(self, graph):
        from services.risk.app.aggregator import score_packet_dir
        from shared.schemas import Action

        for pid in ("PKT-0018", "PKT-0019", "PKT-0020", "PKT-0021"):
            with_graph = score_packet_dir(PACKETS_DIR / pid, pid, graph=graph)
            assert with_graph.recommendation.action == Action.FREEZE

    def test_clean_packets_stay_approved_with_graph(self, graph):
        """Graph linkage must not flip any clean packet out of APPROVE."""
        from services.risk.app.aggregator import score_packet_dir
        from shared.schemas import Action

        labels = _labels()
        clean = [p for p, e in labels.items() if e["label"] == "clean"]
        for pid in clean:
            dec = score_packet_dir(PACKETS_DIR / pid, pid, graph=graph)
            assert dec.recommendation.action == Action.APPROVE, (
                f"{pid} (clean) -> {dec.recommendation.action} with graph"
            )

    def test_graph_evidence_in_chain(self, graph):
        from services.risk.app.aggregator import score_packet_dir

        dec = score_packet_dir(PACKETS_DIR / "PKT-0031", "PKT-0031", graph=graph)
        assert any(e.category == EvidenceCategory.GRAPH for e in dec.evidence_chain)


# ── endpoints ─────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not MODELS_EXIST, reason="models not trained yet")
class TestGraphEndpoints:
    def _client(self, tmp_store: Path):
        import os

        os.environ["TRUSTSHIELD_GRAPH_STORE"] = str(tmp_store)
        from fastapi.testclient import TestClient
        from services.risk.app.main import app
        return TestClient(app)

    def test_upsert_and_clusters(self, tmp_path):
        client = self._client(tmp_path / "g.pkl")
        # upsert two applications on the same property by different applicants
        client.post("/risk/graph/upsert", json={
            "packet_id": "A", "applicant_pan": "P1", "property_ids": ["PROP-9"]})
        client.post("/risk/graph/upsert", json={
            "packet_id": "B", "applicant_pan": "P2", "property_ids": ["PROP-9"]})
        resp = client.get("/risk/graph/clusters")
        assert resp.status_code == 200
        clusters = resp.json()["collateral_clusters"]
        assert any(c["property_id"] == "PROP-9" for c in clusters)

    def test_subgraph_endpoint(self, tmp_path):
        client = self._client(tmp_path / "g.pkl")
        client.post("/risk/graph/upsert", json={
            "packet_id": "A", "applicant_pan": "P1", "property_ids": ["PROP-9"]})
        resp = client.get("/risk/graph/subgraph/A")
        assert resp.status_code == 200
        assert any(n["id"] == "app:A" for n in resp.json()["nodes"])
