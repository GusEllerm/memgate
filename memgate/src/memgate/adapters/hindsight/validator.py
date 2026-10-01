"""memgate's second lock inside Hindsight: an operation validator extension.

Load it in the Hindsight server with:

    HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=memgate.adapters.hindsight.validator:MemgateValidator
    HINDSIGHT_API_EXTENSION_PASSTHROUGH_HEADERS=x-memgate-agent,x-memgate-location,x-memgate-secret,x-memgate-role
    MEMGATE_WORLD=/path/world.json  MEMGATE_REGISTRY=/path/registry.sqlite  MEMGATE_SECRET=...

Only memgate holds the secret; agents never call Hindsight directly. Even so, the validator trusts
nothing but the caller's identity: it recomputes the allowed label sets itself and overwrites every
recall's tags with them, checks every retained item's label set (and that a reused write ID stays
within it), and refuses the operations that read around the tag filter (reflect, mental models, raw
memory listing, export).
"""

from __future__ import annotations

import hmac
import logging
import re

from hindsight_api.extensions.operation_validator import (
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

from memgate.context import (HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, Gate, partition_location,
                             serve_fingerprint)
from memgate.provenance import write_id_label_set

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


def _headers(ctx) -> dict[str, str]:
    extra = getattr(ctx.request_context, "extra_headers", None) or {}
    return {k.lower(): v for k, v in extra.items()}


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
        self.gate = Gate.from_env()
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
            raise PermissionError("request did not come through memgate")
        role = h.get(HEADER_ROLE, "agent")
        return role, h.get(HEADER_AGENT), h.get(HEADER_LOCATION)

    # -- recall: overwrite the tag filter with what this context may read --------------------------
    async def validate_recall(self, ctx: RecallContext) -> ValidationResult:
        try:
            role, agent, location = self._caller(ctx)
        except PermissionError as e:
            return ValidationResult.reject(str(e))
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
        return ValidationResult.accept_with(tags=allowed, tags_match="any_strict", tag_groups=[])

    # -- retain: every item carries exactly one registered label set the writer may write ---------
    async def validate_retain(self, ctx: RetainContext) -> ValidationResult:
        try:
            role, agent, location = self._caller(ctx)
        except PermissionError as e:
            return ValidationResult.reject(str(e))
        if role == "internal":
            return ValidationResult.accept()
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        known = self.gate.registry.all()
        part = partition_location(ctx.bank_id, self.gate.world)
        for item in ctx.contents:
            tags = item.get("tags") or []
            if len(tags) != 1 or tags[0] not in known:
                return ValidationResult.reject("each item needs exactly one registered label-set tag")
            if item.get("observation_scopes") not in (None, "combined"):
                return ValidationResult.reject("observation scopes that widen beyond a label set are not allowed")
            # A document_id names the document this write replaces (Hindsight upserts by it), so it must
            # have been minted under this same label set; and an append would fold the existing document's
            # text into this write, re-extracting it under this write's label set.
            if item.get("update_mode") is not None:
                return ValidationResult.reject("update_mode is not allowed: it would fold another document into this write")
            if (doc := item.get("document_id")) is not None and write_id_label_set(doc) != tags[0]:
                return ValidationResult.reject("a write ID must carry the label set it is written under")
            ha = {l for l in known[tags[0]].locs if self.gate.world.high_assurance(l)}
            if (part is None and ha) or (part is not None and part not in ha):
                return ValidationResult.reject("memory stored in the wrong partition for its high-assurance label")
            if role != "admin":
                if not agent or not location:
                    return ValidationResult.reject("a write needs an agent and a location")
                if not self.gate.policy.may_write(agent, location, known[tags[0]]):
                    return ValidationResult.reject("writer may not write this label set here")
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
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        try:
            role, _, _ = self._caller(ctx)
        except PermissionError as e:
            return ValidationResult.reject(str(e))
        if role in ("internal", "admin") or ctx.operation in SAFE_READS:
            return ValidationResult.accept()
        return ValidationResult.reject(f"{ctx.operation} reads memory around the label filter")

    async def validate_create_bank(self, ctx: CreateBankContext) -> ValidationResult:
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        try:
            role, _, _ = self._caller(ctx)
        except PermissionError as e:
            return ValidationResult.reject(str(e))
        return ValidationResult.accept() if role in ("internal", "admin") else ValidationResult.reject("admin only")

    async def validate_bank_write(self, ctx: BankWriteContext) -> ValidationResult:
        if (why := self._out_of_scope(ctx.bank_id)):
            return ValidationResult.reject(why)
        try:
            role, _, _ = self._caller(ctx)
        except PermissionError as e:
            return ValidationResult.reject(str(e))
        return ValidationResult.accept() if role in ("internal", "admin") else ValidationResult.reject("admin only")
