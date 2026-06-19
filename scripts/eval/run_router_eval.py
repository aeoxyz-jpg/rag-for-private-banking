"""Pillar F routing-accuracy validation. Prereq: warehouse + corpus built, Ollama reachable.
Runs the routing gold through router.classify() for each model in --models and writes the
confusion-matrix report for the FIRST model. Run: `uv run scripts/eval/run_router_eval.py`."""
import argparse
import json
from pathlib import Path

from rm_assistant import config
from rm_assistant.routerx import runner, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(config.SWEEP_MODELS))
    args = ap.parse_args()
    gold = runner.load_gold()
    out_dir = Path("docs/experiments"); out_dir.mkdir(parents=True, exist_ok=True)
    for i, model in enumerate(args.models.split(",")):
        recs = runner.run(gold, model=model)
        agg = report.aggregate(recs)
        print(f"{model}: accuracy {agg['accuracy']:.0%} (n={agg['n']}), "
              f"{len(agg['errors'])} misroutes")
        if i == 0:
            config.ROUTERX_RECORDS.parent.mkdir(parents=True, exist_ok=True)
            config.ROUTERX_RECORDS.write_text(json.dumps(recs, indent=1))
            (out_dir / "router_eval.md").write_text(report.to_markdown(agg, model))
    print("Report -> docs/experiments/router_eval.md")


if __name__ == "__main__":
    main()
