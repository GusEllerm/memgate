"""The clients' decisions and routing, with the transport replaced by a recorder (no server needed)."""

import asyncio

import pytest

from memgate.adapters.hindsight.client import AsyncHindsightMemory, HindsightMemory, Recalled
from memgate.context import Context, Gate, partition_bank
from memgate.derivation import conversation_labels


class Recording:
    """Replaces `_call`: records each request and answers like an empty Hindsight."""

    def __init__(self):
        self.calls = []

    def answer(self, client, method, path, body, agent, location, role):
        self.calls.append((client._base_for(path), method, path, body, agent, location, role))
        if path.endswith("/memories/recall"):
            return {"results": [{"text": f"from {path.split('/')[4]}", "tags": ["ls_x"],
                                 "scores": {"final": 0.9 if "--ha--" in path else 0.5}}]}
        return {}


def sync_client(gate, **kw):
    rec = Recording()
    mem = HindsightMemory(gate, bank="b", base_url="http://shared", **kw)
    mem._call = lambda method, path, body, *, agent=None, location=None, role="agent": rec.answer(
        mem, method, path, body, agent, location, role)
    return mem, rec


def async_client(gate, **kw):
    pytest.importorskip("httpx")
    rec = Recording()
    mem = AsyncHindsightMemory(gate, bank="b", base_url="http://shared", **kw)

    async def fake(method, path, body, *, agent=None, location=None, role="agent"):
        return rec.answer(mem, method, path, body, agent, location, role)
    mem._call = fake
    return mem, rec


@pytest.fixture
def gate(world, registry):
    return Gate(world, registry, "s")


def test_partitions_route_to_their_own_server(gate):
    mem, rec = sync_client(gate, partition_url="http://partitions")
    mem.remember(Context("ada", "vault", ("ada", "bo")), "inside")
    mem.remember(Context("ada", "lab", ("ada", "bo")), "outside")
    writes = [(base, path) for base, method, path, *_ in rec.calls if method == "POST"]
    assert ("http://partitions", f"/v1/default/banks/{partition_bank('b', 'vault')}/memories") in writes
    assert ("http://shared", "/v1/default/banks/b/memories") in writes

    rec.calls.clear()
    batch = mem.recall(Context("ada", "vault"), "anything")
    assert {base for base, *_ in rec.calls if _[1].endswith("/recall")} == {"http://shared", "http://partitions"}
    assert batch[0].text == f"from {partition_bank('b', 'vault')}"            # merged by score across servers


def test_without_a_partition_server_everything_goes_to_one(gate):
    mem, rec = sync_client(gate)
    mem.remember(Context("ada", "vault", ("ada",)), "inside")
    assert {base for base, *_ in rec.calls} == {"http://shared"}


def test_carry_out_from_a_recalled_memory(gate, registry):
    mem, rec = sync_client(gate)
    earlier = conversation_labels("lab", ["ada", "bo"])          # formed with Bo, earlier
    registry.register(earlier)
    item = Recalled("Bo thinks the kiln runs hot.", earlier.id, None, "w_earlier")
    now = Context("ada", "lab")                                    # Ada alone now
    mem.carry_out(now, "Bo thinks the kiln runs hot.", "opinion", source=item)
    posted = [body for _, method, path, body, *_ in rec.calls if method == "POST"]
    assert posted and posted[-1]["items"][0]["context"] == "carried out (opinion)"
    with pytest.raises(PermissionError):                           # not readable here: refused
        mem.carry_out(Context("ada", "cafe"), "x", "opinion", source=item)
    with pytest.raises(PermissionError):                           # by label-set ID, out of a sealed place
        sealed = conversation_labels("macrodata", ["ada"])
        registry.register(sealed)
        mem.carry_out(Context("ada", "macrodata"), "x", "fact", source=sealed.id)


def test_carry_out_records_the_recalled_write_as_its_source(world, registry, tmp_path):
    from memgate.provenance import ProvenanceLog
    gate = Gate(world, registry, "s")
    log = ProvenanceLog(tmp_path, gate)
    mem, _ = sync_client(gate, provenance=log)
    earlier = conversation_labels("lab", ["ada", "bo"])
    registry.register(earlier)
    w = mem.carry_out(Context("ada", "lab"), "kept", "opinion", source=Recalled("x", earlier.id, None, "w_earlier"))
    assert log.sources_of(w, ["shared"]) == ["w_earlier"]


def test_the_async_client_decides_and_routes_the_same(gate, registry):
    async def go():
        mem, rec = async_client(gate, partition_url="http://partitions")
        await mem.remember(Context("ada", "vault", ("ada", "bo")), "inside")
        batch = await mem.recall(Context("ada", "vault"), "anything")
        with pytest.raises(PermissionError):
            await mem.carry_out(Context("ada", "vault", ("ada", "bo")), "out", "opinion")
        with pytest.raises(PermissionError):
            await mem.remember(Context("ada", "nowhere"), "unknown place")
        await mem.aclose()
        return rec, batch
    rec, batch = asyncio.run(go())
    assert ("http://partitions", "POST", f"/v1/default/banks/{partition_bank('b', 'vault')}/memories") in \
        [(b, m, p) for b, m, p, *_ in rec.calls]
    assert batch[0].text == f"from {partition_bank('b', 'vault')}"


def test_world_check_interval_from_the_environment(tmp_path, monkeypatch):
    (tmp_path / "w.json").write_text('{"environments": [{"id": "e"}], "locations": [{"id": "l", "environment": "e"}], "agents": ["a"]}')
    monkeypatch.setenv("MEMGATE_WORLD", str(tmp_path / "w.json"))
    monkeypatch.setenv("MEMGATE_REGISTRY", str(tmp_path / "r.sqlite"))
    monkeypatch.setenv("MEMGATE_SECRET", "s")
    assert Gate.from_env().check_every == 1.0
    monkeypatch.setenv("MEMGATE_WORLD_CHECK_S", "0.1")
    assert Gate.from_env().check_every == 0.1
