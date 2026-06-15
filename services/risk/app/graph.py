"""Phase 5 — Cross-Application Graph.

A NetworkX graph linking applications by their shared attributes (applicant PAN,
employer, property/title ID, document-template fingerprint). Surfaces two kinds of
cross-application fraud a single-document tool is blind to:

  1. APPLICATION-FRAUD RING — one employer (and shared document template) claimed by
     several *distinct* applicants. The synthetic "QuickCash" ring is the example.
  2. DOUBLE-FINANCED COLLATERAL — one property pledged across several live applications
     by different applicants (loan stacking — exactly what CERSAI exists to catch).

Hub suppression: an attribute shared by a large fraction of applications (e.g. the
generator's default document template, which 25 packets share) is not discriminative
and is ignored for clustering / subgraph extraction. Only *minority* shared attributes
form links.

Persistence: the graph pickles to ``services/risk/graph_store/app_graph.pkl`` so the demo
accumulates linkage across uploads. All local; no network.
"""

from __future__ import annotations

import math
import pickle
from pathlib import Path
from typing import Iterable, Optional

import networkx as nx

from shared.schemas import EvidenceCategory, EvidenceItem, Severity

# Node-kind prefixes (keep node ids unique across kinds).
KIND_APP = "app"
KIND_PAN = "pan"
KIND_EMPLOYER = "employer"
KIND_PROPERTY = "property"
KIND_TEMPLATE = "template"

_ATTR_KINDS = (KIND_PAN, KIND_EMPLOYER, KIND_PROPERTY, KIND_TEMPLATE)

_DEFAULT_STORE = Path(__file__).resolve().parent.parent / "graph_store" / "app_graph.pkl"


def _nid(kind: str, value: str) -> str:
    return f"{kind}:{value}"


