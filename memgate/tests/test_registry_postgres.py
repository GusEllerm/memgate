"""The PostgreSQL registry gives the same answers as SQLite: same IDs, same compiled-filter results, same
fail-closed handling of unknown labels, serialised registration. Needs psycopg and either MEMGATE_TEST_PG
(a postgresql:// URL) or pg0 (an embedded PostgreSQL started for the test)."""

import json
import os
import random

import pytest

psycopg = pytest.importorskip("psycopg")

from memgate.labels import LabelSet  # noqa: E402
from memgate.policy import Policy  # noqa: E402
from memgate.registry import PostgresRegistry, Registry  # noqa: E402
from memgate.world import World  # noqa: E402


@pytest.fixture(scope="module")
def pg_url():
    url = os.environ.get("MEMGATE_TEST_PG")
    if url:
        yield url
        return
    pg0 = pytest.importorskip("pg0")
    name = f"memgate-test-{os.getpid()}"
    info = pg0.start(name=name, port=None, username="memgate", password="memgate", database="memgate")
    try:
        yield f"postgresql://memgate:memgate@127.0.0.1:{info.port}/memgate"
    finally:
        pg0.stop(name)
        pg0.drop(name)


@pytest.fixture
def pg(pg_url):
    reg = Registry(pg_url)
    assert isinstance(reg, PostgresRegistry)
    with reg._db.transaction():
        reg._db.execute("TRUNCATE memgate.label, memgate.label_sets")
    return reg


def test_the_url_selects_the_backend_and_answers_match_sqlite(pg):
    lite = Registry()
    sets = [LabelSet.build(locs=["lab"], withs=["ada", "bo"]), LabelSet.build(selfs=["ada"]),
            LabelSet.build(selfs=["ada"], classes=["unattributed"]), LabelSet.build(selfs=["bo"], locs=["vault"])]
    for ls in sets:
        assert pg.register(ls) == lite.register(ls) == ls.id
    assert pg.register(sets[0]) == sets[0].id and len(pg) == len(lite) == 4
    assert pg.all() == lite.all() and pg.get(sets[2].id) == sets[2]
    with pytest.raises(KeyError):
        pg.get("ls_nope")


def test_compiled_filters_run_on_postgres_like_sqlite(pg):
    rng = random.Random(5)
    w = World()
    w.add_environment("e")
    for i, l in enumerate(["l0", "l1", "l2"]):
        w.add_location(l, "e", high_assurance=(i == 0))
    w.add_agents("a0", "a1", "a2", "a3")
    lite = Registry()
    for _ in range(40):
        ls = LabelSet.build(selfs=rng.sample(["a0", "a1", "a2", "a3"], rng.choice([0, 1])),
                            locs=rng.sample(["l0", "l1", "l2"], rng.choice([0, 1])),
                            withs=rng.sample(["a0", "a1", "a2", "a3"], rng.randint(0, 2)))
        pg.register(ls)
        lite.register(ls)
    for reg in (pg, lite):
        pol = Policy(w, reg)
        for a in ("a0", "a1", "a2", "a3"):
            for l in ("l0", "l1", "l2"):
                assert pol.allowed_ids(a, l) == pol.allowed_ids_exact(a, l) == Policy(w, lite).allowed_ids_exact(a, l), (a, l)


def test_incremental_reads_and_unknown_labels_fail_closed(pg):
    pol_where = "TRUE"
    a = pg.register(LabelSet.build(selfs=["ada"]))
    ids, newest = pg.select_ids(pol_where, [])
    assert ids == {a}
    b = pg.register(LabelSet.build(selfs=["bo"]))
    ids2, newest2 = pg.select_ids(pol_where, [], after=newest)
    assert ids2 == {b} and newest2 > newest
    with pg._db.transaction():                              # as written by a future memgate
        pg._db.execute("INSERT INTO memgate.label_sets (id, key, labels) VALUES (%s, %s, %s)",
                       ("ls_future", "self:ada|mood:calm", json.dumps(["self:ada", "mood:calm"])))
        pg._db.execute("INSERT INTO memgate.label (label_set, kind, value) VALUES (%s, %s, %s), (%s, %s, %s)",
                       ("ls_future", "self", "ada", "ls_future", "mood", "calm"))
    assert set(pg.all()) == {a, b}
    assert pg.select_ids(pol_where, [])[0] == {a, b}


def test_copy_from_migrates_a_sqlite_registry(pg, tmp_path):
    lite = Registry(tmp_path / "r.sqlite")
    for who in ("ada", "bo", "cy"):
        lite.register(LabelSet.build(selfs=[who]))
    assert pg.copy_from(lite) == 3 and pg.copy_from(lite) == 0
    assert pg.all() == lite.all()
