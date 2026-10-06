"""memgate's second lock inside Hindsight: an operation validator extension.

Load it in the Hindsight server with:

    HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=memgate.adapters.hindsight.validator:MemgateValidator
    HINDSIGHT_API_EXTENSION_PASSTHROUGH_HEADERS=x-memgate-agent,x-memgate-location,x-memgate-secret,x-memgate-role,x-memgate-version
    MEMGATE_WORLD=/path/world.json  MEMGATE_REGISTRY=/path/registry.sqlite  MEMGATE_SECRET=...

Only memgate holds the secret; agents never call Hindsight directly. Even so, the validator trusts
nothing but the caller's identity: it recomputes the allowed label sets itself and overwrites every
recall's tags with them, checks every retained item's label set (and that a reused write ID stays
within it), refuses the operations that read around the tag filter (reflect, mental models, raw
memory listing, export), empties the bank list for anyone but an admin, and refuses a client whose
release is newer than the server's (or older than `--min-client-version`) with status 426.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
import sys
import time

from hindsight_api.extensions.operation_validator import (
    BankListContext,
    BankListResult,
    BankReadContext,
    BankReadOperation,
    BankWriteContext,
    BankWriteOperation,
    ConsolidateContext,
    CreateBankContext,
    OperationValidatorExtension,
    RecallContext,
    ReflectContext,
    RetainContext,
    ValidationResult,
)

import os

from memgate import __version__
from memgate.context import (HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, HEADER_VERSION, Gate,
                             partition_location, serve_fingerprint)
from memgate.provenance import write_id_label_set

VERSION_REFUSED = "memgate version:"        # a version refusal: status 426, and the reason starts with this
ROLES = ("agent", "admin")                  # "internal" is Hindsight's own work and comes only from request_context.internal

log = logging.getLogger("memgate.validator")


def _event(event: str, **fields) -> None:
    """One structured line on stdout (JSON; ids, counts and reasons, never memory or query text)."""
    log.info(json.dumps({"event": event, "ts": round(time.time(), 3), **fields}, default=str))


class _StdoutHandler(logging.StreamHandler):
    """Writes to whatever sys.stdout is at emit time (uvicorn and test harnesses replace it)."""
    _memgate = True

    def __init__(self):
        super().__init__(sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value):
        pass


def install_event_log() -> None:
    """memgate's own JSON log on stdout, independent of Hindsight's level (memgate serve sets that to
    warning so Hindsight logs no memory text; memgate's lines never hold any)."""
    if not any(getattr(h, "_memgate", False) for h in log.handlers):
        h = _StdoutHandler()
        h.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False


def _release(v: str | None) -> tuple[int, int, int] | None:
    """A release string as (major, minor, patch), padded; None for anything that is not one. A pre-release
    suffix (0.6.0rc1, 0.6.0-dev) is dropped, so it compares as its release."""
    if not v:
        return None
    m = re.fullmatch(r"\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.+]?[A-Za-z].*)?\s*", v)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)

NO_MATCH = "ls_none"  # a tag no item carries: recall returns nothing

# Hindsight 0.10.1 logs the start of every recall query (`Query: '<text>...'`, `for query: <text>...`),
# at INFO and, when a recall fails, at ERROR. A query is conversation text, and the host contract makes
# logs labelled data, so the server never writes it: `memgate serve` sets Hindsight's level to WARNING,
# and this filter redacts the query from whatever is logged at any level.
_QUERY_PATTERNS = (
    (re.compile(r"Query: '.*?\.\.\.' \((?=budget=)", re.S), "Query: [redacted] ("),
    (re.compile(r"for query: .*?\.\.\.(?=, tags=|\n|$)", re.S), "for query: [redacted]"),
)


