from evolution_core.lineage import LineageGraph
from evolution_core.models import ExecutionEvidence, EvolutionRecord, Intent, Review, SourceVersion


def test_result_is_attached_to_child_not_a_node():
    parent = SourceVersion("p", "a" * 64)
    child = SourceVersion("c", "b" * 64, parent_version_id="p", generation=1)
    graph = LineageGraph(campaign_id="t", initial_parent=parent)
    record = EvolutionRecord(
        "r", 1, parent, child,
        Intent("i", "m", "limitation", "mechanism", "behavior"),
        ExecutionEvidence("run", "c", "batch", metrics={"pass": 1}),
        Review("effective", "implemented", task_effect="improved", parent_decision="promote_candidate"),
    )
    graph.append(record)
    snapshot = graph.snapshot()
    assert len(snapshot["records"]) == 1
    assert {item["version_id"] for item in snapshot["source_versions"]} == {"p", "c"}
    assert snapshot["records"][0]["child_evidence"]["metrics"]["pass"] == 1
    assert "result" not in snapshot["records"][0]


def test_hash_chain_and_parent_continuity():
    parent = SourceVersion("p", "a" * 64)
    graph = LineageGraph(campaign_id="t", initial_parent=parent)
    child = SourceVersion("c", "b" * 64, parent_version_id="p", generation=1)
    graph.append(EvolutionRecord("r", 1, parent, child, Intent("i", "m", "l", "m", "b"), ExecutionEvidence("run", "c", "b"), Review("inconclusive", "unknown")))
    assert graph.head_sha256
    assert graph.snapshot()["head_version_id"] == "c"
