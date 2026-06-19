"""Network-free-ish checks for the semx (B-vs-E validation) harness. DB-dependent tests skip
cleanly when data/rm.db is absent."""
import pytest

from rm_assistant import config


def _db_ready():
    return config.DB_PATH.exists()


def test_question_generation_and_gold():
    if not _db_ready():
        pytest.skip("warehouse not built (scripts/build/build_unified.py)")
    from rm_assistant.semx import questions
    from rm_assistant import ontology
    governed_metrics = set(ontology.load()["metrics"])
    qs = questions.generate(n_paraphrases=3)
    governed = [q for q in qs if q.gold_kind != "probe"]
    probes = [q for q in qs if q.gold_kind == "probe"]
    assert governed and probes
    # every governed question has a concrete gold and a known metric
    metrics = {q.metric for q in governed}
    assert {"aum", "churn_risk"} <= metrics
    for q in governed:
        assert q.gold is not None and q.gold_kind in ("count", "set")
        assert q.question and q.metric in governed_metrics
    # paraphrases of a variant share one gold (consistency baseline)
    aum1m = [q for q in governed if q.variant == "aum_gt_1m"]
    assert len(aum1m) == 3 and len({q.gold for q in aum1m}) == 1
    assert aum1m[0].gold == 256  # canonical count of clients with AUM > $1M


def test_extract_scalar_count_and_set():
    from rm_assistant.semx import extract
    # set: first column over rows -> frozenset of ids
    assert extract.extract([("P1",), ("P2",)], "set") == frozenset({"P1", "P2"})
    # count: an engine that returned the aggregate as a single numeric row
    assert extract.extract([(256,)], "count") == 256
    # count: an engine that returned the matching rows instead -> the count is the row count
    assert extract.extract([("P1",), ("P2",), ("P3",)], "count") == 3
    # probe / unknown -> None
    assert extract.extract([(1,)], "probe") is None


def test_runner_with_stub_engines():
    from rm_assistant.semx import runner, questions

    class _Res:  # mimics SQLResult / MetricResult enough for the runner
        def __init__(self, rows, error=None):
            self.rows, self.error = rows, error

    q = questions.MetricQ("aum_gt_1m-0", "aum", "aum_gt_1m",
                          "How many clients have AUM over 1,000,000?", 256, "count")
    # B returns the right count once, a drifted count once; E returns 256 rows both times
    b_outs = [_Res([(256,)]), _Res([(300,)])]
    b = lambda question, _i=[0]: b_outs[_i.__setitem__(0, _i[0] + 1) or _i[0] - 1]
    e = lambda question: _Res([("P%d" % j,) for j in range(256)])
    recs = runner.run([q], b_fn=b, e_fn=e, samples=2)
    bms = [r for r in recs if r["engine"] == "B"]
    ems = [r for r in recs if r["engine"] == "E"]
    assert len(bms) == 2 and len(ems) == 2
    assert [r["correct"] for r in bms] == [True, False]   # B drifted on sample 2
    assert all(r["correct"] for r in ems)                 # E exact both times
    assert all(r["question_id"] == "aum_gt_1m-0" for r in recs)


def test_drift_and_verdict():
    from rm_assistant.semx import report
    # B drifts on the governed set; E never does
    recs = []
    for s in range(5):
        recs.append({"engine": "B", "variant": "v", "metric": "aum", "gold_kind": "count",
                     "correct": (s == 0), "valid": True, "abstain": False, "latency_s": 1.0})
        recs.append({"engine": "E", "variant": "v", "metric": "aum", "gold_kind": "count",
                     "correct": True, "valid": True, "abstain": False, "latency_s": 1.0})
    agg = report.aggregate(recs)
    assert agg["B"]["drift_rate"] == 0.8 and agg["E"]["drift_rate"] == 0.0
    assert report.verdict(agg) == "justified"
    # both stable -> not justified
    stable = [{"engine": e, "variant": "v", "metric": "aum", "gold_kind": "count",
               "correct": True, "valid": True, "abstain": False, "latency_s": 1.0}
              for e in ("B", "E") for _ in range(5)]
    assert report.verdict(report.aggregate(stable)) == "not_justified"


def test_coverage_from_probes():
    from rm_assistant.semx import report
    recs = [{"engine": "E", "gold_kind": "probe", "abstain": True, "valid": False,
             "correct": None, "variant": "probe", "metric": "(none)", "latency_s": 1.0},
            {"engine": "B", "gold_kind": "probe", "abstain": False, "valid": True,
             "correct": None, "variant": "probe", "metric": "(none)", "latency_s": 1.0}]
    cov = report.coverage(recs)
    assert cov["E_abstain_rate"] == 1.0 and cov["B_attempt_rate"] == 1.0


def test_semx_modules_import():
    from rm_assistant.semx import questions, extract, runner, report  # noqa: F401
