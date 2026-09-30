"""memgate's second lock inside Hindsight: an operation validator extension.

Load it in the Hindsight server with:

    HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=memgate.adapters.hindsight.validator:MemgateValidator
    HINDSIGHT_API_EXTENSION_PASSTHROUGH_HEADERS=x-memgate-agent,x-memgate-location,x-memgate-secret,x-memgate-role
    MEMGATE_WORLD=/path/world.json  MEMGATE_REGISTRY=/path/registry.sqlite  MEMGATE_SECRET=...

Only memgate holds the secret; agents never call Hindsight directly. Even so, the validator trusts
nothing but the caller's identity: it recomputes the allowed label sets itself and overwrites every
recall's tags with them, checks every retained item's label set, and refuses the operations that
read around the tag filter (reflect, mental models, raw memory listing, export).
"""

from __future__ import annotations

import hmac

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

from memgate.context import HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, Gate, partition_location

NO_MATCH = "ls_none"  # a tag no item carries: recall returns nothing

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
