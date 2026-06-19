# Semantic Layer (E) vs Text-to-SQL (B) — consistency validation

Same governed KPIs, paraphrased N ways x M samples; gold = canonical ontology metric. **Drift** = fraction of runs whose answer != the governed gold (lower is better; the semantic layer should be ~0 by construction).

Reason model: `deepseek-v4-flash:cloud`. Scope: governed-metric regime only.

## Verdict: **INCONCLUSIVE**

| engine | runs | drift_rate | valid | latency_s |
|---|--:|--:|--:|--:|
| B (text-to-SQL) | 168 | 0.173 | 1.0 | 9.83 |
| E (semantic layer) | 168 | 0.0 | 1.0 | 7.41 |

## Drift by metric

| metric | B | E |
|---|--:|--:|
| aum | 0.042 | 0.0 |
| churn_risk | 0.417 | 0.0 |
| days_since_contact | 0.25 | 0.0 |
| net_new_money | 0.042 | 0.0 |
| share_of_wallet | 0.0 | 0.0 |

## Coverage cost (probe set: metric-sounding but NOT governed)
E does NOT cleanly refuse ungoverned questions — it either abstains or **mis-routes**:
- E abstains cleanly on 25% of probe runs.
- E **mis-routes** on 75% of probe runs: it silently picks a nearby governed metric (here: aum, churn_risk, days_since_contact, net_new_money, share_of_wallet) and answers the wrong question. This is a worse failure than a refusal — the RM gets a confident, wrong-metric answer with no signal it's off.
- B attempts 100% of probes (free SQL is unconstrained; it answers the actual question rather than substituting a governed metric).

_Verdict rule: justified iff B drift >= 0.2 and (B-E) drift >= 0.15; not_justified iff B drift <= 0.1 or (B-E) <= 0.05; else inconclusive._