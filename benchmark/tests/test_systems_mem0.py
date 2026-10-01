"""Mem0 scoping for the selective benchmark, without a store: the filters a recall sends."""

import pytest

pytest.importorskip("memgate")

from smbench.selective.systems_mem0 import TAG, filters_for  # noqa: E402


def test_filters_for_scopes():
    assert filters_for([]) is None                                           # nothing readable: no search at all
    assert filters_for(["ls_a"]) == {"user_id": "ls_a"}
    f = filters_for(["ls_a", "ls_b"])
    assert f["agent_id"] == TAG and f["OR"] == [{"user_id": "ls_a"}, {"user_id": "ls_b"}]
