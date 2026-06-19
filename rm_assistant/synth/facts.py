"""Gather grounding facts per client from the warehouse. These facts (a) condition
the LLM note synthesis so notes stay consistent with the structured data, and
(b) are stored verbatim as provenance to make gold-answer construction possible (spec §3.4)."""
from __future__ import annotations

import sqlite3

# Berka k_symbol -> life-stage / cashflow signal (grounds realistic narratives)
KSYMBOL_MEANING = {
    "DUCHOD": "receives an old-age pension (retiree)",
    "UVER": "makes loan repayments",
    "POJISTNE": "pays insurance premiums",
    "SIPO": "pays recurring household bills",
    "UROK": "earns account interest",
    "SANKC. UROK": "has incurred penalty interest",
    "SLUZBY": "pays account service fees",
}

DATA_AS_OF = "1998-12-31"  # Berka corpus end; note dates are anchored before this


def active_book(conn: sqlite3.Connection, n: int) -> list[int]:
    """Deterministic 'active book' subset: clients ranked by an engagement score
    (AUM + has-loan + transaction volume)."""
    rows = conn.execute(
        """
        SELECT cl.client_id,
               SUM(a.balance) + COALESCE(SUM(h.mv),0)            AS aum,
               COUNT(DISTINCT l.loan_id)                          AS loans,
               COUNT(t.txn_id)                                    AS txns
        FROM clients cl
        JOIN accounts a       ON a.client_id = cl.client_id
        LEFT JOIN (SELECT account_id, SUM(market_value) mv FROM holdings GROUP BY account_id) h
                              ON h.account_id = a.account_id
        LEFT JOIN loans l     ON l.client_id = cl.client_id
        LEFT JOIN transactions t ON t.account_id = a.account_id
        GROUP BY cl.client_id
        """
    ).fetchall()
    scored = sorted(
        rows,
        key=lambda r: (r["aum"] or 0) / 1e5 + (r["loans"] or 0) * 5 + (r["txns"] or 0) / 100,
        reverse=True,
    )
    return [r["client_id"] for r in scored[:n]]


def client_facts(conn: sqlite3.Connection, client_id: int) -> dict:
    cl = conn.execute("SELECT * FROM clients WHERE client_id=?", (client_id,)).fetchone()
    birth_year = int(cl["birth_date"][:4]) if cl["birth_date"] else None
    age = 1999 - birth_year if birth_year else None

    acc = conn.execute(
        """SELECT a.account_id, a.balance, a.opened_at,
                  COALESCE(SUM(h.market_value),0) portfolio
           FROM accounts a LEFT JOIN holdings h ON h.account_id=a.account_id
           WHERE a.client_id=? GROUP BY a.account_id""", (client_id,)).fetchall()
    aum = sum(a["balance"] + a["portfolio"] for a in acc)

    classes = conn.execute(
        """SELECT h.asset_class, ROUND(SUM(h.market_value),0) v
           FROM holdings h JOIN accounts a ON a.account_id=h.account_id
           WHERE a.client_id=? GROUP BY h.asset_class ORDER BY v DESC""", (client_id,)).fetchall()

    loans = conn.execute(
        "SELECT principal, rate, status, maturity FROM loans WHERE client_id=?",
        (client_id,)).fetchall()
    leads = [r["product"] for r in conn.execute(
        "SELECT DISTINCT product FROM leads WHERE client_id=?", (client_id,))]

    # cashflow signals from recurring transaction purpose codes
    signals = []
    for r in conn.execute(
        """SELECT t.k_symbol, COUNT(*) n FROM transactions t
           JOIN accounts a ON a.account_id=t.account_id
           WHERE a.client_id=? AND t.k_symbol IS NOT NULL
           GROUP BY t.k_symbol ORDER BY n DESC""", (client_id,)):
        meaning = KSYMBOL_MEANING.get((r["k_symbol"] or "").strip())
        if meaning:
            signals.append(meaning)

    notable = conn.execute(
        """SELECT t.ts, t.amount, t.type, t.channel FROM transactions t
           JOIN accounts a ON a.account_id=t.account_id
           WHERE a.client_id=? ORDER BY t.amount DESC LIMIT 3""", (client_id,)).fetchall()

    household = conn.execute(
        "SELECT COUNT(*) n FROM clients WHERE household_id=?", (cl["household_id"],)).fetchone()["n"]

    return {
        "client_id": client_id,
        "name": cl["name"],
        "age": age,
        "gender": "female" if cl["gender"] == "F" else "male",
        "district": cl["district"],
        "segment": cl["segment"],
        "risk_profile": cl["risk_profile"],
        "kyc_status": cl["kyc_status"],
        "client_since": cl["since"],
        "aum_usd": round(aum),
        "num_accounts": len(acc),
        "portfolio_mix": {c["asset_class"]: c["v"] for c in classes},
        "loans": [dict(l) for l in loans],
        "open_leads": leads,
        "cashflow_signals": signals[:4],
        "household_size": household,
        "notable_transactions": [dict(t) for t in notable],
    }
