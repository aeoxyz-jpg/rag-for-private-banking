"""Aggregate semx records: per-engine DRIFT (fraction of governed runs whose answer != canonical
gold) is the headline; plus coverage from the probe set; plus a pre-registered verdict on whether
the semantic layer (E) earns its keep. Mechanical, not editorial (spec §7)."""
from __future__ import annotations

from ..eval.metrics import mean


def _governed(records):
    return [r for r in records if r["gold_kind"] != "probe"]


def aggregate(records: list[dict]) -> dict:
    out = {}
    gov = _governed(records)
    for e in ("B", "E"):
        er = [r for r in gov if r["engine"] == e]
        out[e] = {
            "n": len(er),
            "drift_rate": round(mean([0.0 if r["correct"] else 1.0 for r in er]), 3) if er else 0.0,
            "valid_rate": round(mean([1.0 if r["valid"] else 0.0 for r in er]), 3) if er else 0.0,
            "latency_s": round(mean([r["latency_s"] for r in er]), 2) if er else 0.0,
            "by_metric": {},
        }
        for m in sorted({r["metric"] for r in er}):
            mr = [r for r in er if r["metric"] == m]
            out[e]["by_metric"][m] = round(mean([0.0 if r["correct"] else 1.0 for r in mr]), 3)
    return out


def coverage(records: list[dict]) -> dict:
    """E's coverage cost on the probe set (metric-sounding but NOT governed). E does NOT cleanly
    refuse: it either abstains (no governed metric matched) or MIS-ROUTES — silently picks a nearby
    governed metric and answers the wrong question. Mis-route is the honest, worse failure mode."""
    probes = [r for r in records if r["gold_kind"] == "probe"]
    e = [r for r in probes if r["engine"] == "E"]
    b = [r for r in probes if r["engine"] == "B"]
    misrouted = [r for r in e if not r["abstain"] and r.get("valid")]
    return {
        "E_abstain_rate": round(mean([1.0 if r["abstain"] else 0.0 for r in e]), 3) if e else 0.0,
        "E_misroute_rate": round(len(misrouted) / len(e), 3) if e else 0.0,
        "E_misroute_metrics": sorted({r["chosen_metric"] for r in misrouted if r.get("chosen_metric")}),
        "B_attempt_rate": round(mean([1.0 if r["valid"] else 0.0 for r in b]), 3) if b else 0.0,
    }


def verdict(agg: dict) -> str:
    """E justified iff free SQL drifts materially while the governed layer does not (spec §7)."""
    b, e = agg["B"]["drift_rate"], agg["E"]["drift_rate"]
    if b >= 0.2 and (b - e) >= 0.15:
        return "justified"
    if b <= 0.1 or (b - e) <= 0.05:
        return "not_justified"
    return "inconclusive"


def to_markdown(agg: dict, cov: dict, model: str) -> str:
    v = verdict(agg)
    L = ["# Semantic Layer (E) vs Text-to-SQL (B) — consistency validation", "",
         "Same governed KPIs, paraphrased N ways x M samples; gold = canonical ontology metric. "
         "**Drift** = fraction of runs whose answer != the governed gold (lower is better; the "
         "semantic layer should be ~0 by construction).", "",
         f"Reason model: `{model}`. Scope: governed-metric regime only.", "",
         f"## Verdict: **{v.replace('_', ' ').upper()}**", "",
         "| engine | runs | drift_rate | valid | latency_s |",
         "|---|--:|--:|--:|--:|",
         f"| B (text-to-SQL) | {agg['B']['n']} | {agg['B']['drift_rate']} | {agg['B']['valid_rate']} | {agg['B']['latency_s']} |",
         f"| E (semantic layer) | {agg['E']['n']} | {agg['E']['drift_rate']} | {agg['E']['valid_rate']} | {agg['E']['latency_s']} |",
         "", "## Drift by metric", "", "| metric | B | E |", "|---|--:|--:|"]
    for m in sorted(set(agg["B"]["by_metric"]) | set(agg["E"]["by_metric"])):
        L.append(f"| {m} | {agg['B']['by_metric'].get(m, '-')} | {agg['E']['by_metric'].get(m, '-')} |")
    misroute_to = ", ".join(cov["E_misroute_metrics"]) or "—"
    L += ["", "## Coverage cost (probe set: metric-sounding but NOT governed)",
          "E does NOT cleanly refuse ungoverned questions — it either abstains or **mis-routes**:",
          f"- E abstains cleanly on {cov['E_abstain_rate']:.0%} of probe runs.",
          f"- E **mis-routes** on {cov['E_misroute_rate']:.0%} of probe runs: it silently picks a nearby "
          f"governed metric (here: {misroute_to}) and answers the wrong question. This is a worse "
          "failure than a refusal — the RM gets a confident, wrong-metric answer with no signal it's off.",
          f"- B attempts {cov['B_attempt_rate']:.0%} of probes (free SQL is unconstrained; it answers the "
          "actual question rather than substituting a governed metric).", "",
          "_Verdict rule: justified iff B drift >= 0.2 and (B-E) drift >= 0.15; "
          "not_justified iff B drift <= 0.1 or (B-E) <= 0.05; else inconclusive._"]
    return "\n".join(L)
