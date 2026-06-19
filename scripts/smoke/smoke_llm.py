"""M0 smoke: exercise the model abstraction. Always runs the fast (local) LLM;
runs the smart provider too if --smart is passed (codex/anthropic may be slow).
Run: `uv run scripts/smoke/smoke_llm.py [--smart]`"""
import sys

from rm_assistant.models.factory import get_fast_llm, get_smart_llm

PROMPT = "In one sentence, what is a relationship manager in private banking?"


def main() -> None:
    fast = get_fast_llm()
    print(f"[fast] {fast.name}")
    print("  " + fast.complete(PROMPT))

    if "--smart" in sys.argv:
        smart = get_smart_llm()
        print(f"\n[smart] {smart.name}")
        print("  " + smart.complete(PROMPT))


if __name__ == "__main__":
    main()
