"""Build the unified warehouse (spec §3.3) from the raw Berka mirror + seeded synthesis.

Deterministic given config.SEED -> reproducible build (spec §3.6). The LLM-synthesized
unstructured layer (documents/interactions) is added separately by synth/notes.py.

Berka is *retail* banking; the wealth framing needs a portfolio layer, RMs, leads and
employer links that Berka lacks — those are synthesized here. The currency is labelled
USD and Berka magnitudes are taken at face value (no FX); the synthetic holdings layer
supplies the HNW/UHNW tail so AUM-based queries (Q1/Q6) are meaningful.
"""
from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

from faker import Faker

from .. import config, db

_SQL = Path(__file__).with_name("unified_schema.sql")

RISK_PROFILES = ["Conservative", "Balanced", "Growth", "Aggressive"]
KYC_STATES = (["verified"] * 85) + (["pending"] * 10) + (["expired"] * 5)
ASSET_CLASSES = ["Equity", "Fixed Income", "Fund", "Cash", "Alternative"]
SECTORS = ["Technology", "Manufacturing", "Real Estate", "Healthcare",
           "Energy", "Retail", "Financial Services", "Logistics"]
LEAD_PRODUCTS = ["Term Deposit", "Structured Note", "Mortgage Refinance",
                 "Investment Fund", "Premium Credit Card", "Wealth Advisory"]
LEAD_STATES = ["open", "contacted", "won", "lost"]
CHANNEL_MAP = {
    "VYBER": "atm", "VYBER KARTOU": "card", "VKLAD": "branch",
    "PREVOD NA UCET": "transfer_out", "PREVOD Z UCTU": "transfer_in", None: "system",
}
LOAN_STATUS_MAP = {"A": "paid", "B": "defaulted", "C": "current", "D": "delinquent"}


def _segment(aum: float) -> str:
    if aum >= 5_000_000:
        return "UHNW"
    if aum >= 1_000_000:
        return "HNW"
    if aum >= 100_000:
        return "Affluent"
    return "Mass Affluent"


# Berka loans are interest-free in the source (payments == amount/duration), so there
# is no rate signal to derive. We synthesize a plausible APR varied by status.
_STATUS_PREMIUM = {"paid": -0.005, "current": 0.0, "delinquent": 0.02, "defaulted": 0.03}