class RedactQueries(logging.Filter):
    """Removes recall query text from Hindsight's log records (installed by `MemgateValidator`)."""

    @staticmethod
    def redact(text: str) -> str:
        for pattern, repl in _QUERY_PATTERNS:
            text = pattern.sub(repl, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("hindsight_api"):
            message = record.getMessage()
            redacted = self.redact(message)
            if redacted != message:
                record.msg, record.args = redacted, ()
        return True


def install_log_redaction() -> None:
    """Put `RedactQueries` on the root logger and every handler it has, once. Filters on a logger apply
    only to records logged to it directly, and Hindsight's handler is on the root logger (its
    `configure_logging` runs before the validator loads), so the handlers are where it must sit."""
    targets = [logging.getLogger(), *logging.getLogger().handlers]
    for t in targets:
        if not any(isinstance(f, RedactQueries) for f in t.filters):
            t.addFilter(RedactQueries())

# Bank reads that don't return memory content.
SAFE_READS = {
    BankReadOperation.GET_OPERATION_STATUS, BankReadOperation.LIST_OPERATIONS,
    BankReadOperation.GET_BANK_PROFILE, BankReadOperation.GET_BANK_STATS,
}
# Bank writes that store nothing themselves: they only schedule work that is validated when it runs.
# Hindsight submits a consolidation right after every retain, with the writer's own request context, so
# an agent-role caller must be allowed this one or consolidation waits for Hindsight's reconcile sweep
# (every 5 minutes by default). The consolidation itself goes through validate_consolidate.
SCHEDULE_ONLY = {BankWriteOperation.SUBMIT_ASYNC_CONSOLIDATION}


def _headers(ctx) -> dict[str, str]:
    extra = getattr(ctx.request_context, "extra_headers", None) or {}
    return {k.lower(): v for k, v in extra.items()}


class _Version(PermissionError):
    """A version refusal: reported with status 426 so the client needs no body matching."""


def _refusal(e: PermissionError) -> ValidationResult:
    return ValidationResult.reject(str(e), status_code=426 if isinstance(e, _Version) else 403)


class MemgateValidator(OperationValidatorExtension):
    def __init__(self, config: dict | None = None):
        super().__init__(config or {})
        # Started by `memgate serve`: refuse to run if anything it forced was changed afterwards (Hindsight
        # applies a .env found from its working directory over the environment, before loading us). A
        # raise here stops Hindsight from starting at all, which is the safe outcome.
        keys = [k for k in os.environ.get("MEMGATE_SERVE_KEYS", "").split(",") if k]
        if keys and serve_fingerprint(dict(os.environ), keys) != os.environ.get("MEMGATE_SERVE_FINGERPRINT"):
            raise RuntimeError("the environment memgate serve set for Hindsight was changed after start "
                               "(a .env above Hindsight's working directory?); refusing to run")
        install_log_redaction()
        install_event_log()
        self.gate = Gate.from_env()
        # Which client versions this server accepts (MEMGATE_SERVE_MIN_CLIENT, set by `memgate serve
        # --min-client-version`): a client newer than the server is always refused (upgrade the server
        # first); one older than the minimum, or sending no version, is refused when a minimum is set.
        self.min_client = os.environ.get("MEMGATE_SERVE_MIN_CLIENT") or None
        if self.min_client and (_release(self.min_client) is None or _release(self.min_client) > _release(__version__)):
            raise ValueError(f"MEMGATE_SERVE_MIN_CLIENT must be a release no newer than this server ({__version__}), "
                             f"not {self.min_client!r}")
        # Which banks this server holds (MEMGATE_SERVE_SCOPE): "all" (default), "shared" (no high-assurance
        # partitions) or "partitions" (only them), so a split deployment can never land a memory on the
        # wrong server.
        self.scope = os.environ.get("MEMGATE_SERVE_SCOPE", "all")
        if self.scope not in ("all", "shared", "partitions"):
            raise ValueError(f"MEMGATE_SERVE_SCOPE must be all, shared or partitions, not {self.scope!r}")

    def _out_of_scope(self, bank_id: str) -> str | None:
        """Why this server may not touch `bank_id`, or None."""
        if self.scope == "all":
            return None
        is_partition = partition_location(bank_id, self.gate.world) is not None
        if self.scope == "shared" and is_partition:
            return "this server does not hold high-assurance partitions"
        if self.scope == "partitions" and not is_partition:
            return "this server holds only high-assurance partitions"
        return None

    # -- identity -------------------------------------------------------------------------------
    def _caller(self, ctx) -> tuple[str, str | None, str | None]:
        """Return (role, agent, location) for an authenticated caller, or raise PermissionError."""
        if getattr(ctx.request_context, "internal", False):
            return "internal", None, None           # Hindsight's own background work (consolidation)
        h = _headers(ctx)
        if not hmac.compare_digest(h.get(HEADER_SECRET, ""), self.gate.secret):
            _event("refused", op="auth", why="no or wrong secret")
            raise PermissionError("request did not come through memgate")
        client = (h.get(HEADER_VERSION) or "")[:32]
        release = _release(client)
        if release and release > _release(__version__):
            _event("refused", op="version", client=client, server=__version__, why="client newer than server")
            raise _Version(f"{VERSION_REFUSED} client {client} is newer than this server ({__version__}); "
                           "upgrade the server first")
        if self.min_client and (release is None or release < _release(self.min_client)):
            _event("refused", op="version", client=client or None, server=__version__, min=self.min_client,
                   why="client older than the server's minimum, or unversioned")
            raise _Version(f"{VERSION_REFUSED} client {client or 'unversioned'} is below this server's minimum "
                           f"({self.min_client}); upgrade the client (a stale worker?)")
        role = h.get(HEADER_ROLE, "agent")
        if role not in ROLES:
            _event("refused", op="auth", role=role[:32], why="unknown role")
            raise PermissionError("unknown role")
        return role, h.get(HEADER_AGENT), h.get(HEADER_LOCATION)

    # -- recall: overwrite the tag filter with what this context may read --------------------------
    async def validate_recall(self, ctx: RecallContext) -> ValidationResult:
        try:
            role, agent, location = self._caller(ctx)
        except PermissionError as e:
            return _refusal(e)
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        if role == "internal":
            return ValidationResult.accept()
        if not agent or not location:
            return ValidationResult.reject("recall needs an agent and a location")
        part = partition_location(ctx.bank_id, self.gate.world)
        if part is not None and part != location:
            return ValidationResult.reject("a high-assurance partition is searched only from inside it")
        allowed = sorted(self.gate.policy.allowed_ids(agent, location)) or [NO_MATCH]
        _event("recall", agent=agent, location=location, bank=ctx.bank_id, allowed=len(allowed) if allowed != [NO_MATCH] else 0)
        return ValidationResult.accept_with(tags=allowed, tags_match="any_strict", tag_groups=[])

    # -- retain: every item carries exactly one registered label set the writer may write ---------
    async def validate_retain(self, ctx: RetainContext) -> ValidationResult:
        try:
            role, agent, location = self._caller(ctx)
        except PermissionError as e:
            return _refusal(e)
        if role == "internal":
            return ValidationResult.accept()
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        known = self.gate.registry.all()
        part = partition_location(ctx.bank_id, self.gate.world)

        def refuse(why: str) -> ValidationResult:
            _event("refused", op="write", agent=agent, location=location, bank=ctx.bank_id, role=role, why=why)
            return ValidationResult.reject(why)
        for item in ctx.contents:
            tags = item.get("tags") or []
            if len(tags) != 1 or tags[0] not in known:
                return refuse("each item needs exactly one registered label-set tag")
            if item.get("observation_scopes") not in (None, "combined"):
                return refuse("observation scopes that widen beyond a label set are not allowed")
            # A document_id names the document this write replaces (Hindsight upserts by it), so it must
            # have been minted under this same label set; and an append would fold the existing document's
            # text into this write, re-extracting it under this write's label set.
            if item.get("update_mode") is not None:
                return refuse("update_mode is not allowed: it would fold another document into this write")
            if (doc := item.get("document_id")) is not None and write_id_label_set(doc) != tags[0]:
                return refuse("a write ID must carry the label set it is written under")
            ha = {l for l in known[tags[0]].locs if self.gate.world.high_assurance(l)}
            if (part is None and ha) or (part is not None and part not in ha):
                return refuse("memory stored in the wrong partition for its high-assurance label")
            if role != "admin":
                if not agent or not location:
                    return refuse("a write needs an agent and a location")
                if not self.gate.policy.may_write(agent, location, known[tags[0]]):
                    return refuse("writer may not write this label set here")
        _event("write", agent=agent, location=location, bank=ctx.bank_id, role=role, items=len(ctx.contents),
               label_sets=sorted({(i.get("tags") or [""])[0] for i in ctx.contents}))
        return ValidationResult.accept()

    # -- everything that reads around the tag filter -------------------------------------------
    async def validate_reflect(self, ctx: ReflectContext) -> ValidationResult:
        return ValidationResult.reject("reflect is disabled: its tag scope cannot be enforced")

    async def validate_consolidate(self, ctx: ConsolidateContext) -> ValidationResult:
        return ValidationResult.accept()  # observations use the default "combined" scope: one label set

    async def validate_mental_model_get(self, ctx) -> ValidationResult:
        return ValidationResult.reject("mental models blend a whole bank")

    async def validate_mental_model_refresh(self, ctx) -> ValidationResult:
        return ValidationResult.reject("mental models blend a whole bank")

    async def validate_bank_read(self, ctx: BankReadContext) -> ValidationResult:
        try:
            role, _, _ = self._caller(ctx)
        except PermissionError as e:
            return _refusal(e)
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        if role in ("internal", "admin") or ctx.operation in SAFE_READS:
            return ValidationResult.accept()
        return ValidationResult.reject(f"{ctx.operation} reads memory around the label filter")

    async def validate_create_bank(self, ctx: CreateBankContext) -> ValidationResult:
        try:
            role, _, _ = self._caller(ctx)
        except PermissionError as e:
            return _refusal(e)
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        return ValidationResult.accept() if role in ("internal", "admin") else ValidationResult.reject("admin only")

    async def validate_bank_write(self, ctx: BankWriteContext) -> ValidationResult:
        try:
            role, _, location = self._caller(ctx)
        except PermissionError as e:
            return _refusal(e)
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        if role in ("internal", "admin"):
            return ValidationResult.accept()
        if ctx.operation in SCHEDULE_ONLY:
            # Hindsight's own post-write trigger carries the writer's location; a partition may be scheduled
            # only from inside its location, so nothing outside can even prod a sealed partition.
            part = partition_location(ctx.bank_id, self.gate.world)
            if part is None or part == location:
                return ValidationResult.accept()
            return ValidationResult.reject("a high-assurance partition is consolidated only from inside it")
        return ValidationResult.reject("admin only")

    async def filter_bank_list(self, ctx: BankListContext) -> BankListResult:
        """The bank list (GET /v1/default/banks) has no gate in Hindsight, only this filter: bank names embed
        high-assurance locations and the counts say how much each holds, so only an admin with the secret
        sees any of it. A filter cannot refuse, so everyone else gets an empty list."""
        try:
            role, _, _ = self._caller(ctx)
        except PermissionError:
            return BankListResult(banks=[])
        return BankListResult(banks=ctx.banks if role in ("internal", "admin") else [])
