"""The validator (memgate's second lock inside Hindsight) against its specification, without a server.

Each hook is called directly with Hindsight's own context objects, so every rule, and every way of
failing closed, is checked in isolation: who may call, what a recall is scoped to, which writes are
accepted and into which partition, and which operations are refused outright.
"""

import asyncio
import json

import pytest

hindsight = pytest.importorskip("hindsight_api")

from hindsight_api.extensions.operation_validator import (  # noqa: E402
    BankReadContext, BankReadOperation, BankWriteContext, BankWriteOperation, ConsolidateContext,
    CreateBankContext, RecallContext, ReflectContext, RetainContext)
from hindsight_api.models import RequestContext  # noqa: E402

from memgate.context import partition_bank  # noqa: E402
from memgate.derivation import conversation_labels, personal_labels, personal_note_labels  # noqa: E402

SECRET = "test-secret"
BANK = "w"
VAULT_BANK = partition_bank(BANK, "vault")


@pytest.fixture
def gate_offline(tmp_path):
    from memgate.context import Gate, load_world
    from memgate.registry import Registry
    (tmp_path / "w.json").write_text(json.dumps({"environments": [{"id": "campus"}], "locations": [{"id": "lab", "environment": "campus"}],
                                                 "agents": ["ada"]}))
    return Gate(load_world(tmp_path / "w.json"), Registry(), SECRET)


@pytest.fixture
def validator(tmp_path, monkeypatch):
    world = {"environments": [{"id": "campus"}],
             "locations": [{"id": "lab", "environment": "campus"}, {"id": "cafe", "environment": "campus"},
                           {"id": "vault", "environment": "campus", "high_assurance": True}],
             "agents": ["ada", "bo", "dee"]}
    (tmp_path / "world.json").write_text(json.dumps(world))
    monkeypatch.setenv("MEMGATE_WORLD", str(tmp_path / "world.json"))
    monkeypatch.setenv("MEMGATE_REGISTRY", str(tmp_path / "registry.sqlite"))
    monkeypatch.setenv("MEMGATE_SECRET", SECRET)
    from memgate.adapters.hindsight.validator import MemgateValidator
    return MemgateValidator()


def rc(agent=None, location=None, secret=SECRET, role=None, internal=False):
    h = {}
    if secret is not None:
        h["x-memgate-secret"] = secret
    if agent:
        h["x-memgate-agent"] = agent
    if location:
        h["x-memgate-location"] = location
    if role:
        h["x-memgate-role"] = role
    return RequestContext(extra_headers=h, internal=internal)


def run(coro):
    return asyncio.run(coro)


def retain(v, bank, labels, **who):
    ls = v.gate.registry.register(labels)
    return run(v.validate_retain(RetainContext(bank_id=bank, contents=[{"content": "x", "tags": [ls]}],
                                               request_context=rc(**who))))


# -- who may call ------------------------------------------------------------------------------------
@pytest.mark.parametrize("secret", [None, "", "wrong"])
def test_every_hook_refuses_a_caller_without_the_secret(validator, secret):
    ctx = rc("ada", "lab", secret=secret)
    assert not run(validator.validate_recall(RecallContext(bank_id=BANK, query="q", request_context=ctx))).allowed
    assert not retain(validator, BANK, conversation_labels("lab", ["ada"]), agent="ada", location="lab", secret=secret).allowed
    assert not run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, ctx))).allowed
    assert not run(validator.validate_create_bank(CreateBankContext(BANK, rc(secret=secret, role="admin")))).allowed


def test_claiming_admin_without_the_secret_gets_nothing(validator):
    assert not run(validator.validate_create_bank(CreateBankContext(BANK, rc(secret="wrong", role="admin")))).allowed


# -- recall ------------------------------------------------------------------------------------------
def test_recall_is_rescoped_to_what_the_context_may_read(validator):
    mine = validator.gate.registry.register(personal_labels("ada"))
    lab = validator.gate.registry.register(conversation_labels("lab", ["ada", "bo"]))
    other = validator.gate.registry.register(conversation_labels("lab", ["bo", "dee"]))
    ctx = RecallContext(bank_id=BANK, query="q", request_context=rc("ada", "lab"))
    r = run(validator.validate_recall(ctx))
    assert r.allowed and set(r.tags) == {mine, lab} and other not in r.tags
    assert r.tags_match == "any_strict" and r.tag_groups == []          # anything the caller sent is replaced


