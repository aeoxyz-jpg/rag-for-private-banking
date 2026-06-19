"""Sensitivity sweep: is the KG verdict ("recursive SQL is fully capable at the oracle ceiling
except variable-length shortest_path") robust to graph scale/depth? For each scale, rebuild the
graph and re-run the ORACLE-mode queries (samples=0) — the deterministic capability ceiling the
verdict is keyed on — then tabulate per-engine oracle accuracy by category.

Oracle-only is the methodologically correct test here: the verdict is oracle-keyed, so LLM-authoring
noise is irrelevant. It also sidesteps a native kuzu crash triggered by pathological LLM-generated
Cypher under heavy load (see docs/experiments/kg_sensitivity.md note). Run: `uv run scripts/eval/sweep_kg.py`.
Each scale rebuilds the graph; the SQL shortest_path recursive CTE hits the 30s timeout by design, so
allow a few minutes per scale."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

N_PER_CATEGORY = 8  # enough to expose a capability break per category; bounds shortest_path timeouts

SCALES = [  # (name, RM_WG_* env overrides) — small / default / large
    ("small", {"RM_WG_ENTITIES": "120", "RM_WG_HOUSEHOLDS": "80", "RM_WG_ACCOUNTS": "250"}),
    ("default", {}),
    ("large", {"RM_WG_ENTITIES": "320", "RM_WG_HOUSEHOLDS": "200", "RM_WG_ACCOUNTS": "650"}),
]


def _run_oracle(config) -> list[dict]:
    from rm_assistant.kgx import kuzu_loader, questions, runner
    kuzu_loader.load_kuzu(config.WEALTH_GRAPH_DIR, config.WEALTH_KUZU)
    qs = questions.generate(config.WEALTH_TRUTH, N_PER_CATEGORY, config.SEED)
    # samples=0 -> no LLM tasks, oracle records only (deterministic capability ceiling)
    return runner.run(qs, sql_llm=None, cypher_llm=None, samples=0)


def _summary(recs: list[dict]) -> dict:
    oracle = [r for r in recs if r.get("mode") == "oracle"]

    def acc(engine, cat=None, exclude=None):
        rs = [r for r in oracle if r["engine"] == engine
              and (cat is None or r["category"] == cat)
              and (exclude is None or r["category"] != exclude)]
        return round(sum(1.0 if r["correct"] else 0.0 for r in rs) / len(rs), 2) if rs else None

    return {"sql_sp": acc("sql", cat="shortest_path"), "cy_sp": acc("cypher", cat="shortest_path"),
            "sql_other": acc("sql", exclude="shortest_path"),
            "cy_other": acc("cypher", exclude="shortest_path")}


def _graph_note(config) -> str:
    con = sqlite3.connect(config.WEALTH_DB)
    try:
        n = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        e = con.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        return f"{n}/{e}"
    finally:
        con.close()


def main() -> None:
    from rm_assistant import config
    rows = []
    for name, overrides in SCALES:
        env = {**os.environ, **overrides}
        subprocess.run([sys.executable, "scripts/build/build_wealth_graph.py"], check=True, env=env)
        recs = _run_oracle(config)
        s = _summary(recs)
        s["note"] = _graph_note(config)
        rows.append((name, s))
        print(f"{name}: {s}")
    L = ["# KG sensitivity — oracle-ceiling robustness across graph scale/depth", "",
         "Does the oracle-keyed verdict ('recursive SQL is fully capable except variable-length "
         "shortest_path') survive as the graph scales? Each row rebuilds the graph at a different "
         f"scale and re-runs the hand-authored oracle queries ({N_PER_CATEGORY}/category, model-free, "
         "deterministic). SQL shortest_path is expected at 0.0 (recursive CTE times out at 30s); "
         "every other category is expected at 1.0 for both engines.", "",
         "| scale | nodes/edges | SQL shortest_path | Cypher shortest_path | SQL other cats | Cypher other cats |",
         "|---|---|--:|--:|--:|--:|"]
    for name, s in rows:
        L.append(f"| {name} | {s['note']} | {s['sql_sp']} | {s['cy_sp']} | {s['sql_other']} | {s['cy_other']} |")
    L += ["", "_A stable pattern (SQL=0 on shortest_path, =1 elsewhere; Cypher=1 throughout) across "
          "scales means the verdict is robust, not an artifact of one graph size._", "",
          "_Note: the LLM-authored sweep was abandoned — pathological LLM-generated Cypher under heavy "
          "load (n×samples) reliably crashed the embedded kuzu engine natively (SIGBUS/SIGSEGV). The "
          "oracle ceiling is the verdict-relevant signal and is crash-free; LLM-authoring capability is "
          "separately characterized in the main report and is model-bound, not scale-bound._"]
    Path("docs/experiments").mkdir(parents=True, exist_ok=True)
    Path("docs/experiments/kg_sensitivity.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
