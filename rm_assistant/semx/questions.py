"""Generate the paraphrase question set with canonical gold. Each variant is a governed metric +
threshold; gold is computed once from ontology.metric_sql (the single governed definition). Every
gold query returns client_ids, so count = set size — making extraction unambiguous for both engines."""
from __future__ import annotations

from dataclasses import dataclass

from .. import config, db, ontology

# (metric, variant_id, predicate over the metric's value column, human label, gold_kind)
VARIANTS = [
    ("aum", "aum_gt_1m", "aum > 1000000", "AUM over 1,000,000", "count"),
    ("aum", "aum_gt_2m", "aum > 2000000", "AUM over 2,000,000", "set"),
    ("days_since_contact", "dsc_gt_180", "days_since_contact > 180",
     "more than 180 days since last contact", "count"),
    ("net_new_money", "nnm_lt_0", "net_new_money < 0", "negative net new money", "count"),
    ("share_of_wallet", "sow_lt_05", "share_of_wallet < 0.5", "share of wallet below 0.5", "count"),
    ("churn_risk", "churn_gt_05", "churn_risk > 0.5", "churn risk above 0.5", "count"),
    ("churn_risk", "churn_gt_07", "churn_risk > 0.7", "churn risk above 0.7", "set"),
]

_COUNT_PHRASINGS = [
    "How many clients have {label}?",
    "Count the clients with {label}.",
    "What is the number of clients with {label}?",
    "How many of my clients have {label}?",
    "Give me the count of clients where there is {label}.",
    "Tally the clients that have {label}.",
]
_SET_PHRASINGS = [
    "Which clients have {label}?",
    "List the clients with {label}.",
    "Show me the clients that have {label}.",
    "Who are the clients with {label}?",
    "Identify clients with {label}.",
    "Return the client ids with {label}.",
]

# metric-sounding questions that are NOT governed metrics -> E should abstain (coverage cost)
PROBES = [
    "What is the average loan interest rate by loan status?",
    "What is the median account balance?",
    "How many credit cards does each client hold?",
    "What is the total transaction volume per channel?",
    "Which districts have the highest average client tenure?",
]


@dataclass(frozen=True)
class MetricQ:
    id: str
    metric: str
    variant: str
    question: str
    gold: object        # int (count) | frozenset[str] (set) | None (probe)
    gold_kind: str      # "count" | "set" | "probe"


def _gold(conn, metric: str, predicate: str, gold_kind: str):
    base = ontology.metric_sql(metric)
    sql = f"SELECT client_id FROM (\n{base}\n) WHERE {predicate}"
    ids = [str(r[0]) for r in conn.execute(sql, ontology.metric_binds(sql)).fetchall()]
    return len(ids) if gold_kind == "count" else frozenset(ids)


def generate(n_paraphrases: int = config.SEMX_PARAPHRASES) -> list[MetricQ]:
    conn = db.connect(readonly=True)
    out: list[MetricQ] = []
    try:
        for metric, variant, predicate, label, kind in VARIANTS:
            gold = _gold(conn, metric, predicate, kind)
            phrasings = (_COUNT_PHRASINGS if kind == "count" else _SET_PHRASINGS)[:n_paraphrases]
            for i, p in enumerate(phrasings):
                out.append(MetricQ(f"{variant}-{i}", metric, variant,
                                   p.format(label=label), gold, kind))
    finally:
        conn.close()
    for i, p in enumerate(PROBES):
        out.append(MetricQ(f"probe-{i}", "(none)", "probe", p, None, "probe"))
    return out
