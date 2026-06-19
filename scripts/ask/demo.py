"""M6 demo: one representative query per archetype Q1–Q8, answered end-to-end through the
router (F). Proves the prototype covers the full taxonomy.
Run: `uv run scripts/ask/demo.py`"""
from rm_assistant.retrieval import router

DEMO = [
    ("Q1 filter/agg", "Which clients have AUM over 2 million and have not been contacted in over 180 days?"),
    ("Q2 entity lookup", "What is the balance and last transaction date for account 1787?"),
    ("Q3 fuzzy recall", "Which clients raised concerns about retirement or running out of savings?"),
    ("Q4 client-360", "Give me a pre-meeting brief for client 980."),
    ("Q5 multi-hop", "Which clients work at the same employer as client 16?"),
    ("Q6 metric/KPI", "What is the total AUM held by my UHNW clients?"),
    ("Q7 hybrid", "Among clients who mentioned a property purchase or liquidity need, which have an outstanding loan?"),
    ("Q8 policy Q&A", "What is the eligibility for the structured note product?"),
]


def main() -> None:
    for label, q in DEMO:
        print("=" * 80)
        print(f"{label}\nQ: {q}")
        r = router.ask(q)
        first = r.answer.strip().splitlines()[0] if r.answer.strip() else "(no answer)"
        print(f"[route -> {r.route}]")
        print(f"A: {first[:300]}")
    print("=" * 80)


if __name__ == "__main__":
    main()