@pytest.mark.parametrize("who", [{"agent": "ada"}, {"location": "lab"}, {}])
def test_recall_needs_an_agent_and_a_location(validator, who):
    assert not run(validator.validate_recall(RecallContext(bank_id=BANK, query="q", request_context=rc(**who)))).allowed


def test_recall_by_unknown_agent_or_location_matches_nothing(validator):
    validator.gate.registry.register(personal_labels("ada"))
    for agent, loc in (("ada", "nowhere"), ("zed", "lab")):
        r = run(validator.validate_recall(RecallContext(bank_id=BANK, query="q", request_context=rc(agent, loc))))
        assert r.tags == ["ls_none"]


def test_a_partition_is_searched_only_from_inside(validator):
    inside = RecallContext(bank_id=VAULT_BANK, query="q", request_context=rc("ada", "vault"))
    outside = RecallContext(bank_id=VAULT_BANK, query="q", request_context=rc("ada", "lab"))
    assert run(validator.validate_recall(inside)).allowed
    assert not run(validator.validate_recall(outside)).allowed


# -- retain ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("bank,labels,agent,location,ok", [
    (BANK, conversation_labels("lab", ["ada", "bo"]), "ada", "lab", True),         # a participant, there
    (BANK, conversation_labels("lab", ["ada", "bo"]), "dee", "lab", False),        # not a participant
    (BANK, conversation_labels("lab", ["ada", "bo"]), "ada", "cafe", False),       # not there
    (BANK, personal_labels("ada"), "ada", "cafe", True),                           # own personal memory
    (BANK, personal_labels("ada"), "bo", "cafe", False),                           # another's identity
    (BANK, personal_note_labels("ada", "lab"), "ada", "lab", True),
    (BANK, personal_labels("ada"), "ada", "vault", False),                         # the write seal
    (VAULT_BANK, personal_note_labels("ada", "vault"), "ada", "vault", True),      # a vault note, in its partition
    (BANK, personal_note_labels("ada", "vault"), "ada", "vault", False),           # ...but not in the shared bank
    (VAULT_BANK, conversation_labels("lab", ["ada"]), "ada", "lab", False),        # ordinary memory in a partition
    (BANK, personal_labels("ada"), "ada", "nowhere", False),                       # unknown location: fail closed
    (BANK, personal_labels("zed"), "zed", "lab", False),                           # unknown agent: fail closed
])
def test_retain_spec(validator, bank, labels, agent, location, ok):
    assert retain(validator, bank, labels, agent=agent, location=location).allowed is ok


def test_retain_refuses_missing_or_unregistered_tags(validator):
    for tags in ([], ["ls_madeup"], [validator.gate.registry.register(personal_labels("ada"))] * 2):
        ctx = RetainContext(bank_id=BANK, contents=[{"content": "x", "tags": tags}], request_context=rc("ada", "lab"))
        assert not run(validator.validate_retain(ctx)).allowed


def test_retain_refuses_observation_scopes_wider_than_a_label_set(validator):
    ls = validator.gate.registry.register(personal_labels("ada"))
    item = {"content": "x", "tags": [ls], "observation_scopes": "per_tag"}
    ctx = RetainContext(bank_id=BANK, contents=[item], request_context=rc("ada", "lab"))
    assert not run(validator.validate_retain(ctx)).allowed


# -- operations refused outright -----------------------------------------------------------------------
def test_reads_around_the_filter_are_refused(validator):
    ctx = rc("ada", "lab")
    assert not run(validator.validate_reflect(ReflectContext(bank_id=BANK, query="q", request_context=ctx))).allowed
    assert not run(validator.validate_mental_model_get(None)).allowed
    assert not run(validator.validate_mental_model_refresh(None)).allowed
    safe = {BankReadOperation.GET_OPERATION_STATUS, BankReadOperation.LIST_OPERATIONS,
            BankReadOperation.GET_BANK_PROFILE, BankReadOperation.GET_BANK_STATS}
    for op in BankReadOperation:
        assert run(validator.validate_bank_read(BankReadContext(BANK, op, ctx))).allowed is (op in safe), op


