"""The Cedar speed suite runs end to end at its smallest size, and the compiled filter agrees with Cedar."""

import random

import pytest

pytest.importorskip("memgate")

from smbench.speed.cedar import SHAPES, build_world, label_sets, measure  # noqa: E402


def test_label_sets_are_distinct_and_realistic():
    world = build_world(*SHAPES[1000], random.Random(1))
    sets = list(label_sets(world, 500, random.Random(1)))
    assert len({ls.id for ls in sets}) == 500
    assert sum(bool(ls.withs) for ls in sets) > 300          # mostly conversations
    assert all(ls.withs or ls.selfs for ls in sets)


def test_measure_at_the_smallest_size(tmp_path):
    row = measure(1000, tmp_path, random.Random(1))
    assert row["label_sets"] == 1000 and row["compiled_matches_exact"] is True
    assert row["allowed_ids_warm"]["median_ms"] < row["allowed_ids_cold"]["median_ms"] < row["allowed_ids_exact"]["median_ms"]
    assert (tmp_path / "registry-1000.sqlite").exists()
