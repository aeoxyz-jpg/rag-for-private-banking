"""Phase-3a: B-vs-E consistency validation. Prereq: data/rm.db built + corpus synthesized.
Run: `uv run scripts/eval/run_semantic_eval.py`  (env: RM_SEMX_PARAPHRASES, RM_SEMX_SAMPLES)."""
import json
from pathlib import Path

from rm_assistant import config
from rm_assistant.semx import questions, report, runner


def main() -> None:
    qs = questions.generate()
    print(f"{len(qs)} questions ({sum(q.gold_kind!='probe' for q in qs)} governed, "
          f"{sum(q.gold_kind=='probe' for q in qs)} probes), samples={config.SEMX_SAMPLES}")
    recs = runner.run(qs)
    agg = report.aggregate(recs)
    cov = report.coverage(recs)
    Path(config.SEMX_RECORDS).write_text(json.dumps(recs, indent=1, default=str))
    Path("docs/experiments/semantic_eval.md").write_text(report.to_markdown(agg, cov, config.REASON_MODEL))
    print(f"  B drift={agg['B']['drift_rate']}  E drift={agg['E']['drift_rate']}")
    print(f"  coverage: E abstain={cov['E_abstain_rate']}  B attempt={cov['B_attempt_rate']}")
    print(f"  VERDICT: {report.verdict(agg)}")
    print(f"Wrote docs/experiments/semantic_eval.md + {config.SEMX_RECORDS}")


if __name__ == "__main__":
    main()
