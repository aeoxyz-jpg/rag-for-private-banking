"""M3: run the gold set through both pillars, score, write the scoreboard.
Run: `uv run scripts/eval/run_eval.py [--limit N] [--no-judge]`
Outputs: data/eval_records.json (raw) + docs/experiments/scoreboard.md."""
import argparse
import json
from pathlib import Path

from rm_assistant import config
from rm_assistant.eval import runner, scoreboard


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()

    records = runner.run(limit=args.limit, do_judge=not args.no_judge)
    agg = scoreboard.aggregate(records)

    Path("data/eval_records.json").write_text(json.dumps(records, indent=1, default=str))
    md = scoreboard.to_markdown(agg, config.REASON_MODEL)
    Path("docs/experiments/scoreboard.md").write_text(md)

    print(json.dumps(agg["sql"]["ALL"], indent=1))
    print(json.dumps(agg["vector"]["ALL"], indent=1))
    print(f"\nWrote docs/experiments/scoreboard.md + data/eval_records.json "
          f"({len(records)} queries, {len(agg['errors'])} errors)")


if __name__ == "__main__":
    main()
