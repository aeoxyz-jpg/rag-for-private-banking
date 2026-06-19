"""Network-free checks for the routerx (routing-accuracy) harness. The live classify() path is
exercised by scripts/eval/run_router_eval.py, not here."""


def test_aggregate_confusion_and_accuracy():
    from rm_assistant.routerx import report
    recs = [
        {"id": "a", "expected_route": "sql", "predicted_route": "sql"},
        {"id": "b", "expected_route": "sql", "predicted_route": "metric"},
        {"id": "c", "expected_route": "metric", "predicted_route": "metric"},
        {"id": "d", "expected_route": "vector", "predicted_route": "vector"},
    ]
    agg = report.aggregate(recs)
    assert agg["n"] == 4
    assert agg["accuracy"] == 0.75
    assert agg["confusion"]["sql"]["sql"] == 1
    assert agg["confusion"]["sql"]["metric"] == 1
    assert agg["per_route"]["sql"]["recall"] == 0.5
    assert agg["per_route"]["sql"]["precision"] == 1.0


def test_markdown_renders():
    from rm_assistant.routerx import report
    recs = [{"id": "a", "expected_route": "sql", "predicted_route": "sql"}]
    md = report.to_markdown(report.aggregate(recs), model="glm-5.2:cloud")
    assert "Routing accuracy" in md and "glm-5.2:cloud" in md


def test_runner_uses_injected_classify():
    from rm_assistant.routerx import runner
    gold = [{"id": "a", "question": "q1", "expected_route": "sql"},
            {"id": "b", "question": "q2", "expected_route": "vector"}]
    routes = {"q1": "sql", "q2": "metric"}
    recs = runner.run(gold, classify_fn=lambda q: routes[q])
    assert len(recs) == 2
    assert recs[0] == {"id": "a", "question": "q1", "expected_route": "sql", "predicted_route": "sql"}
    assert recs[1]["predicted_route"] == "metric"
