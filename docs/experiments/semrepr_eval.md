# Semantic-Layer Storage Representation — structural comparison (Phase 3b)

The 5 governed metrics ported to two representations vs the YAML+hand-SQL baseline. Equivalence is a hard gate (compiled SQL must reproduce the canonical numbers). Composition is measured on the 2 composite metrics (`share_of_wallet`, `churn_risk`).

Baseline metric-definition lines: **43**. Verbosity budget for 'migrate': <= 1.5x baseline.

| repr | equivalence | native composites (/2) | catalog | verbosity (lines / xbase) | dialect | verdict |
|---|--:|--:|---|--:|---|---|
| baseline (YAML+SQL) | all pass | 0 | yes | 43 / 1.0x | locked | **keep** |
| dbt-style | all pass | 1 | yes | 54 / 1.26x | generates | **migrate** |
| rdf | all pass | 0 | yes | 48 / 1.12x | locked | **keep** |

## Composition by metric (the 2 composites)

| repr | share_of_wallet | churn_risk |
|---|---|---|
| baseline (YAML+SQL) | string-substitution | string-substitution |
| dbt-style | native | escape |
| rdf | native-edge | native-edge |

_Verdict rule (spec §6): migrate iff equivalence all-pass AND >=1 composite expressed natively (not the baseline's `{{ref}}` string-substitution) AND catalog queryable AND verbosity <= 1.5x baseline; else keep. Hybrid outcomes are noted in prose._