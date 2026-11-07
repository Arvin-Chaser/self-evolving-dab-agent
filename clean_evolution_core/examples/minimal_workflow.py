"""In-memory example showing parent/child lineage and attached evidence."""

from pathlib import Path

from evolution_core.lineage import LineageGraph
from evolution_core.models import ExecutionEvidence, EvolutionRecord, Intent, Review, SourceVersion


def main() -> None:
    parent = SourceVersion("source_000", "a" * 64)
    graph = LineageGraph(campaign_id="demo", initial_parent=parent)
    child = SourceVersion("source_001", "b" * 64, parent_version_id=parent.version_id, generation=1, changed_files=("agent.py",))
    intent = Intent("intent_001", "bounded_retry", "repeated transient failures", "retry one safe operation once", "recover transient failures")
    evidence = ExecutionEvidence("run_001", child.version_id, "batch_001", metrics={"score": 0.5}, observations=({"event": "retry", "status": "success"},))
    review = Review("effective", "implemented", ("retry event reached the runner",), "one recovery observed", "score improved", "continue from child", "promote_candidate")
    graph.append(EvolutionRecord("gen_001_intent_001", 1, parent, child, intent, evidence, review))
    print(graph.snapshot())


if __name__ == "__main__":
    main()
