"""Phase-2: build the greenfield wealth graph and write all three projections.
Run: `uv run scripts/build/build_wealth_graph.py`"""
from rm_assistant import config
from rm_assistant.wealthgraph import builder, graph_export, ground_truth, relational


def main() -> None:
    print(f"Building canonical wealth graph (seed={config.SEED})")
    g = builder.build_canonical(config.SEED)
    print(f"  nodes={g.number_of_nodes()}  edges={g.number_of_edges()}")
    rel = relational.project_relational(g, config.WEALTH_DB)
    print(f"  relational -> {config.WEALTH_DB}  {rel}")
    exp = graph_export.export_graph(g, config.WEALTH_GRAPH_DIR)
    print(f"  graph export -> {config.WEALTH_GRAPH_DIR}  {exp}")
    gt = ground_truth.emit_ground_truth(g, config.WEALTH_TRUTH, config.WG_UBO_THRESHOLD)
    print(f"  ground truth -> {config.WEALTH_TRUTH}  "
          f"(ubo={len(gt['ubo'])}, households={len(gt['household_members'])}, "
          f"paths={len(gt['shortest_paths'])})")


if __name__ == "__main__":
    main()
