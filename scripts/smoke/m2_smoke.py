"""M2 exit smoke: run the representative query set through both pillars (B text-to-SQL,
A hybrid vector) and show each answers end-to-end.
Run: `uv run scripts/smoke/m2_smoke.py`"""
from rm_assistant.eval.queryset import SMOKE_SET
from rm_assistant.retrieval import sql_pillar, vector_pillar


def main() -> None:
    ok = 0
    for arche, pillar, q, kw in SMOKE_SET:
        print("=" * 78)
        print(f"[{arche} | {pillar}] {q}")
        if pillar == "sql":
            r = sql_pillar.answer(q)
            passed = r.error is None and bool(r.rows)
            print(f"  SQL (attempt {r.attempts}): {' '.join(r.sql.split())[:140]}")
            print(f"  -> {len(r.rows)} rows | {'OK' if passed else 'FAIL: ' + (r.error or 'no rows')}")
            print(f"  answer: {r.answer.strip().splitlines()[0][:160] if r.answer else '-'}")
        else:
            r = vector_pillar.answer(q, **kw)
            passed = bool(r.sources) and bool(r.answer)
            cites = ", ".join(s.doc_id for s in r.sources[:3])
            print(f"  retrieved: {len(r.sources)} sources ({cites}...)")
            print(f"  answer: {r.answer.strip().splitlines()[0][:160]}")
        ok += passed
    print("=" * 78)
    print(f"M2 smoke: {ok}/{len(SMOKE_SET)} queries answered end-to-end")


if __name__ == "__main__":
    main()
