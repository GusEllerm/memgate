"""Several processes may write one registry file at once (e.g. a host running several workers)."""

import multiprocessing as mp

from memgate.labels import LabelSet
from memgate.registry import Registry


def _worker(path: str, n: int, offset: int, out) -> None:
    reg = Registry(path)
    ids = []
    for i in range(n):
        # Half the label sets are shared by every worker (the idempotent race), half are the worker's own.
        who = f"a{i}" if i % 2 == 0 else f"w{offset}-{i}"
        ids.append(reg.register(LabelSet.build(locs=["lab"], withs=[who])))
    out.put(ids)


def test_concurrent_writers_from_several_processes(tmp_path):
    path = str(tmp_path / "registry.sqlite")
    Registry(path)                                          # created once, as a host would at startup
    ctx = mp.get_context("spawn")
    out = ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(path, 300, k, out)) for k in range(4)]
    for p in procs:
        p.start()
    results = [out.get(timeout=120) for _ in procs]
    for p in procs:
        p.join(timeout=120)
        assert p.exitcode == 0                              # no "database is locked"
    reg = Registry(path)
    registered = set(reg.all())
    assert set().union(*map(set, results)) == registered    # every write landed, none twice
    assert len(registered) == 150 + 4 * 150                  # shared ones once, each worker's own
    ids, newest = reg.select_ids("1", [], after=0)          # rowids are dense and commit-ordered
    assert ids == registered and newest == len(registered)
