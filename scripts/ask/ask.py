"""Top-level router (F): ask anything, it routes to the right pillar.
Run: `uv run scripts/ask/ask.py "summarize client 980 before our meeting"`"""
import sys

from rm_assistant.retrieval import router


def main() -> None:
    q = " ".join(sys.argv[1:]) or "How many clients are UHNW?"
    r = router.ask(q)
    print(f"Q: {q}")
    print(f"[route: {r.route}]  {r.detail}\n")
    print(r.answer)


if __name__ == "__main__":
    main()
