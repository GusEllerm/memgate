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
    for op in BankWriteOperation:
        assert not run(validator.validate_bank_write(BankWriteContext(BANK, op, rc("ada", "lab")))).allowed
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
