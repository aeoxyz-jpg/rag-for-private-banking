"""Pillar D-lite — Customer-360 / pre-meeting brief (spec §4.1, §4.3). A deterministic
template filled from the structured warehouse + governed metrics + the client's latest
interactions and notes, then an LLM narrative. Answers Q4 ("summarize everything about
client X before the meeting") without the cost of a full RAPTOR tree.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import config, db, ontology
from ..models.ollama import OllamaLLM
from ..synth import facts


@dataclass
class Brief:
    client_id: int
    profile: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    recent_interactions: list[dict] = field(default_factory=list)
    recent_docs: list[dict] = field(default_factory=list)
    narrative: str = ""


def _client_metric(conn, name: str, client_id: int):
    sql = f"SELECT * FROM ({ontology.metric_sql(name)}) WHERE client_id = :cid"
    row = conn.execute(sql, ontology.metric_binds(sql, cid=client_id)).fetchone()
    return row[1] if row else None


def build(client_id: int, model: str = config.REASON_MODEL, narrate: bool = True) -> Brief:
    conn = db.connect(readonly=True)
    b = Brief(client_id=client_id)
    b.profile = facts.client_facts(conn, client_id)
    b.metrics = {
        "aum": _client_metric(conn, "aum", client_id),
        "days_since_contact": _client_metric(conn, "days_since_contact", client_id),
        "churn_risk": _client_metric(conn, "churn_risk", client_id),
        "share_of_wallet": _client_metric(conn, "share_of_wallet", client_id),
    }
    b.recent_interactions = [dict(r) for r in conn.execute(
        "SELECT ts, channel, type, sentiment FROM interactions "
        "WHERE client_id=? ORDER BY ts DESC LIMIT 5", (client_id,))]
    b.recent_docs = [dict(r) for r in conn.execute(
        "SELECT doc_id, kind, ts, substr(text,1,400) AS text FROM documents "
        "WHERE client_id=? ORDER BY ts DESC LIMIT 5", (client_id,))]
    conn.close()

    if narrate:
        b.narrative = OllamaLLM(model).complete(
            f"STRUCTURED PROFILE:\n{b.profile}\n\nGOVERNED METRICS:\n{b.metrics}\n\n"
            f"RECENT INTERACTIONS:\n{b.recent_interactions}\n\n"
            f"RECENT NOTES:\n{b.recent_docs}\n\n"
            "Write a tight pre-meeting brief for the relationship manager: who the client is, "
            "portfolio/wealth snapshot, recent themes from notes, open opportunities/risks, and "
            "2-3 suggested talking points. Ground every claim in the data above.",
            system="You write private-banking pre-meeting briefs. Be concise and specific.",
            temperature=0.3)
    return b


def to_markdown(b: Brief) -> str:
    p, m = b.profile, b.metrics
    aum = f"${m['aum']:,.0f}" if m.get("aum") is not None else "n/a"
    churn = f"{m['churn_risk']:.2f}" if m.get("churn_risk") is not None else "n/a"
    lines = [
        f"# Customer-360 — {p.get('name')} (client {b.client_id})",
        f"- Segment **{p.get('segment')}** · risk {p.get('risk_profile')} · "
        f"KYC {p.get('kyc_status')} · since {p.get('client_since')} · {p.get('district')}",
        f"- **AUM {aum}** · days since contact {m.get('days_since_contact')} · churn-risk {churn}",
        f"- Portfolio mix: {p.get('portfolio_mix')}",
        f"- Loans: {len(p.get('loans', []))} · open leads: {p.get('open_leads')}",
        "", "## Pre-meeting brief", b.narrative,
    ]
    return "\n".join(lines)
