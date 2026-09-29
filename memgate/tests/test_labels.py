import pytest

from memgate.labels import Label, LabelSet


def test_id_is_order_independent_and_stable():
    a = LabelSet.build(locs=["lab"], withs=["bo", "ada"])
    b = LabelSet.of(["with:ada", "loc:lab", "with:bo"])
    assert a.id == b.id and a.id.startswith("ls_")
    assert a.key == "loc:lab|with:ada|with:bo"


def test_different_labels_different_ids():
    assert LabelSet.build(withs=["ada"]).id != LabelSet.build(selfs=["ada"]).id


def test_rejects_bad_labels():
    with pytest.raises(ValueError):
        Label("colour", "red")
    with pytest.raises(ValueError):
        Label("loc", "a|b")
