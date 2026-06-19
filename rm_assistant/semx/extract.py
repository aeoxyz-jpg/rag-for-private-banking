"""Normalize an engine's result rows to a comparable answer. Set questions -> frozenset of ids
(first column). Count questions -> the aggregate if the engine returned a single numeric cell,
else the number of returned rows (the engine returned the matching client rows). This makes B
(which may SELECT COUNT(*) or list rows) and E (which returns per-client rows) comparable."""
from __future__ import annotations


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def extract(rows: list, gold_kind: str):
    if gold_kind == "set":
        return frozenset(str(r[0]) for r in rows if r)
    if gold_kind == "count":
        if len(rows) == 1 and rows[0] and _num(rows[0][0]) is not None:
            return int(round(_num(rows[0][0])))
        # ASSUMPTION: a count answered by LISTING rows must not exceed the engine's row cap
        # (sql_pillar caps at 200). All count golds here are answered via COUNT(*); a gold > 200
        # answered by listing would be under-counted at the cap and falsely scored as drift.
        return len(rows)
    return None
