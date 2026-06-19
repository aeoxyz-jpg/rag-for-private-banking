"""Phase-3d: RRF vs RRF+LLM-reranker vs RRF+cross-encoder on the hard set. Prereq: corpus built,
hard gold generated. Run: `uv run scripts/eval/run_rerank_eval.py`."""
import json
from pathlib import Path

from rm_assistant import config
from rm_assistant.rerankx import hardset, report, runner, reranker


def main() -> None:
    qs = hardset.load()
    print(f"{len(qs)} hard questions, pool={config.RERANK_POOL}")
    out = {}
    # LLM reranker (existing default)
    out["llm"] = report.aggregate(runner.run(qs))
    # cross-encoder
    ce = reranker.CrossEncoderReranker()
    recs_ce = runner.run(qs, rerank_fn=lambda q, c: ce.rerank(q, c))
    out["cross_encoder"] = report.aggregate(recs_ce)
    for arm, agg in out.items():
        v = report.verdict(agg)
        print(f"{arm}: MRR {agg['rrf']['mrr']}->{agg['rerank']['mrr']} "
              f"recall@1 {agg['rrf']['recall@1']}->{agg['rerank']['recall@1']} verdict={v}")
    Path("docs/experiments").mkdir(parents=True, exist_ok=True)
    md = report.to_markdown(out["cross_encoder"], config.RERANK_CE_MODEL)
    Path("docs/experiments/rerank_eval.md").write_text(md)
    config.RERANKX_RECORDS.write_text(json.dumps(recs_ce, indent=1))
    print("Report -> docs/experiments/rerank_eval.md")


if __name__ == "__main__":
    main()
