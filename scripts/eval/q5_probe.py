"""Q5 gate (spec §4.4 step 6 / M5): can the existing pillars cover multi-hop relationship
queries via text-to-SQL over the edges projection, or is a dedicated KG (C) justified?
Runs the Q5 gold through pillar B and reports execution accuracy + router classification.
Run: `uv run scripts/eval/q5_probe.py`"""
import json
from pathlib import Path

from rm_assistant import db
from rm_assistant.eval import metrics
from rm_assistant.retrieval import router, sql_pillar

GOLD = Path("rm_assistant/eval/gold/q5.json")


def main() -> None:
    gold = json.loads(GOLD.read_text())
    conn = db.connect(readonly=True)
    exact = lenient = routed_ok = 0
    for g in gold:
        gold_rows = [tuple(r) for r in conn.execute(g["reference_sql"]).fetchall()]
        route = router.classify(g["question"])["route"]
        res = sql_pillar.answer(g["question"])
        pred = [tuple(r) for r in res.rows] if res.error is None else []
        em = res.error is None and metrics.exec_match(gold_rows, pred)
        vr = metrics.value_recall(gold_rows, pred) if res.error is None else 0.0
        exact += em
        lenient += vr
        routed_ok += route in ("sql", "hybrid", "metric")
        print(f"  {g['id']}  route={route:7} exec={'Y' if em else 'n'} "
              f"value_recall={vr:.2f}  gold_n={len(gold_rows)} pred_n={len(pred)}")
        if not em:
            print(f"      Q: {g['question']}")
            print(f"      gen SQL: {' '.join(res.sql.split())[:150]}")
    n = len(gold)
    print(f"\nQ5 via B/router: exec_accuracy={exact/n:.2f}  value_recall={lenient/n:.2f}  "
          f"routed_to_structured={routed_ok}/{n}")
    print("Gate: if coverage is high, the edges projection + text-to-SQL suffices -> KG (C) "
          "is NOT justified yet; if low, build the KG.")


if __name__ == "__main__":
    main()
