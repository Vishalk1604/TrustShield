"""Phase 8 - deterministic demo replay.

Rebuilds the cross-application graph from the synthetic packets, scores the staged
demo packets, and prints the expected results so the live walkthrough (DEMO.md)
reproduces identically from a clean state. Doubles as a self-check: it asserts each
staged packet lands on its expected action.

Run from the repo root:
    .venv/Scripts/python.exe scripts/seed_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PACKETS_DIR = REPO_ROOT / "data" / "synthetic" / "packets"
LABELS_PATH = REPO_ROOT / "data" / "synthetic" / "labels.json"
METRICS_PATH = REPO_ROOT / "services" / "risk" / "models" / "metrics.json"

# The staged demo: (packet_id, headline, expected_action).
DEMO_STEPS: list[tuple[str, str, str]] = [
    ("PKT-0001", "Clean financial packet - should sail through", "approve"),
    ("PKT-0010", "Tampered Form 16 (income white-boxed) - forensics catches it", "freeze"),
    ("PKT-0014", "Income story doesn't add up across documents - semantics catches it", "freeze"),
    ("PKT-0028", "Encumbrance certificate forged to 'NIL' vs CERSAI charge - critical", "freeze"),
    ("PKT-0031", "Double-financing ring, application #1 - looks ordinary alone", "freeze"),
    ("PKT-0032", "Double-financing ring, application #2 - same property surfaces", "freeze"),
    ("PKT-0033", "Double-financing ring, application #3 - the graph reveal", "freeze"),
    ("PKT-0018", "Synthetic-identity ring (shared employer + template)", "freeze"),
    ("PKT-0034", "Flattened/repainted Form 16 - no text layer; semantics catch the inflated value, the learned model localizes the repaint on a deep scan", "freeze"),
]

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _top_evidence(decision: dict, n: int = 2) -> list[str]:
    chain = sorted(
        decision["evidence_chain"],
        key=lambda e: _SEV_ORDER.get(e["severity"], 9),
    )
    return [f"[{e['severity']}] {e['title']}" for e in chain[:n]]


def main() -> int:
    from services.risk.app.aggregator import score_packet_dir
    from services.risk.app.graph import ApplicationGraph

    if not METRICS_PATH.exists():
        print("ERROR: models not trained. Run:  python -m services.risk.train")
        return 1

    labels = json.loads(LABELS_PATH.read_text())

    print("=" * 74)
    print("  TrustShield - Demo Seed & Replay")
    print("=" * 74)

    # 1. Rebuild + persist the cross-application graph (so the dashboard shows clusters).
    print("\n[1/3] Building cross-application graph from synthetic packets ...")
    graph = ApplicationGraph.build_from_packets(PACKETS_DIR, labels)
    store = graph.save()
    clusters = graph.clusters()
    print(f"      {clusters['n_applications']} applications | "
          f"{len(clusters['employer_rings'])} fraud ring(s) | "
          f"{len(clusters['collateral_clusters'])} collateral cluster(s)")
    print(f"      graph persisted -> {store.relative_to(REPO_ROOT)}")

    # 2. Score each staged packet and check expectations.
    print("\n[2/3] Scoring staged demo packets ...\n")
    header = f"  {'packet':9} {'trust':6} {'action':14} {'OK':3} headline"
    print(header)
    print("  " + "-" * 70)

    failures = 0
    for pkt_id, headline, expected in DEMO_STEPS:
        decision = score_packet_dir(PACKETS_DIR / pkt_id, pkt_id, graph=graph).model_dump(mode="json")
        action = decision["recommendation"]["action"]
        trust = decision["trust_score"]["overall"]
        ok = action == expected
        failures += 0 if ok else 1
        print(f"  {pkt_id:9} {trust:6.1f} {action:14} {'yes' if ok else 'NO!':3} {headline}")
        for ev in _top_evidence(decision):
            print(f"      - {ev}")

    # 3. Model metrics slide.
    print("\n[3/3] Learned model metrics (5-fold CV on the synthetic set):")
    metrics = json.loads(METRICS_PATH.read_text())
    gb = metrics["gradient_boosting"]
    cm = gb["confusion_matrix"]
    print(f"      ROC-AUC: {gb['roc_auc_cv']:.4f}")
    print(f"      Confusion: TN={cm[0][0]} FP={cm[0][1]} FN={cm[1][0]} TP={cm[1][1]}")
    print("      Top features: " + ", ".join(
        f"{f['feature']} ({f['importance']:.2f})" for f in metrics["top_features"][:3]
    ))

    print("\n" + "=" * 74)
    if failures:
        print(f"  REPLAY FAILED - {failures} staged packet(s) did not match expectations.")
        print("=" * 74)
        return 1
    print("  Demo replay OK - every staged packet matched its expected action.")
    print("  Follow DEMO.md for the live 3-minute walkthrough.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
