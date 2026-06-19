"""Score each representation on the structural axes (spec §5) and apply the pre-registered
recommendation rule (spec §6). Mechanical, not editorial."""
from __future__ import annotations

_COMPOSITES = ("share_of_wallet", "churn_risk")
_VERBOSITY_BUDGET = 1.5


def axis_scores(repr_name: str, equivalence: dict, composition: dict, *, queryable: str,
                verbosity_lines: int, baseline_lines: int, generates_sql: bool) -> dict:
    native = sum(1 for c in _COMPOSITES if composition.get(c) == "native")
    return {
        "repr": repr_name,
        "equivalence_all": all(equivalence.values()),
        "native_composites": native,
        "queryable": queryable,
        "verbosity_lines": verbosity_lines,
        "verbosity_ratio": round(verbosity_lines / baseline_lines, 2) if baseline_lines else 0.0,
        "dialect": "generates" if generates_sql else "locked",
        "composition": composition,
    }


def verdict(scores: dict) -> str:
    """migrate iff equivalence passes AND >=1 native composite AND full catalog AND within budget."""
    if (scores["equivalence_all"] and scores["native_composites"] >= 1
            and scores["queryable"] == "yes" and scores["verbosity_ratio"] <= _VERBOSITY_BUDGET):
        return "migrate"
    return "keep"


def to_markdown(rows: list[dict], baseline_lines: int) -> str:
    L = ["# Semantic-Layer Storage Representation — structural comparison (Phase 3b)", "",
         "The 5 governed metrics ported to two representations vs the YAML+hand-SQL baseline. "
         "Equivalence is a hard gate (compiled SQL must reproduce the canonical numbers). "
         "Composition is measured on the 2 composite metrics (`share_of_wallet`, `churn_risk`).", "",
         f"Baseline metric-definition lines: **{baseline_lines}**. "
         f"Verbosity budget for 'migrate': <= {_VERBOSITY_BUDGET}x baseline.", "",
         "| repr | equivalence | native composites (/2) | catalog | verbosity (lines / xbase) | dialect | verdict |",
         "|---|--:|--:|---|--:|---|---|"]
    for r in rows:
        eq = "all pass" if r["equivalence_all"] else "FAIL"
        L.append(f"| {r['repr']} | {eq} | {r['native_composites']} | {r['queryable']} | "
                 f"{r['verbosity_lines']} / {r['verbosity_ratio']}x | {r['dialect']} | "
                 f"**{verdict(r)}** |")
    L += ["", "## Composition by metric (the 2 composites)", "", "| repr | share_of_wallet | churn_risk |",
          "|---|---|---|"]
    for r in rows:
        c = r["composition"]
        L.append(f"| {r['repr']} | {c.get('share_of_wallet', '-')} | {c.get('churn_risk', '-')} |")
    L += ["", "_Verdict rule (spec §6): migrate iff equivalence all-pass AND >=1 composite expressed "
          "natively (not the baseline's `{{ref}}` string-substitution) AND catalog queryable AND "
          "verbosity <= 1.5x baseline; else keep. Hybrid outcomes are noted in prose._"]
    return "\n".join(L)
