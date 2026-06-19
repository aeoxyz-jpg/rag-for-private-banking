"""M0: pull Berka from the CTU public DB into SQLite. Run: `uv run scripts/build/load_berka.py`"""
from rm_assistant import config
from rm_assistant.etl import berka


def main() -> None:
    print(f"Loading Berka -> {config.BERKA_RAW_DB}")
    counts = berka.load()
    print(f"Done. {sum(counts.values()):,} rows across {len(counts)} tables.")


if __name__ == "__main__":
    main()
