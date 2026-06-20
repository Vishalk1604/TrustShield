"""Synthetic tamper-image dataset + eval harness (plan §10 Day 2).

Builds a tiny labeled clean/tampered dataset (rasterized synthetic PDFs + ground-truth masks) and
runs the image-forensics eval over it, asserting the headline guarantee holds: ZERO false positives
on clean documents, and the realistic paint/splice edits are detected + localized. Writes results to
a tmp dir so the committed `results/` is untouched.
"""

import numpy as np
import pytest
from PIL import Image

from data.generator.build_image_dataset import DEFAULT_PACKETS, build_dataset


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    if not DEFAULT_PACKETS.exists():
        pytest.skip("synthetic packets not generated")
    out = tmp_path_factory.mktemp("img_ds")
    summary = build_dataset(out_dir=out, n_sources=2, seed=7)
    return out, summary


def test_dataset_structure_and_masks(dataset):
    out, s = dataset
    assert s["n_clean"] == 2 and s["n_tampered"] == 2 * len(s["tamper_types"])
    assert (out / "labels.json").exists()
    for rec in s["records"]:
        assert (out / rec["file"]).exists()
        if rec["label"] == "tampered":
            mask = np.asarray(Image.open(out / rec["mask"]).convert("L"))
            assert mask.max() == 255 and mask.min() == 0          # a real binary mask
            assert (mask > 127).sum() > 0                          # non-empty tampered region
            assert rec["boxes"]                                    # ground-truth bbox recorded


def test_eval_zero_false_positives_and_detects_edits(dataset, tmp_path, monkeypatch):
    import scripts.eval_image_forensics as ev

    monkeypatch.setattr(ev, "RESULTS_DIR", tmp_path / "results")  # don't clobber committed results
    out, _ = dataset
    m = ev.evaluate(images_dir=out)

    # Headline guarantee: clean documents are never flagged (precision 1.0, no false positives).
    assert m["detection"]["confusion"]["fp"] == 0
    assert m["detection"]["precision"] == 1.0
    # The realistic "edit a number" attack is detected and localized.
    by_type = m["localization"]["by_tamper_type"]
    assert by_type["number_edit"]["localization_hit_rate"] >= 0.5
    # results were written
    assert (tmp_path / "results" / "metrics.json").exists()
    assert (tmp_path / "results" / "summary.md").exists()
