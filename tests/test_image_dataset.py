"""Synthetic tamper-image dataset v2 + eval harness (plan §11).

Builds a tiny labeled clean/tampered dataset (realistic docs built in-process, field-targeted seamless
edits across a naive→blended→pro difficulty spectrum + geometric tampers, with ground-truth masks) and
runs the image-forensics eval over it. Asserts the headline guarantee that still holds: ZERO false
positives on clean documents. (The seamless `pro` edits are realistic forgeries designed to evade the
hand-tuned pixel heuristics — that gap is measured, not asserted away; it is the job of the learned
forgery model.) Writes results to a tmp dir so the committed `results/` is untouched.
"""

import numpy as np
import pytest
from PIL import Image

from data.generator.build_image_dataset import DIFFICULTIES, build_dataset


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("img_ds")
    # 2 sources (form16 + salary_slip). dpi=150 keeps the heuristic eval fast in CI; the shipped
    # dataset renders at 300 dpi (verified in scripts/eval_forgery_v2.py), but the structure + zero-FP
    # invariants checked here are resolution-independent.
    summary = build_dataset(out_dir=out, n_sources=2, seed=7, dpi=150)
    return out, summary


def test_dataset_structure_masks_and_difficulty(dataset):
    out, s = dataset
    assert s["n_clean"] == 2 and s["n_tampered"] > 0
    assert (out / "labels.json").exists()
    seen_diff, seen_fields = set(), set()
    for rec in s["records"]:
        assert (out / rec["file"]).exists()
        assert rec["split"] in ("train", "val", "test")
        if rec["label"] == "tampered":
            mask = np.asarray(Image.open(out / rec["mask"]).convert("L"))
            assert mask.max() == 255 and (mask > 127).sum() > 0    # real, non-empty binary mask
            assert rec["boxes"]                                    # ground-truth bbox(es) recorded
            seen_diff.add(rec["difficulty"])
            if rec.get("field_name"):
                seen_fields.add(rec["field_name"])
    # the full difficulty spectrum is present, plus the field-targeted fraud fields
    assert {"naive", "blended", "pro"}.issubset(seen_diff)
    assert set(DIFFICULTIES).issubset(seen_diff)
    assert seen_fields & {"gross_salary", "tds", "net_pay", "basic"}


def test_eval_zero_false_positives(dataset, tmp_path, monkeypatch):
    import scripts.eval_image_forensics as ev

    monkeypatch.setattr(ev, "RESULTS_DIR", tmp_path / "results")  # don't clobber committed results
    out, _ = dataset
    m = ev.evaluate(images_dir=out)

    # Headline guarantee: clean documents are NEVER flagged (precision 1.0, no false positives).
    assert m["detection"]["confusion"]["fp"] == 0
    assert m["detection"]["precision"] == 1.0
    # The eval reports a per-difficulty breakdown (detection rate fades from naive → pro by design).
    assert "by_difficulty" in m and "pro" in m["by_difficulty"]
    assert (tmp_path / "results" / "metrics.json").exists()
    assert (tmp_path / "results" / "summary.md").exists()
