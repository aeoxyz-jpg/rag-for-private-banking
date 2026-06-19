"""Phase-3b: compare the three semantic-layer storage representations. Prereq: data/rm.db built.
Run: `uv run scripts/eval/run_semrepr_eval.py`. Writes docs/experiments/semrepr_eval.md."""
from pathlib import Path

import yaml

from rm_assistant import ontology
from rm_assistant.semrepr import catalog, dbt_repr, equivalence, rdf_repr, report


def _metric_lines(text: str) -> int:
    return len([ln for ln in text.splitlines() if ln.strip()])


def _baseline_metric_lines() -> int:
    metrics = ontology.load()["metrics"]
    return _metric_lines(yaml.safe_dump(metrics, sort_keys=False))


def main() -> None:
    baseline_lines = _baseline_metric_lines()
    dbt_lines = _metric_lines(dbt_repr.SRC.read_text())
    rdf_lines = _metric_lines(rdf_repr.SRC.read_text())

    rows = []
    # baseline: composition is string-substitution; it stores dialect-locked SQL; queryable via ontology.load()
    base_comp = catalog.catalog("baseline")["composition"]
    rows.append(report.axis_scores("baseline (YAML+SQL)", {m: True for m in base_comp}, base_comp,
                                   queryable="yes", verbosity_lines=baseline_lines,
                                   baseline_lines=baseline_lines, generates_sql=False))
    rows.append(report.axis_scores("dbt-style", equivalence.check("dbt"),
                                   catalog.catalog("dbt")["composition"], queryable="yes",
                                   verbosity_lines=dbt_lines, baseline_lines=baseline_lines,
                                   generates_sql=True))
    rows.append(report.axis_scores("rdf", equivalence.check("rdf"),
                                   catalog.catalog("rdf")["composition"], queryable="yes",
                                   verbosity_lines=rdf_lines, baseline_lines=baseline_lines,
                                   generates_sql=False))

    Path("docs/experiments/semrepr_eval.md").write_text(report.to_markdown(rows, baseline_lines))
    for r in rows:
        print(f"  {r['repr']:20s} equiv={'all' if r['equivalence_all'] else 'FAIL'} "
              f"native={r['native_composites']}/2 verbosity={r['verbosity_ratio']}x "
              f"dialect={r['dialect']} -> {report.verdict(r)}")
    print("Wrote docs/experiments/semrepr_eval.md")


if __name__ == "__main__":
    main()