class ApplicationGraph:
    """Undirected attribute graph over loan applications."""

    def __init__(self, graph: Optional[nx.Graph] = None) -> None:
        self.G: nx.Graph = graph if graph is not None else nx.Graph()

    # ------------------------------------------------------------------ build

    def upsert_application(
        self,
        packet_id: str,
        *,
        applicant_pan: Optional[str] = None,
        employer: Optional[str] = None,
        property_ids: Optional[Iterable[str]] = None,
        template_fingerprints: Optional[Iterable[str]] = None,
        action: Optional[str] = None,
        label: Optional[str] = None,
    ) -> None:
        """Add or update one application and its attribute edges (idempotent)."""
        app_node = _nid(KIND_APP, packet_id)
        # Re-upsert: drop existing attribute edges so updates don't leave stale links.
        if self.G.has_node(app_node):
            for nbr in list(self.G.neighbors(app_node)):
                self.G.remove_edge(app_node, nbr)
        self.G.add_node(app_node, kind=KIND_APP, label=packet_id, action=action, packet_label=label)

        def _link(kind: str, value: Optional[str]) -> None:
            if not value:
                return
            node = _nid(kind, value)
            if not self.G.has_node(node):
                self.G.add_node(node, kind=kind, label=value)
            self.G.add_edge(app_node, node)

        _link(KIND_PAN, applicant_pan)
        _link(KIND_EMPLOYER, employer)
        for pid in property_ids or []:
            _link(KIND_PROPERTY, pid)
        for fp in template_fingerprints or []:
            _link(KIND_TEMPLATE, fp)

    # --------------------------------------------------------------- helpers

    def _app_nodes(self) -> list[str]:
        return [n for n, d in self.G.nodes(data=True) if d.get("kind") == KIND_APP]

    def _hub_threshold(self) -> int:
        """Attribute nodes linked to more apps than this are non-discriminative hubs."""
        n_apps = len(self._app_nodes())
        return max(6, math.ceil(0.33 * n_apps))

    def _apps_on(self, attr_node: str) -> list[str]:
        return [n for n in self.G.neighbors(attr_node)
                if self.G.nodes[n].get("kind") == KIND_APP]

    def _pans_of_app(self, app_node: str) -> set[str]:
        return {n for n in self.G.neighbors(app_node)
                if self.G.nodes[n].get("kind") == KIND_PAN}

    def _distinct_pans_on(self, attr_node: str) -> set[str]:
        pans: set[str] = set()
        for app in self._apps_on(attr_node):
            pans |= self._pans_of_app(app)
        return pans

    def _is_hub(self, attr_node: str) -> bool:
        return len(self._apps_on(attr_node)) > self._hub_threshold()

    # -------------------------------------------------------------- clusters

    def collateral_clusters(self) -> list[dict]:
        """Properties pledged across >=2 distinct applicants (double-financing)."""
        out: list[dict] = []
        for n, d in self.G.nodes(data=True):
            if d.get("kind") != KIND_PROPERTY or self._is_hub(n):
                continue
            apps = self._apps_on(n)
            pans = self._distinct_pans_on(n)
            if len(apps) >= 2 and len(pans) >= 2:
                out.append({
                    "type": "double_financed_collateral",
                    "property_id": d["label"],
                    "applications": sorted(self.G.nodes[a]["label"] for a in apps),
                    "distinct_applicants": len(pans),
                })
        out.sort(key=lambda c: len(c["applications"]), reverse=True)
        return out

    def employer_rings(self) -> list[dict]:
        """Employers claimed by >=2 distinct applicants (identity / application ring)."""
        out: list[dict] = []
        for n, d in self.G.nodes(data=True):
            if d.get("kind") != KIND_EMPLOYER or self._is_hub(n):
                continue
            apps = self._apps_on(n)
            pans = self._distinct_pans_on(n)
            if len(pans) >= 2:
                # Shared (non-hub) templates among these apps = corroboration.
                shared_templates = self._shared_templates(apps)
                out.append({
                    "type": "application_fraud_ring",
                    "employer": d["label"],
                    "applications": sorted(self.G.nodes[a]["label"] for a in apps),
                    "distinct_applicants": len(pans),
                    "shared_template": bool(shared_templates),
                })
        out.sort(key=lambda c: c["distinct_applicants"], reverse=True)
        return out

    def _shared_templates(self, app_nodes: list[str]) -> set[str]:
        """Non-hub template nodes shared by >=2 of the given apps."""
        shared: set[str] = set()
        app_set = set(app_nodes)
        for n, d in self.G.nodes(data=True):
            if d.get("kind") != KIND_TEMPLATE or self._is_hub(n):
                continue
            if len(set(self._apps_on(n)) & app_set) >= 2:
                shared.add(n)
        return shared

    def clusters(self) -> dict:
        """All surfaced clusters (for GET /risk/graph/clusters)."""
        return {
            "collateral_clusters": self.collateral_clusters(),
            "employer_rings": self.employer_rings(),
            "hub_threshold": self._hub_threshold(),
            "n_applications": len(self._app_nodes()),
        }

    # ------------------------------------------------------------- evidence

    def graph_evidence_for(self, packet_id: str) -> list[EvidenceItem]:
        """Build GRAPH-category evidence items for one application."""
        app_node = _nid(KIND_APP, packet_id)
        if not self.G.has_node(app_node):
            return []
        items: list[EvidenceItem] = []

        # Collateral / double-financing.
        for nbr in self.G.neighbors(app_node):
            d = self.G.nodes[nbr]
            if d.get("kind") != KIND_PROPERTY or self._is_hub(nbr):
                continue
            apps = self._apps_on(nbr)
            pans = self._distinct_pans_on(nbr)
            if len(apps) < 2 or len(pans) < 2:
                continue
            others = sorted(self.G.nodes[a]["label"] for a in apps
                            if self.G.nodes[a]["label"] != packet_id)
            n_other = len(others)
            distinct = len(pans)
            severity = Severity.CRITICAL if distinct >= 3 else Severity.MEDIUM
            items.append(EvidenceItem(
                category=EvidenceCategory.GRAPH,
                severity=severity,
                title="Collateral pledged across multiple applications",
                description=(
                    f"Property {d['label']} is pledged as collateral in {n_other} other live "
                    f"application(s) by {distinct} distinct applicants "
                    f"({', '.join(others)}). This is the signature of double-financing / loan "
                    f"stacking — the same asset financed more than once."
                ),
                source_location="cross-application graph",
                values={
                    "property_id": d["label"],
                    "other_applications": others,
                    "distinct_applicants": distinct,
                },
                confidence=1.0,
            ))

        # Employer / application-fraud ring.
        for nbr in self.G.neighbors(app_node):
            d = self.G.nodes[nbr]
            if d.get("kind") != KIND_EMPLOYER or self._is_hub(nbr):
                continue
            apps = self._apps_on(nbr)
            pans = self._distinct_pans_on(nbr)
            if len(pans) < 2:
                continue
            others = sorted(self.G.nodes[a]["label"] for a in apps
                            if self.G.nodes[a]["label"] != packet_id)
            distinct = len(pans)
            shared_tpl = bool(self._shared_templates(apps))
            severity = Severity.CRITICAL if distinct >= 3 else Severity.HIGH
            tpl_phrase = (" and a shared document template" if shared_tpl else "")
            items.append(EvidenceItem(
                category=EvidenceCategory.GRAPH,
                severity=severity,
                title="Application-fraud ring",
                description=(
                    f"Employer '{d['label']}' is claimed by {distinct} distinct applicants across "
                    f"{len(apps)} applications{tpl_phrase}. Co-applications: {', '.join(others)}. "
                    f"Multiple fabricated identities sharing one employer is a classic fraud ring."
                ),
                source_location="cross-application graph",
                values={
                    "employer": d["label"],
                    "other_applications": others,
                    "distinct_applicants": distinct,
                    "shared_template": shared_tpl,
                },
                confidence=1.0,
            ))

        # Same applicant across multiple applications (informational).
        for nbr in self.G.neighbors(app_node):
            d = self.G.nodes[nbr]
            if d.get("kind") != KIND_PAN or self._is_hub(nbr):
                continue
            apps = self._apps_on(nbr)
            if len(apps) < 2:
                continue
            others = sorted(self.G.nodes[a]["label"] for a in apps
                            if self.G.nodes[a]["label"] != packet_id)
            items.append(EvidenceItem(
                category=EvidenceCategory.GRAPH,
                severity=Severity.INFO,
                title="Repeat applicant",
                description=(
                    f"The same applicant appears in {len(others)} other application(s): "
                    f"{', '.join(others)}. Provided for context; not fraud on its own."
                ),
                source_location="cross-application graph",
                values={"other_applications": others},
                confidence=1.0,
            ))

        return items

    # ------------------------------------------------------------- subgraph

    def subgraph_for(self, packet_id: str, max_nodes: int = 30) -> dict:
        """A small subgraph around one application for visualisation.

        Includes the app, its non-hub attribute nodes, and the other apps that share
        those attributes. Returns plain dicts (nodes + edges) the dashboard can render.
        """
        app_node = _nid(KIND_APP, packet_id)
        if not self.G.has_node(app_node):
            return {"nodes": [], "edges": []}

        keep: set[str] = {app_node}
        for attr in self.G.neighbors(app_node):
            if self.G.nodes[attr].get("kind") in _ATTR_KINDS and not self._is_hub(attr):
                keep.add(attr)
                for app in self._apps_on(attr):
                    keep.add(app)
        # Cap size for the viz.
        if len(keep) > max_nodes:
            keep = set(list(keep)[:max_nodes])

        nodes = [
            {"id": n, "kind": self.G.nodes[n].get("kind"), "label": self.G.nodes[n].get("label")}
            for n in keep
        ]
        edges = [
            {"source": u, "target": v}
            for u, v in self.G.edges()
            if u in keep and v in keep
        ]
        return {"nodes": nodes, "edges": edges}

    # ----------------------------------------------------------- persistence

    def save(self, path: Optional[Path] = None) -> Path:
        path = Path(path) if path else _DEFAULT_STORE
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self.G, fh)
        return path

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ApplicationGraph":
        path = Path(path) if path else _DEFAULT_STORE
        if not path.exists():
            return cls()
        with open(path, "rb") as fh:
            return cls(pickle.load(fh))

    # ----------------------------------------------------- bulk construction

    @classmethod
    def build_from_packets(cls, packets_dir: Path, labels: dict) -> "ApplicationGraph":
        """Construct the full graph from all synthetic packets (demo / tests).

        Reads each packet's manifest for applicant/employer/property, and computes
        document template fingerprints via the Phase 1 analyzer.
        """
        import json

        from services.forensics.app.analyzer import analyze_pdf

        g = cls()
        for pkt_id, entry in labels.items():
            pkt_dir = packets_dir / pkt_id
            manifest_path = pkt_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text())
            gt = manifest.get("ground_truth", {})

            # Property IDs: from claims across docs (sale_deed / valuation / EC).
            property_ids: set[str] = set()
            top_prop = gt.get("property_id") or entry.get("property_id")
            if top_prop:
                property_ids.add(top_prop)
            for claims in gt.get("claims", {}).values():
                pid = claims.get("property_id")
                if pid:
                    property_ids.add(pid)

            # Template fingerprints: one per document (the ring shares these).
            fingerprints: set[str] = set()
            for d in manifest.get("documents", []):
                dp = pkt_dir / d["filename"]
                if not dp.exists():
                    continue
                try:
                    # Only the structural template fingerprint is needed here — skip the OCR
                    # re-OCR cross-check (§6.D2), which would OCR every page of every packet
                    # (very slow, esp. in-container) for no benefit to graph construction.
                    res = analyze_pdf(
                        str(dp), doc_type=d["doc_type"], filename=d["filename"], enable_reocr=False,
                    )
                    fp = res.get("template_fingerprint")
                    if fp:
                        fingerprints.add(fp)
                except Exception:
                    continue

            g.upsert_application(
                pkt_id,
                applicant_pan=gt.get("applicant_pan") or entry.get("applicant_pan"),
                employer=gt.get("employer") or entry.get("employer"),
                property_ids=property_ids,
                template_fingerprints=fingerprints,
                label=entry.get("label"),
            )
        return g
