"""Small representative query set for the M2 pillar smoke. Each item is hand-labelled
with the pillar it targets (routing itself is M4/F). The full ~60-100 gold-answer eval
set is M3."""

# (archetype, pillar, question, kwargs)
SMOKE_SET = [
    ("Q1", "sql", "Which clients have AUM over 2 million and no contact in the last 90 days?", {}),
    ("Q1", "sql", "How many clients are in each wealth segment?", {}),
    ("Q6", "sql", "What is the average loan interest rate by loan status?", {}),
    ("Q2", "sql", "What is the balance and last transaction date for account 1787?", {}),
    ("Q2", "sql", "List the 5 largest loans with their status and borrower client id.", {}),
    ("Q3", "vector", "Which clients raised concerns about retirement or running out of savings?", {}),
    ("Q3", "vector", "Did any client mention a liquidity need for a property purchase?", {}),
    ("Q8", "vector", "What is the eligibility for the structured note product?", {"kind": "kb"}),
    ("Q8", "vector", "How often must KYC be refreshed?", {"kind": "kb"}),
]
