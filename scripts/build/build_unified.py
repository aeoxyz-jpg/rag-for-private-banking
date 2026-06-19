"""M1: build the unified warehouse from raw Berka + seeded synthesis.
Run: `uv run scripts/build/build_unified.py`"""
from rm_assistant import config
from rm_assistant.etl import build_unified


def main() -> None:
    print(f"Building unified warehouse -> {config.DB_PATH} (seed={config.SEED})")
    counts = build_unified.build()
    for table, n in counts.items():
        print(f"  {table:24} {n:>9,}")


if __name__ == "__main__":
    main()
