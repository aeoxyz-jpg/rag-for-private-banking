-- Unified "virtual private bank" schema (spec §3.3). Derived warehouse: built from
-- the raw Berka mirror + seeded synthesis. Everything queryable lives here.
-- FK clauses document relationships; enforcement stays off (build order is not
-- topological — accounts/holdings are populated before clients to derive AUM).

DROP TABLE IF EXISTS relationship_managers;
CREATE TABLE relationship_managers (
    rm_id        INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    book_segment TEXT NOT NULL          -- Mass Affluent | Affluent | HNW | UHNW
);

DROP TABLE IF EXISTS companies;
CREATE TABLE companies (              -- employer nodes for Q5 graph (synthetic)
    company_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    sector     TEXT NOT NULL
);

DROP TABLE IF EXISTS clients;
CREATE TABLE clients (
    client_id    INTEGER PRIMARY KEY,  -- preserved from Berka
    rm_id        INTEGER REFERENCES relationship_managers(rm_id),
    name         TEXT,                 -- synthetic
    gender       TEXT,                 -- from Berka
    birth_date   TEXT,                 -- from Berka
    segment      TEXT,                 -- derived from AUM
    risk_profile TEXT,                 -- synthetic
    kyc_status   TEXT,                 -- synthetic
    household_id INTEGER,              -- derived from shared accounts (disp)
    since        TEXT,                 -- earliest owned-account open date
    district     TEXT                  -- from Berka district A2
);

DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (
    account_id INTEGER PRIMARY KEY,    -- from Berka
    client_id  INTEGER REFERENCES clients(client_id),  -- the OWNER
    type       TEXT,
    currency   TEXT,
    balance    REAL,                   -- latest Berka trans balance
    opened_at  TEXT,
    frequency  TEXT
);

DROP TABLE IF EXISTS holdings;
CREATE TABLE holdings (               -- fully synthetic wealth layer
    holding_id   INTEGER PRIMARY KEY,
    account_id   INTEGER REFERENCES accounts(account_id),
    instrument   TEXT,
    asset_class  TEXT,                 -- Equity | Fixed Income | Fund | Cash | Alternative
    market_value REAL,
    qty          REAL
);

DROP TABLE IF EXISTS transactions;
CREATE TABLE transactions (
    txn_id       INTEGER PRIMARY KEY,  -- from Berka trans_id
    account_id   INTEGER REFERENCES accounts(account_id),
    ts           TEXT,
    amount       REAL,
    type         TEXT,                 -- credit | debit
    counterparty TEXT,
    channel      TEXT,                 -- atm | card | branch | transfer_in | transfer_out | system
    k_symbol     TEXT                  -- raw purpose code (interest/insurance/loan/...)
);

DROP TABLE IF EXISTS loans;
CREATE TABLE loans (
    loan_id         INTEGER PRIMARY KEY,
    client_id       INTEGER REFERENCES clients(client_id),
    account_id      INTEGER REFERENCES accounts(account_id),
    principal       REAL,
    rate            REAL,              -- implied APR derived from payment schedule
    status          TEXT,             -- paid | defaulted | current | delinquent
    opened_at       TEXT,
    maturity        TEXT,
    monthly_payment REAL
);

DROP TABLE IF EXISTS leads;
CREATE TABLE leads (                  -- synthetic NBA targets
    lead_id    INTEGER PRIMARY KEY,
    client_id  INTEGER REFERENCES clients(client_id),
    product    TEXT,
    score      REAL,
    status     TEXT,                  -- open | contacted | won | lost
    created_at TEXT
);

DROP TABLE IF EXISTS interactions;
CREATE TABLE interactions (           -- populated in the synthesis step
    interaction_id INTEGER PRIMARY KEY,
    client_id      INTEGER REFERENCES clients(client_id),
    rm_id          INTEGER REFERENCES relationship_managers(rm_id),
    ts             TEXT,
    channel        TEXT,              -- call | email | meeting | video
    type           TEXT,              -- review | prospecting | service | complaint
    sentiment      TEXT,              -- positive | neutral | negative
    summary_ref    TEXT               -- -> documents.doc_id
);

DROP TABLE IF EXISTS documents;
CREATE TABLE documents (              -- populated in the synthesis step (LLM)
    doc_id         TEXT PRIMARY KEY,
    client_id      INTEGER,           -- NULL for global KB docs
    kind           TEXT,              -- note | transcript | brief | complaint | kb
    ts             TEXT,
    text           TEXT,
    embedding_ref  TEXT,              -- chroma id
    provenance     TEXT               -- JSON: structured facts the doc was grounded on
);

DROP TABLE IF EXISTS edges;
CREATE TABLE edges (                  -- graph projection (spec §3.3)
    src_type TEXT,                    -- client | rm | company
    src_id   INTEGER,
    dst_type TEXT,
    dst_id   INTEGER,
    rel_type TEXT                     -- household | employer | referral | advisor
);

DROP TABLE IF EXISTS build_meta;
CREATE TABLE build_meta (key TEXT PRIMARY KEY, value TEXT);
