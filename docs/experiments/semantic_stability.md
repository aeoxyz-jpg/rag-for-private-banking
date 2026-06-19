# Phase-3a stability pass — B drift distribution over independent runs

The pre-registered verdict (justified iff B drift ≥ 0.2 ∧ B−E ≥ 0.15) is a binary cut on B's drift. A single run is not enough to trust it: this pass re-runs the whole B-vs-E eval N times and reports the run-to-run distribution.

## B drift over 5 runs: mean **0.2**, range [0.185, 0.214], stdev **0.009**

Verdict split: {'justified': 3, 'inconclusive': 2} — the 0.2 threshold sits at B's central tendency, so the label is dominated by run noise. The **magnitude** (~0.2) is the result, not the binary.

| run | B drift | verdict | E mis-route |
|--:|--:|---|--:|
| 0 | 0.202 | justified | 0.9 |
| 1 | 0.214 | justified | 0.85 |
| 2 | 0.202 | justified | 0.8 |
| 3 | 0.196 | inconclusive | 0.7 |
| 4 | 0.185 | inconclusive | 0.65 |

## B drift by metric (per run)

| metric | run 0 | run 1 | run 2 | run 3 | run 4 |
|---|---|---|---|---|---|
| aum | 0.0 | 0.0 | 0.0 | 0.021 | 0.021 |
| net_new_money | 0.125 | 0.042 | 0.125 | 0.042 | 0.125 |
| share_of_wallet | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| days_since_contact | 0.417 | 0.542 | 0.667 | 0.292 | 0.542 |
| churn_risk | 0.438 | 0.458 | 0.312 | 0.5 | 0.292 |