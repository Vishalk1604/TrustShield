"""Phase 8 test — the demo seed/replay script reproduces from a clean state.

`scripts/seed_demo.py` rebuilds the graph and asserts every staged packet lands on
its expected action; this test runs it end-to-end and checks it succeeds.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "services" / "risk" / "models"
MODELS_EXIST = (MODELS_DIR / "gradient_boosting.joblib").exists()


@pytest.mark.skipif(not MODELS_EXIST, reason="models not trained yet")
def test_seed_demo_replay_succeeds():
    result = subprocess.run(
        [sys.executable, "scripts/seed_demo.py"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"seed_demo failed:\n{result.stdout}\n{result.stderr}"
    assert "Demo replay OK" in result.stdout
    # the double-financing reveal must be present
    assert "Collateral pledged across multiple applications" in result.stdout
