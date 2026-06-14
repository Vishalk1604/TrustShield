"""Phase 6 tests — the demo endpoints that drive the investigator dashboard.

These score the committed synthetic packets by id (the browser cannot hand local
file paths to the backend) and expose the cross-application graph.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "services" / "risk" / "models"
MODELS_EXIST = (MODELS_DIR / "gradient_boosting.joblib").exists()


@pytest.mark.skipif(not MODELS_EXIST, reason="models not trained yet")
class TestDemoEndpoints:
    def _client(self, tmp_path):
        os.environ["TRUSTSHIELD_GRAPH_STORE"] = str(tmp_path / "g.pkl")
        from fastapi.testclient import TestClient
        from services.risk.app.main import app
        return TestClient(app)

    def test_list_packets(self, tmp_path):
        client = self._client(tmp_path)
        resp = client.get("/risk/demo/packets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 33
        sample = body["packets"][0]
        assert "packet_id" in sample
        assert "ground_truth_label" in sample
        assert "n_docs" in sample

    def test_seed_builds_clusters(self, tmp_path):
        client = self._client(tmp_path)
        resp = client.post("/risk/demo/seed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["n_applications"] == 33
        assert body["employer_rings"] >= 1
        assert body["collateral_clusters"] >= 1

    def test_score_double_financing_freezes(self, tmp_path):
        client = self._client(tmp_path)
        client.post("/risk/demo/seed")
        resp = client.post("/risk/demo/score/PKT-0031")
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"]["recommendation"]["action"] == "freeze"
        assert len(body["decision"]["evidence_chain"]) >= 1
        assert len(body["subgraph"]["nodes"]) >= 1
        # graph evidence must be present in the chain
        cats = {e["category"] for e in body["decision"]["evidence_chain"]}
        assert "graph" in cats

    def test_score_clean_approves(self, tmp_path):
        client = self._client(tmp_path)
        client.post("/risk/demo/seed")
        resp = client.post("/risk/demo/score/PKT-0001")
        assert resp.status_code == 200
        assert resp.json()["decision"]["recommendation"]["action"] == "approve"

    def test_score_unknown_packet_404(self, tmp_path):
        client = self._client(tmp_path)
        resp = client.post("/risk/demo/score/PKT-9999")
        assert resp.status_code == 404

    def test_score_without_graph_seeds_on_the_fly(self, tmp_path):
        """Scoring with use_graph before seeding should still populate the graph."""
        client = self._client(tmp_path)
        resp = client.post("/risk/demo/score/PKT-0031?use_graph=true")
        assert resp.status_code == 200
        # on-the-fly build means the double-financing collateral is detected -> freeze
        assert resp.json()["decision"]["recommendation"]["action"] == "freeze"
