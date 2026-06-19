"""Network-free checks for eval metrics + gold-set integrity."""
import json
from pathlib import Path

from rm_assistant.eval import metrics as m

_GOLD = Path("rm_assistant/eval/gold")


def test_exec_match_order_insensitive():
    assert m.exec_match([(1,), (2,)], [(2,), (1,)])
    assert not m.exec_match([(1,)], [(1,), (2,)])


def test_exec_match_float_tolerance():
    assert m.exec_match([(1.005,)], [(1.0049,)])  # rounded to 2dp


def test_value_recall_tolerates_extra_columns():
    assert m.value_recall([(256,)], [(256, "extra")]) == 1.0
    assert m.value_recall([], []) == 1.0  # both empty (adversarial)


def test_recall_and_mrr():
    assert m.recall_at_k(["a"], ["x", "a", "b"], 5) == 1.0
    assert m.recall_at_k(["a"], ["x", "b"], 5) == 0.0
    assert m.mrr(["a"], ["x", "a"]) == 0.5


def test_gold_sets_wellformed():
    sql = json.loads((_GOLD / "sql.json").read_text())
    vec = json.loads((_GOLD / "vector.json").read_text())
    assert len(sql) >= 20 and len(vec) >= 20
    assert all({"id", "archetype", "reference_sql"} <= set(g) for g in sql)
    assert all(g["gold_doc_ids"] for g in vec)
