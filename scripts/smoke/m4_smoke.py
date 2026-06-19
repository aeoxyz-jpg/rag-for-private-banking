"""M4 exit smoke: router classification, metric consistency, Q7 end-to-end, Q4 c360.
Run: `uv run scripts/smoke/m4_smoke.py`"""
import re

from rm_assistant import db, ontology
from rm_assistant.retrieval import c360, router, semantic, sql_pillar

CLASSIFY_SET = [
    ("How many clients are in the HNW segment?", "sql"),
    ("What is the total AUM of my UHNW clients?", "metric"),
    ("Which clients mentioned retirement concerns?", "vector"),
    ("How often must KYC be refreshed?", "kb"),
    ("Give me a pre-meeting brief for client 980.", "c360"),
    ("Among clients who mentioned a property purchase, which have an outstanding loan?", "hybrid"),
]


def main() -> None:
    print("== 1. Router classification ==")
    hits = 0
    for q, exp in CLASSIFY_SET:
        got = router.classify(q)["route"]
        hits += got == exp
        print(f"  [{exp:7}] {'OK' if got==exp else 'got '+got:10}  {q[:55]}")
    print(f"  route accuracy: {hits}/{len(CLASSIFY_SET)}")

    print("\n== 2. Metric consistency (governed AUM == text-to-SQL AUM) ==")
    _, e_rows = semantic.run_metric("aum", where="aum > 1000000", limit=10000)
    e_count = len(e_rows)
    direct = db.connect(readonly=True).execute(
        f"SELECT COUNT(*) FROM ({ontology.metric_sql('aum')}) WHERE aum>1000000").fetchone()[0]
    b = sql_pillar.answer("How many clients have AUM over 1 million dollars?")
    b_count = b.rows[0][0] if b.rows else None
    m = re.search(r"\b(\d+)\b", b.answer)
    b_ans = int(m.group(1)) if m else None
    print(f"  E governed metric : {e_count}")
    print(f"  direct governed   : {direct}")
    print(f"  B text-to-SQL rows: {b_count}  (answer says {b_ans})")
    consistent = e_count == direct == b_count
    print(f"  -> consistent: {consistent}")

    print("\n== 3. Q7 hybrid end-to-end ==")
    r = router.ask("Among clients who mentioned a property purchase or liquidity need, "
                   "which ones have an outstanding loan?")
    q7_ok = r.route == "hybrid" and bool(r.detail.get("candidates")) and bool(r.answer)
    print(f"  route={r.route}  candidates={len(r.detail.get('candidates', []))}  answer_len={len(r.answer)}")
    print(f"  -> Q7 pipeline ran: {q7_ok}")

    print("\n== 4. Q4 Customer-360 ==")
    brief = c360.build(980)
    c360_ok = brief.metrics.get("aum") is not None and bool(brief.narrative)
    print(f"  client 980 AUM={brief.metrics['aum']:,.0f}  narrative_len={len(brief.narrative)}  -> {c360_ok}")

    print("\n" + "=" * 60)
    ok = (hits == len(CLASSIFY_SET)) + consistent + q7_ok + c360_ok
    print(f"M4 smoke: {ok}/4 checks passed "
          f"(routing={hits}/{len(CLASSIFY_SET)}, metric_consistent={consistent}, q7={q7_ok}, c360={c360_ok})")


if __name__ == "__main__":
    main()