def test_bank_administration_is_admin_only(validator):
    from memgate.adapters.hindsight.validator import SCHEDULE_ONLY
    for op in BankWriteOperation:
        agent_ok = run(validator.validate_bank_write(BankWriteContext(BANK, op, rc("ada", "lab")))).allowed
        assert agent_ok is (op in SCHEDULE_ONLY)          # only scheduling a consolidation (see the test below)
        assert run(validator.validate_bank_write(BankWriteContext(BANK, op, rc(role="admin")))).allowed
    assert not run(validator.validate_create_bank(CreateBankContext(BANK, rc("ada", "lab")))).allowed


def test_hindsights_own_background_work_passes(validator):
    assert run(validator.validate_consolidate(ConsolidateContext(bank_id=BANK, request_context=rc(internal=True)))).allowed


# -- split deployment: each server holds only its scope ---------------------------------------------
@pytest.mark.parametrize("scope,bank,ok", [
    ("all", BANK, True), ("all", VAULT_BANK, True),
    ("shared", BANK, True), ("shared", VAULT_BANK, False),
    ("partitions", BANK, False), ("partitions", VAULT_BANK, True),
])
def test_server_scope(validator, monkeypatch, scope, bank, ok):
    validator.scope = scope
    where = "vault" if bank == VAULT_BANK else "lab"
    recall = run(validator.validate_recall(RecallContext(bank_id=bank, query="q", request_context=rc("ada", where))))
    labels = personal_note_labels("ada", "vault") if bank == VAULT_BANK else conversation_labels("lab", ["ada"])
    write = retain(validator, bank, labels, agent="ada", location=where)
    stats = run(validator.validate_bank_read(BankReadContext(bank, BankReadOperation.GET_BANK_STATS, rc("ada", where))))
    create = run(validator.validate_create_bank(CreateBankContext(bank, rc(role="admin"))))
    assert recall.allowed is ok and write.allowed is ok and stats.allowed is ok and create.allowed is ok


def test_scope_comes_from_the_environment(tmp_path, monkeypatch, validator):
    from memgate.adapters.hindsight.validator import MemgateValidator
    monkeypatch.setenv("MEMGATE_SERVE_SCOPE", "partitions")
    assert MemgateValidator().scope == "partitions"
    monkeypatch.setenv("MEMGATE_SERVE_SCOPE", "everything")
    with pytest.raises(ValueError):
        MemgateValidator()


def test_validator_refuses_to_run_if_serves_settings_were_changed(validator, monkeypatch):
    """memgate serve fingerprints what it forces; a .env that changed any of it stops Hindsight starting."""
    import os
    from memgate.adapters.hindsight.validator import MemgateValidator
    from memgate.context import serve_fingerprint
    keys = ["MEMGATE_SECRET", "MEMGATE_WORLD", "HINDSIGHT_API_LLM_TRACE_ENABLED"]
    monkeypatch.setenv("HINDSIGHT_API_LLM_TRACE_ENABLED", "false")
    monkeypatch.setenv("MEMGATE_SERVE_KEYS", ",".join(keys))
    monkeypatch.setenv("MEMGATE_SERVE_FINGERPRINT", serve_fingerprint(dict(os.environ), keys))
    MemgateValidator()                                                   # untouched: starts
    monkeypatch.setenv("HINDSIGHT_API_LLM_TRACE_ENABLED", "true")         # what a hostile .env would do
    with pytest.raises(RuntimeError, match="changed after start"):
        MemgateValidator()


# -- a reused write ID stays within its label set ------------------------------------------------------
def test_retain_refuses_update_mode(validator):
    ls = validator.gate.registry.register(personal_labels("ada"))
    for mode in ("append", "replace"):
        item = {"content": "x", "tags": [ls], "update_mode": mode}
        ctx = RetainContext(bank_id=BANK, contents=[item], request_context=rc("ada", "lab"))
        assert not run(validator.validate_retain(ctx)).allowed


