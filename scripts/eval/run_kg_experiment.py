"""Phase-2 fair KG experiment v2: load Kùzu, generate questions, run both engines in oracle +
LLM (xsamples) modes, write the dual-metric report. Prereq: `uv run scripts/build/build_wealth_graph.py`.
Run: `uv run scripts/eval/run_kg_experiment.py`  (env: RM_KGX_N_PER_CATEGORY, RM_KGX_SAMPLES)."""
import json
import os
from pathlib import Path

from rm_assistant import config
from rm_assistant.kgx import kuzu_loader, questions, report, runner
from rm_assistant.models.ollama import OllamaLLM


def main() -> None:
    n = int(os.getenv("RM_KGX_N_PER_CATEGORY", str(config.KGX_N_PER_CATEGORY)))
    samples = int(os.getenv("RM_KGX_SAMPLES", "3"))
    print(f"Loading Kùzu -> {config.WEALTH_KUZU}")
    print("  ", kuzu_loader.load_kuzu(config.WEALTH_GRAPH_DIR, config.WEALTH_KUZU))
    qs = questions.generate(config.WEALTH_TRUTH, n, config.SEED)
    print(f"  {len(qs)} questions, samples={samples}")
    llm = OllamaLLM(config.REASON_MODEL)
    recs = runner.run(qs, sql_llm=llm, cypher_llm=llm, samples=samples)
    agg = report.aggregate(recs)
    Path(config.KGX_RECORDS).write_text(json.dumps(recs, indent=1, default=str))
    Path("docs/experiments/kg_experiment.md").write_text(report.to_markdown(agg, config.REASON_MODEL))
    for mode in ("oracle", "llm"):
        print(f"  {mode} by_depth:", {e: agg[mode][e]["by_depth"] for e in ("sql", "cypher")})
    print("  VERDICT (oracle-keyed):", report.verdict(agg))
    print(f"Wrote docs/experiments/kg_experiment.md + {config.KGX_RECORDS}")


if __name__ == "__main__":
    main()
