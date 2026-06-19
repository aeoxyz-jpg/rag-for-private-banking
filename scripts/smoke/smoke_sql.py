"""M0 smoke: a trivial-but-real SQL query over loaded Berka (incl. a join).
Run: `uv run scripts/smoke/smoke_sql.py`"""
from rm_assistant import config, db


def main() -> None:
    conn = db.connect(config.BERKA_RAW_DB, readonly=True)
    n_clients = conn.execute("SELECT COUNT(*) FROM client").fetchone()[0]
    n_accounts = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    n_txn = conn.execute("SELECT COUNT(*) FROM trans").fetchone()[0]
    print(f"clients={n_clients:,}  accounts={n_accounts:,}  transactions={n_txn:,}")

    print("\nTop 5 districts by client count (client ⨝ district):")
    rows = conn.execute(
        """
        SELECT d.A2 AS district, COUNT(*) AS clients
        FROM client c JOIN district d ON c.district_id = d.district_id
        GROUP BY d.A2 ORDER BY clients DESC LIMIT 5
        """
    ).fetchall()
    for r in rows:
        print(f"  {r['district']:20} {r['clients']:>5}")
    conn.close()


if __name__ == "__main__":
    main()