def test_retain_refuses_a_write_id_minted_under_another_label_set(validator):
    from memgate.provenance import write_id_for
    mine = validator.gate.registry.register(personal_labels("ada"))
    theirs = validator.gate.registry.register(conversation_labels("lab", ["bo", "dee"]))
    for doc, ok in [(write_id_for(mine, "k"), True), (write_id_for(mine), True), (None, True),
                    (write_id_for(theirs, "k"), False), ("w_0123456789abcdef", False), ("anything", False)]:
        item = {"content": "x", "tags": [mine]}
        if doc is not None:
            item["document_id"] = doc
        ctx = RetainContext(bank_id=BANK, contents=[item], request_context=rc("ada", "lab"))
        assert run(validator.validate_retain(ctx)).allowed is ok, doc


# -- the server's log never holds a recall query ------------------------------------------------------
QUERY_LINES = [
    ("[RECALL ranch-12345-abcdef] Query: 'the lab safe combination is 4471 and...' (budget=mid, max_tokens=4096, tags=['ls_x'])",
     "[RECALL ranch-12345-abcdef] Query: [redacted] (budget=mid, max_tokens=4096, tags=['ls_x'])"),
    ("[RECALL ranch] Starting recall for query: the lab safe combination is 4471..., tags=['ls_x'], tags_match=any_strict",
     "[RECALL ranch] Starting recall for query: [redacted], tags=['ls_x'], tags_match=any_strict"),
    ("[RECALL ranch] Starting recall for query: the lab safe combination is 4471...",
     "[RECALL ranch] Starting recall for query: [redacted]"),
    ("[REFLECT r1] Starting agentic reflect for query: what is the combination?...",
     "[REFLECT r1] Starting agentic reflect for query: [redacted]"),
    ("[RECALL ranch] Complete: 3 facts (120 tok) | 0.412s", "[RECALL ranch] Complete: 3 facts (120 tok) | 0.412s"),
]


@pytest.mark.parametrize("line, shown", QUERY_LINES)
def test_queries_are_redacted_from_hindsights_log(validator, line, shown, caplog):
    import logging
    from memgate.adapters.hindsight.validator import install_log_redaction
    install_log_redaction()        # what the validator did at load; pytest's capture handler is newer than that
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("hindsight_api.engine.memory_engine").info("\n" + line)         # Hindsight's buffered form
        logging.getLogger("hindsight_api.engine.memory_engine").error(line)               # and the failure path
        logging.getLogger("other").info(line)                                              # not Hindsight: untouched
    assert [r.getMessage() for r in caplog.records] == ["\n" + shown, shown, line]


def test_redaction_is_installed_once_on_root_and_its_handlers(validator, monkeypatch):
    import logging
    from memgate.adapters.hindsight.validator import RedactQueries, install_log_redaction
    root = logging.getLogger()
    h = logging.StreamHandler()
    root.addHandler(h)
    try:
        install_log_redaction()
        install_log_redaction()
        assert sum(isinstance(f, RedactQueries) for f in root.filters) == 1
        assert sum(isinstance(f, RedactQueries) for f in h.filters) == 1
    finally:
        root.removeHandler(h)


def test_an_agent_may_schedule_consolidation_but_nothing_else(validator):
    """Hindsight submits consolidation after every retain with the writer's context; that one bank write is
    allowed to an authenticated agent (it stores nothing; the run is validated by validate_consolidate)."""
    sched = lambda **who: run(validator.validate_bank_write(BankWriteContext(
        bank_id=BANK, operation=BankWriteOperation.SUBMIT_ASYNC_CONSOLIDATION, request_context=rc(**who))))
    assert sched(agent="ada", location="lab").allowed
    assert sched(role="admin").allowed
    assert not sched(agent="ada", location="lab", secret="wrong").allowed            # still needs the secret
    for op in (BankWriteOperation.DELETE_BANK, BankWriteOperation.DELETE_DOCUMENT, BankWriteOperation.CLEAR_OBSERVATIONS):
        ctx = BankWriteContext(bank_id=BANK, operation=op, request_context=rc("ada", "lab"))
        assert not run(validator.validate_bank_write(ctx)).allowed                   # every other write: admin only


def test_a_class_set_is_written_like_the_plain_personal_set(validator):
    """The validator needs no change for classes: a class set is a registered label set the owner may write
    anywhere {self:A} may be written, and nobody else may."""
    unnamed = personal_labels("ada", "unattributed")
    assert retain(validator, BANK, unnamed, agent="ada", location="lab").allowed
    assert not retain(validator, BANK, unnamed, agent="bo", location="lab").allowed
    assert not retain(validator, VAULT_BANK, unnamed, agent="ada", location="vault").allowed      # the seal holds
    assert not retain(validator, BANK, unnamed, agent="ada", location="vault").allowed