def _synth_apr(rng: random.Random, status: str) -> float:
    rate = rng.uniform(0.03, 0.07) + _STATUS_PREMIUM.get(status, 0.0)
    return round(max(0.02, rate), 4)


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def build() -> dict[str, int]:
    rng = random.Random(config.SEED)
    fake = Faker()
    Faker.seed(config.SEED)

    raw = db.connect(config.BERKA_RAW_DB, readonly=True)
    if Path(config.DB_PATH).exists():
        Path(config.DB_PATH).unlink()
    uni = db.connect(config.DB_PATH)
    uni.executescript(_SQL.read_text())

    counts: dict[str, int] = {}

    # --- relationship managers ---
    rms = [(i, fake.name(), rng.choice(["Mass Affluent", "Affluent", "HNW", "UHNW"]))
           for i in range(1, config.N_RMS + 1)]
    uni.executemany("INSERT INTO relationship_managers VALUES (?,?,?)", rms)
    counts["relationship_managers"] = len(rms)

    # --- companies ---
    companies = [(i, fake.company(), rng.choice(SECTORS))
                 for i in range(1, config.N_COMPANIES + 1)]
    uni.executemany("INSERT INTO companies VALUES (?,?,?)", companies)
    counts["companies"] = len(companies)

    # --- accounts (owner from disp, balance from latest trans) ---
    owner = {r["account_id"]: r["client_id"]
             for r in raw.execute("SELECT account_id, client_id FROM disp WHERE type='OWNER'")}
    balance = {r["account_id"]: r["balance"] for r in raw.execute(
        """SELECT account_id, balance FROM (
               SELECT account_id, balance,
                      ROW_NUMBER() OVER (PARTITION BY account_id
                                         ORDER BY date DESC, trans_id DESC) rn
               FROM trans) WHERE rn = 1""")}
    acct_rows = []
    for a in raw.execute("SELECT account_id, frequency, date FROM account"):
        aid = a["account_id"]
        acct_rows.append((aid, owner.get(aid), "current", "USD",
                          float(balance.get(aid, 0.0)), a["date"], a["frequency"]))
    uni.executemany("INSERT INTO accounts VALUES (?,?,?,?,?,?,?)", acct_rows)
    counts["accounts"] = len(acct_rows)

    # --- holdings (synthetic, wealth-weighted by balance) ---
    bal_sorted = sorted((b for b in balance.values()), reverse=True) or [0]
    p80 = bal_sorted[int(len(bal_sorted) * 0.2)] if bal_sorted else 0
    holdings, hid = [], 1
    acct_portfolio: dict[int, float] = {}
    for aid, _, _, _, bal, _, _ in acct_rows:
        # wealthier accounts more likely to hold a portfolio; size ~ lognormal
        prob = 0.85 if bal >= p80 else 0.35
        if rng.random() > prob:
            continue
        scale = bal * rng.uniform(1.5, 12) + rng.lognormvariate(11, 1.4)
        n = rng.randint(1, 8)
        for _ in range(n):
            mv = round(scale / n * rng.uniform(0.4, 1.6), 2)
            acct_portfolio[aid] = acct_portfolio.get(aid, 0.0) + mv
            holdings.append((hid, aid, fake.company(),
                             rng.choice(ASSET_CLASSES), mv, round(rng.uniform(1, 5000), 2)))
            hid += 1
    uni.executemany("INSERT INTO holdings VALUES (?,?,?,?,?,?)", holdings)
    counts["holdings"] = len(holdings)

    # --- households (union-find over clients sharing an account) ---
    uf = _UnionFind()
    acct_clients: dict[int, list[int]] = {}
    for r in raw.execute("SELECT account_id, client_id FROM disp"):
        acct_clients.setdefault(r["account_id"], []).append(r["client_id"])
    for cids in acct_clients.values():
        for c in cids[1:]:
            uf.union(cids[0], c)

    # AUM per client = owned-account balances + portfolios
    client_aum: dict[int, float] = {}
    client_since: dict[int, str] = {}
    for aid, cid, _, _, bal, opened, _ in acct_rows:
        if cid is None:
            continue
        client_aum[cid] = client_aum.get(cid, 0.0) + bal + acct_portfolio.get(aid, 0.0)
        if cid not in client_since or (opened and opened < client_since[cid]):
            client_since[cid] = opened

    # --- clients ---
    districts = {r["district_id"]: r["A2"] for r in raw.execute("SELECT district_id, A2 FROM district")}
    client_rows = []
    for c in raw.execute("SELECT client_id, gender, birth_date, district_id FROM client"):
        cid = c["client_id"]
        aum = client_aum.get(cid, 0.0)
        name = fake.name_female() if c["gender"] == "F" else fake.name_male()
        client_rows.append((
            cid, rng.randint(1, config.N_RMS), name, c["gender"], c["birth_date"],
            _segment(aum), rng.choice(RISK_PROFILES), rng.choice(KYC_STATES),
            uf.find(cid), client_since.get(cid), districts.get(c["district_id"]),
        ))
    uni.executemany("INSERT INTO clients VALUES (?,?,?,?,?,?,?,?,?,?,?)", client_rows)
    counts["clients"] = len(client_rows)

    # --- loans (client via account owner; implied APR; maturity = opened + duration months) ---
    loan_rows = []
    for ln in raw.execute("SELECT * FROM loan"):
        opened = dt.date.fromisoformat(ln["date"])
        maturity = opened + dt.timedelta(days=30 * ln["duration"])
        status = LOAN_STATUS_MAP.get(ln["status"], "current")
        loan_rows.append((
            ln["loan_id"], owner.get(ln["account_id"]), ln["account_id"],
            float(ln["amount"]), _synth_apr(rng, status), status,
            ln["date"], maturity.isoformat(), float(ln["payments"]),
        ))
    uni.executemany("INSERT INTO loans VALUES (?,?,?,?,?,?,?,?,?)", loan_rows)
    counts["loans"] = len(loan_rows)

    # --- leads (synthetic; sparse, weighted toward wealthier clients) ---
    lead_rows, lid = [], 1
    today = dt.date(1999, 1, 1)  # Berka data ends ~1998
    for cid in client_aum:
        if rng.random() > 0.25:
            continue
        for _ in range(rng.randint(1, 3)):
            created = today - dt.timedelta(days=rng.randint(0, 540))
            lead_rows.append((lid, cid, rng.choice(LEAD_PRODUCTS),
                              round(rng.random(), 3), rng.choice(LEAD_STATES),
                              created.isoformat()))
            lid += 1
    uni.executemany("INSERT INTO leads VALUES (?,?,?,?,?,?)", lead_rows)
    counts["leads"] = len(lead_rows)

    # --- transactions (stream-transform the ~1M raw rows) ---
    n_txn = 0
    batch = []
    for t in raw.execute("SELECT * FROM trans"):
        ttype = "credit" if t["type"] == "PRIJEM" else "debit"
        batch.append((t["trans_id"], t["account_id"], t["date"], float(t["amount"]),
                      ttype, t["bank"], CHANNEL_MAP.get(t["operation"], "system"),
                      t["k_symbol"]))
        if len(batch) >= 10000:
            uni.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)", batch)
            n_txn += len(batch)
            batch = []
    if batch:
        uni.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)", batch)
        n_txn += len(batch)
    counts["transactions"] = n_txn

    # --- edges: advisor (rm->client), household (client-client), employer (client->company) ---
    edges = []
    for r in client_rows:
        cid, rm = r[0], r[1]
        edges.append(("rm", rm, "client", cid, "advisor"))               # advisor
        root = uf.find(cid)
        if root != cid:                                                  # household
            edges.append(("client", cid, "client", root, "household"))
        if rng.random() < 0.30:                                          # employer (Q5)
            edges.append(("client", cid, "company", rng.randint(1, config.N_COMPANIES), "employer"))
    uni.executemany("INSERT INTO edges VALUES (?,?,?,?,?)", edges)
    counts["edges"] = len(edges)

    uni.executemany("INSERT INTO build_meta VALUES (?,?)",
                    [("seed", str(config.SEED)), ("built_from", "berka_raw")])
    uni.commit()
    raw.close()
    uni.close()
    return counts
