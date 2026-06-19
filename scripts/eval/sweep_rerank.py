"""Sensitivity sweep: does the rerank verdict survive harder/easier distractor densities?
For each density d in --densities, regenerate the hard set (gold by-product BEFORE any arm runs),
run RRF vs cross-encoder, and tabulate the MRR/recall@1 lift. Model is held fixed for the LLM-free
cross-encoder; the point is data-knob robustness, not model choice. Run: `uv run scripts/eval/sweep_rerank.py`."""
import subprocess
import sys
from pathlib import Path

from rm_assistant import config
from rm_assistant.rerankx import hardset, report, runner, reranker


def main() -> None:
    densities = [3, 5, 7]
    ce = reranker.CrossEncoderReranker()
    rows = []
    for d in densities:
        out = Path(f"data/rerank_hard_d{d}.json")
        subprocess.run([sys.executable, "scripts/build/gen_rerank_hardset.py",
                        "--min-notes", str(d), "--out", str(out)], check=True)
        qs = hardset.load(out)
        agg = report.aggregate(runner.run(qs, rerank_fn=lambda q, c: ce.rerank(q, c)))
        rows.append((d, len(qs), agg["rrf"]["mrr"], agg["rerank"]["mrr"],
                     agg["rrf"]["recall@1"], agg["rerank"]["recall@1"], report.verdict(agg)))
    L = ["# Rerank sensitivity — cross-encoder across distractor densities", "",
         "Does the reranking verdict survive a harder/easier hard set? Model-free cross-encoder; "
         "only the data knob (min notes per client) varies.", "",
         "| min notes/client | n | RRF MRR | +CE MRR | RRF r@1 | +CE r@1 | verdict |",
         "|--:|--:|--:|--:|--:|--:|---|"]
    for d, n, a, b, ra, rb, v in rows:
        L.append(f"| {d} | {n} | {a} | {b} | {ra} | {rb} | {v} |")
    L += ["", "_A verdict that flips across densities is fragile; a stable sign is robust._"]
    Path("docs/experiments").mkdir(parents=True, exist_ok=True)
    Path("docs/experiments/rerank_sensitivity.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
