"""B smoke: ask a natural-language question, see generated SQL + answer.
Run: `uv run scripts/ask/ask_sql.py "which clients are UHNW?"`"""
import sys

from rm_assistant.retrieval import sql_pillar


def main() -> None:
    q = " ".join(sys.argv[1:]) or "How many clients are in each wealth segment?"
    r = sql_pillar.answer(q)
    print(f"Q: {r.question}\n")
    print(f"SQL (attempt {r.attempts}):\n{r.sql}\n")
    if r.error:
        print(f"ERROR: {r.error}")
        return
    print(f"rows: {len(r.rows)}  columns: {r.columns}")
    for row in r.rows[:8]:
        print("  ", tuple(row))
    print(f"\nAnswer:\n{r.answer}")


if __name__ == "__main__":
    main()