# -- the version handshake --------------------------------------------------------------------------
def test_a_client_newer_than_the_server_is_refused(validator, monkeypatch):
    from memgate.adapters.hindsight import validator as v
    import memgate
    rcx = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": "admin", "x-memgate-version": "99.0.0"})
    r = run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, rcx)))
    assert not r.allowed and v.VERSION_REFUSED in r.reason and "upgrade the server" in r.reason
    same = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": "admin", "x-memgate-version": memgate.__version__})
    assert run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, same))).allowed
    unversioned = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": "admin"})
    assert run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, unversioned))).allowed


def test_a_minimum_client_version_refuses_old_and_unversioned_clients(validator):
    import memgate
    validator.min_client = memgate.__version__
    old = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": "admin", "x-memgate-version": "0.5.0"})
    assert "stale worker" in run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, old))).reason
    unversioned = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": "admin"})
    assert not run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, unversioned))).allowed
    ok = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": "admin", "x-memgate-version": memgate.__version__})
    assert run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, ok))).allowed


def test_the_client_turns_a_426_into_version_mismatch():
    from memgate.adapters.hindsight.store import HindsightError, VersionMismatch, _Routing
    with pytest.raises(VersionMismatch):
        _Routing.raise_for(426, '{"detail": "memgate version: client 9.9.9 is newer than this server (0.6.0)"}')
    with pytest.raises(HindsightError) as e:
        _Routing.raise_for(403, '{"detail": "memgate version: looks like one but is a plain refusal"}')
    assert not isinstance(e.value, VersionMismatch)


def test_version_refusals_carry_status_426_and_the_version_header_is_forwarded(validator):
    from memgate.context import HEADERS, HEADER_VERSION
    assert HEADER_VERSION in HEADERS                                      # on memgate serve's passthrough allowlist
    from hindsight_api.api import passthrough_headers as ph
    raw = [(b"x-memgate-secret", b"s"), (b"X-Memgate-Version", b"0.6.0"), (b"x-other", b"no")]
    kept = ph.collect_passthrough_headers(raw, list(HEADERS))             # what Hindsight hands the validator
    assert set(kept) == {"x-memgate-secret", HEADER_VERSION}
    newer = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": "admin", "x-memgate-version": "99.0.0"})
    r = run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, newer)))
    assert not r.allowed and r.status_code == 426
    wrong = RequestContext(extra_headers={"x-memgate-secret": "wrong", "x-memgate-version": "99.0.0"})
    r = run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, wrong)))
    assert not r.allowed and r.status_code == 403 and "version" not in r.reason    # the secret is checked first


@pytest.mark.parametrize("text, release", [
    ("0.6.0", (0, 6, 0)), ("0.6", (0, 6, 0)), ("1", (1, 0, 0)), ("0.6.0rc1", (0, 6, 0)), ("0.6.0-dev3", (0, 6, 0)),
    ("1.2.3.4", None), ("abc", None), ("", None), (None, None), ("-1.0.0", None), (" 0.7.1 ", (0, 7, 1)),
])
def test_release_parsing(text, release):
    from memgate.adapters.hindsight.validator import _release
    assert _release(text) == release


def test_a_minimum_above_the_server_or_unparseable_is_refused_at_load(tmp_path, monkeypatch, validator):
    import memgate
    from memgate.adapters.hindsight.validator import MemgateValidator
    for bad in ("99.0.0", "abc"):
        monkeypatch.setenv("MEMGATE_SERVE_MIN_CLIENT", bad)
        with pytest.raises(ValueError):
            MemgateValidator()
    monkeypatch.setenv("MEMGATE_SERVE_MIN_CLIENT", memgate.__version__)
    assert MemgateValidator().min_client == memgate.__version__


def test_unknown_roles_are_refused(validator):
    for role in ("internal", "root", "Admin"):
        ctx = RequestContext(extra_headers={"x-memgate-secret": SECRET, "x-memgate-role": role})
        assert not run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, ctx))).allowed
    internal = RequestContext(extra_headers={}, internal=True)                 # Hindsight's own work: no header needed
    assert run(validator.validate_bank_read(BankReadContext(BANK, BankReadOperation.GET_BANK_STATS, internal))).allowed


