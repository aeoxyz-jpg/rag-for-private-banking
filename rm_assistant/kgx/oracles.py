"""Hand-written, expert-idiomatic oracle queries per (engine x category) — the CAPABILITY
CEILING (spec §12.2). Run through the same executor/scorer as the LLM-authored queries to
separate 'can this engine answer the question class at all' from 'can the LLM author it'.

k_hop / shortest_path / household are PURE TRAVERSAL with unambiguous gold (from networkx) — the
oracles are exact and the verdict keys on these. ubo / controls encode a derived effective-ownership
semantic (not pure traversal); their oracles are best-effort majority-chain derivations and are
reported but NOT verdict-keyed (see spec §12.3)."""
from __future__ import annotations

from .questions import Question

# percent lives in relationships.attrs_json (SQL) / Rel.percent (Cypher)
_PCT_SQL = "CAST(json_extract(r.attrs_json,'$.percent') AS REAL)"


def sql_oracle(q: Question) -> str:
    p = q.params
    if q.category == "household":
        return ("SELECT src_id FROM relationships "
                f"WHERE rel_type='member_of_household' AND dst_id='{p['household']}'")
    if q.category == "k_hop":
        party, k = p["party"], p["k"]
        return f"""
WITH RECURSIVE bfs(id, d, path) AS (
  SELECT '{party}', 0, '|{party}|'
  UNION
  SELECT CASE WHEN r.src_id=b.id THEN r.dst_id ELSE r.src_id END, b.d+1,
         b.path || (CASE WHEN r.src_id=b.id THEN r.dst_id ELSE r.src_id END) || '|'
  FROM relationships r JOIN bfs b ON b.id IN (r.src_id, r.dst_id)
  WHERE b.d < {k}
    AND b.path NOT LIKE '%|' || (CASE WHEN r.src_id=b.id THEN r.dst_id ELSE r.src_id END) || '|%'
)
SELECT DISTINCT id FROM bfs WHERE d={k} AND id NOT IN (SELECT id FROM bfs WHERE d<{k})"""
    if q.category == "shortest_path":
        a, b = p["a"], p["b"]
        return f"""
WITH RECURSIVE bfs(id, d, path) AS (
  SELECT '{a}', 0, '{a}'
  UNION
  SELECT CASE WHEN r.src_id=x.id THEN r.dst_id ELSE r.src_id END, x.d+1,
         x.path || ',' || (CASE WHEN r.src_id=x.id THEN r.dst_id ELSE r.src_id END)
  FROM relationships r JOIN bfs x ON x.id IN (r.src_id, r.dst_id)
  WHERE x.d < 8
    AND ','||x.path||',' NOT LIKE '%,'||(CASE WHEN r.src_id=x.id THEN r.dst_id ELSE r.src_id END)||',%'
)
SELECT path FROM bfs WHERE id='{b}' ORDER BY d LIMIT 1"""
    if q.category == "ubo":
        return f"""
WITH RECURSIVE up(id) AS (
  SELECT '{p['entity']}'
  UNION
  SELECT r.src_id FROM relationships r JOIN up ON r.dst_id=up.id
  WHERE r.rel_type='owns_shares_in' AND {_PCT_SQL} >= 0.25
)
SELECT DISTINCT up.id FROM up JOIN nodes n ON n.node_id=up.id WHERE n.label='NaturalPerson'"""
    if q.category == "controls":
        return f"""
WITH RECURSIVE down(id) AS (
  SELECT '{p['person']}'
  UNION
  SELECT r.dst_id FROM relationships r JOIN down ON r.src_id=down.id
  WHERE r.rel_type='owns_shares_in' AND {_PCT_SQL} >= 0.25
)
SELECT DISTINCT down.id FROM down JOIN nodes n ON n.node_id=down.id WHERE n.label='LegalEntity'"""
    raise ValueError(q.category)


def cypher_oracle(q: Question) -> str:
    p = q.params
    if q.category == "household":
        return (f"MATCH (m:Node)-[r:Rel]->(h:Node {{id:'{p['household']}'}}) "
                "WHERE r.type='member_of_household' RETURN DISTINCT m.id")
    if q.category == "k_hop":
        party, k = p["party"], p["k"]
        if k == 1:
            return f"MATCH (a:Node {{id:'{party}'}})-[:Rel]-(b:Node) RETURN DISTINCT b.id"
        return (f"MATCH (a:Node {{id:'{party}'}})-[:Rel*1..{k-1}]-(near:Node) "
                f"WITH COLLECT(near.id)+['{party}'] AS seen "
                f"MATCH (a:Node {{id:'{party}'}})-[:Rel*{k}..{k}]-(b:Node) "
                "WHERE NOT b.id IN seen RETURN DISTINCT b.id")
    if q.category == "shortest_path":
        a, b = p["a"], p["b"]
        return (f"MATCH path = (a:Node {{id:'{a}'}})-[:Rel* SHORTEST]-(b:Node {{id:'{b}'}}) "
                "RETURN properties(nodes(path),'id') LIMIT 1")
    if q.category == "ubo":
        return (f"MATCH p = (person:Node)-[:Rel*1..6]->(e:Node {{id:'{p['entity']}'}}) "
                "WHERE person.label='NaturalPerson' "
                "AND ALL(rel IN relationships(p) WHERE rel.percent >= 0.25) "
                "RETURN DISTINCT person.id")
    if q.category == "controls":
        return (f"MATCH p = (person:Node {{id:'{p['person']}'}})-[:Rel*1..6]->(e:Node) "
                "WHERE e.label='LegalEntity' "
                "AND ALL(rel IN relationships(p) WHERE rel.percent >= 0.25) "
                "RETURN DISTINCT e.id")
    raise ValueError(q.category)
