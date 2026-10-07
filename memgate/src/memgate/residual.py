"""Compile Cedar residual policies into a SQL filter over the label-set registry.

Cedar evaluates the policies with the agent and location known and the label set left unknown. What
remains of each policy (its residual) is a condition on the unknown label set's attributes. This
module turns those residuals into one SQL WHERE clause, so the database picks the readable label
sets instead of Cedar checking every one.

Truth literals are TRUE/FALSE, which SQLite (3.23+) and PostgreSQL both accept. Only the constructs our policies produce are compiled: && || ! true/false, containsAll, contains,
containsAny and isEmpty over the label set's attributes and literal sets of entities. Anything else
raises Unsupported, and the caller falls back to checking each label set with Cedar, so an
unfamiliar policy makes recall slower but never wrong. tests/test_residual.py checks the compiled
filter against Cedar on random worlds.

Cedar's decision rule: allowed if some permit holds and no forbid holds.
"""

from __future__ import annotations

from dataclasses import dataclass

from memgate.world import World


class Unsupported(ValueError):
    """The residual uses a construct the compiler doesn't handle; use Cedar directly."""


@dataclass(frozen=True)
class AttrSet:
    """A set-valued attribute of the unknown label set, as rows of the `label` table."""
    kind: str
    only: tuple[str, ...] | None = None   # restrict to these values (e.g. the high-assurance locations)

    def rows(self, extra: str = "") -> tuple[str, list]:
        sql = "SELECT 1 FROM label l WHERE l.label_set = ls.id AND l.kind = ?"
        params: list = [self.kind]
        if self.only is not None:
            if not self.only:
                # Matches nothing, but keeps `extra` so its placeholders still line up with the caller's params.
                return "SELECT 1 FROM label l WHERE FALSE" + extra, []
            sql += f" AND l.value IN ({','.join('?' * len(self.only))})"
            params += list(self.only)
        return sql + extra, params


class Compiler:
    def __init__(self, world: World):
        ha = tuple(sorted(l.id for l in world.locations.values() if l.high_assurance))
        sealed = tuple(sorted(l for l in world.locations if world.sealed(l)))
        self.attrs = {"selfs": AttrSet("self"), "locs": AttrSet("loc"), "withs": AttrSet("with"),
                      "haLocs": AttrSet("loc", ha), "srcs": AttrSet("src"), "sealedSrcs": AttrSet("src", sealed)}

    # -- operands ------------------------------------------------------------------------------------
    def _attr(self, node) -> AttrSet | None:
        if isinstance(node, dict) and "." in node:
            dot = node["."]
            if dot.get("left") == {"unknown": [{"Value": "resource"}]}:
                if dot["attr"] not in self.attrs:
                    raise Unsupported(f"attribute {dot['attr']!r}")
                return self.attrs[dot["attr"]]
        return None

    @staticmethod
    def _literal(node) -> list[str] | None:
        """A literal entity, or set of entities, as a list of ids."""
        if isinstance(node, dict) and "Value" in node:
            v = node["Value"]
            if isinstance(v, dict) and "__entity" in v:
                return [v["__entity"]["id"]]
            if isinstance(v, list) and all(isinstance(x, dict) and "__entity" in x for x in v):
                return [x["__entity"]["id"] for x in v]
        if isinstance(node, dict) and "Set" in node:
            out = []
            for item in node["Set"]:
                lit = Compiler._literal(item)
                if lit is None or len(lit) != 1:
                    return None
                out += lit
            return out
        return None

    # -- expressions -------------------------------------------------------------------------------
    def expr(self, node) -> tuple[str, list]:
        if not isinstance(node, dict) or len(node) != 1:
            raise Unsupported(str(node)[:80])
        (op, body), = node.items()
        if op == "Value" and isinstance(body, bool):
            return ("TRUE" if body else "FALSE"), []
        if op in ("&&", "||"):
            a, pa = self.expr(body["left"])
            b, pb = self.expr(body["right"])
            return f"({a} {'AND' if op == '&&' else 'OR'} {b})", pa + pb
        if op == "!":
            a, pa = self.expr(body["arg"])
            return f"(NOT {a})", pa
        if op == "isEmpty":
            attr = self._attr(body["arg"])
            if attr is None:
                raise Unsupported("isEmpty on a non-attribute")
            rows, p = attr.rows()
            return f"(NOT EXISTS ({rows}))", p
        if op in ("containsAll", "contains", "containsAny"):
            left, right = body["left"], body["right"]
            la, ra = self._attr(left), self._attr(right)
            ll, rl = self._literal(left), self._literal(right)
            if op == "containsAll" and ll is not None and ra is not None:      # attribute ⊆ literal
                if not ll:
                    rows, p = ra.rows()
                    return f"(NOT EXISTS ({rows}))", p
                rows, p = ra.rows(f" AND l.value NOT IN ({','.join('?' * len(ll))})")
                return f"(NOT EXISTS ({rows}))", p + ll
            if op == "containsAll" and la is not None and rl is not None:      # literal ⊆ attribute
                parts, params = [], []
                for v in rl:
                    rows, p = la.rows(" AND l.value = ?")
                    parts.append(f"EXISTS ({rows})")
                    params += p + [v]
                return ("(" + " AND ".join(parts) + ")" if parts else "TRUE"), params
            if op == "contains" and la is not None and rl is not None and len(rl) == 1:
                rows, p = la.rows(" AND l.value = ?")
                return f"(EXISTS ({rows}))", p + rl
            if op == "containsAny" and ((la is not None and rl is not None) or (ra is not None and ll is not None)):
                attr, lit = (la, rl) if la is not None else (ra, ll)
                if not lit:
                    return "FALSE", []
                rows, p = attr.rows(f" AND l.value IN ({','.join('?' * len(lit))})")
                return f"(EXISTS ({rows}))", p + lit
            raise Unsupported(f"{op} with these operands")
        raise Unsupported(f"operator {op!r}")

    # -- policies ----------------------------------------------------------------------------------
    def policy(self, residual: dict) -> tuple[str, list]:
        for part in ("principal", "action", "resource"):
            if residual.get(part, {}).get("op") != "All":
                raise Unsupported(f"{part} scope in a residual")
        clauses, params = [], []
        for cond in residual.get("conditions", []):
            sql, p = self.expr(cond["body"])
            clauses.append(sql if cond["kind"] == "when" else f"(NOT {sql})")
            params += p
        return ("(" + " AND ".join(clauses) + ")" if clauses else "TRUE"), params

    def where(self, residuals: dict[str, dict]) -> tuple[str, list]:
        """One WHERE clause for the label sets allowed by a set of residual policies."""
        permits, forbids, params_p, params_f = [], [], [], []
        for r in residuals.values():
            sql, p = self.policy(r)
            if r["effect"] == "permit":
                permits.append(sql)
                params_p += p
            else:
                forbids.append(sql)
                params_f += p
        if not permits:
            return "FALSE", []
        where = "(" + " OR ".join(permits) + ")"
        if forbids:
            where += " AND NOT (" + " OR ".join(forbids) + ")"
        return where, params_p + params_f