def test_the_bank_list_is_empty_for_everyone_but_an_admin(validator):
    from hindsight_api.extensions.operation_validator import BankListContext
    banks = [{"bank_id": "w"}, {"bank_id": VAULT_BANK}]
    assert run(validator.filter_bank_list(BankListContext(banks, rc(role="admin")))).banks == banks
    assert run(validator.filter_bank_list(BankListContext(banks, rc("ada", "lab")))).banks == []
    assert run(validator.filter_bank_list(BankListContext(banks, RequestContext(extra_headers={})))).banks == []
    assert run(validator.filter_bank_list(BankListContext(banks, rc(secret="wrong", role="admin")))).banks == []


def test_an_agent_schedules_consolidation_only_where_it_is(validator):
    sched = lambda bank, **who: run(validator.validate_bank_write(BankWriteContext(
        bank_id=bank, operation=BankWriteOperation.SUBMIT_ASYNC_CONSOLIDATION, request_context=rc(**who))))
    assert sched(BANK, agent="ada", location="lab").allowed
    assert sched(VAULT_BANK, agent="ada", location="vault").allowed                   # inside the vault
    assert not sched(VAULT_BANK, agent="ada", location="lab").allowed                 # a partition from outside
    assert sched(VAULT_BANK, role="admin").allowed


def test_check_version_is_a_gated_request_that_tolerates_a_missing_bank(gate_offline):
    from memgate.adapters.hindsight.client import HindsightMemory, VersionMismatch
    calls = []

    def answer(status):
        def fake(method, path, body, *, agent=None, location=None, role="agent"):
            calls.append((method, path, role))
            from memgate.adapters.hindsight.store import _Routing
            _Routing.raise_for(status, '{"detail": "x"}')
            return {}
        return fake
    mem = HindsightMemory(gate_offline, bank="ranch", base_url="http://shared")
    mem._call = answer(404)
    assert mem.check_version() == {"client": __import__("memgate").__version__, "servers": 1}
    assert calls == [("GET", "/v1/default/banks/ranch/stats", "admin")]            # a validated read, as admin
    mem._call = answer(426)
    with pytest.raises(VersionMismatch):
        mem.check_version()
    with pytest.raises(VersionMismatch):
        m2 = HindsightMemory.__new__(HindsightMemory)
        HindsightMemory.__init__(m2, gate_offline, bank="ranch", base_url="http://shared")
        m2._call = answer(426)
        m2.check_version()


def test_events_are_json_without_text(validator, capsys):
    ls = validator.gate.registry.register(personal_labels("ada"))
    ctx = RetainContext(bank_id=BANK, contents=[{"content": "the kiln code is EMBER-4471", "tags": [ls]}], request_context=rc("ada", "lab"))
    assert run(validator.validate_retain(ctx)).allowed
    run(validator.validate_recall(RecallContext(bank_id=BANK, query="what is the kiln code?", request_context=rc("ada", "lab"))))
    out = capsys.readouterr().out
    events = [json.loads(l) for l in out.splitlines() if l.startswith("{")]
    assert [e["event"] for e in events][-2:] == ["write", "recall"]
    assert "EMBER" not in out and "kiln" not in out


def test_retain_refuses_a_label_set_naming_a_location_the_world_no_longer_lists_for_every_role(validator, tmp_path):
    """0.8.2: with a location removed from the server's world, a write under a label set that names it is refused,
    the admin role included; routing such a write would otherwise skip the high-assurance partition rule."""
    import os
    from memgate.derivation import conversation_labels
    vault_set = conversation_labels("vault", ["ada", "bo"])
    assert retain(validator, f"{BANK}--ha--vault", vault_set, agent="ada", location="vault").allowed
    world = json.loads(open(os.environ["MEMGATE_WORLD"]).read())
    world["locations"] = [l for l in world["locations"] if l["id"] != "vault"]
    (tmp_path / "world.json").write_text(json.dumps(world))
    validator.gate.refresh(force=True)
    assert not retain(validator, BANK, vault_set, role="admin").allowed
    assert not retain(validator, BANK, vault_set, agent="ada", location="lab").allowed
