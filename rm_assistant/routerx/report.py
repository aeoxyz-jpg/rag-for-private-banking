"""Aggregate routerx records into a routing confusion matrix + per-route precision/recall +
overall accuracy. Mechanical, not editorial (spec §7)."""
from __future__ import annotations

from ..retrieval.router import ROUTES


def aggregate(records: list[dict]) -> dict:
    n = len(records)
    correct = sum(1 for r in records if r["expected_route"] == r["predicted_route"])
    confusion = {e: {p: 0 for p in ROUTES} for e in ROUTES}
    for r in records:
        confusion[r["expected_route"]][r["predicted_route"]] += 1
    per_route = {}
    for route in ROUTES:
        tp = confusion[route][route]
        fn = sum(confusion[route][p] for p in ROUTES) - tp
        fp = sum(confusion[e][route] for e in ROUTES) - tp
        per_route[route] = {
            "support": tp + fn,
            "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
            "recall": round(tp / (tp + fn), 3) if (tp + fn) else None,
        }
    return {"n": n, "accuracy": round(correct / n, 3) if n else 0.0,
            "confusion": confusion, "per_route": per_route,
            "errors": [r for r in records if r["expected_route"] != r["predicted_route"]]}


def to_markdown(agg: dict, model: str) -> str:
    present = [r for r in ROUTES if agg["per_route"][r]["support"]]
    L = ["# Routing accuracy — pillar F (router) validation", "",
         f"Classifier: `{model}`. `router.classify()` over the hand-labeled routing gold "
         f"(incl. Q4/Q7 and deliberate E↔B boundary cases). **Accuracy: "
         f"{agg['accuracy']:.0%}** (n={agg['n']}).", "",
         "## Confusion matrix (rows = expected, cols = predicted)", "",
         "| expected \\\\ predicted | " + " | ".join(present) + " |",
         "|---" * (len(present) + 1) + "|"]
    for e in present:
        L.append(f"| {e} | " + " | ".join(str(agg["confusion"][e][p]) for p in present) + " |")
    L += ["", "## Per-route precision / recall", "",
          "| route | support | precision | recall |", "|---|--:|--:|--:|"]
    def _cell(v):
        return "-" if v is None else v
    for r in present:
        pr = agg["per_route"][r]
        L.append(f"| {r} | {pr['support']} | {_cell(pr['precision'])} | {_cell(pr['recall'])} |")
    if agg["errors"]:
        L += ["", "## Misroutes", "", "| id | expected | predicted |", "|---|---|---|"]
        L += [f"| {e['id']} | {e['expected_route']} | {e['predicted_route']} |" for e in agg["errors"]]
    return "\n".join(L)
