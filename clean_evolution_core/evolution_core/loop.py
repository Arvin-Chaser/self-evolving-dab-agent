"""Generic orchestration shell; benchmark adapters own execution and scoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .feedback import build_feedback
from .interfaces import EvaluatorAdapter, MetaAgentAdapter, RunnerAdapter, SourceBuilder
from .lineage import LineageGraph
from .models import EvolutionRecord, SourceVersion, digest


class EvolutionLoop:
    def __init__(self, *, graph: LineageGraph, runner: RunnerAdapter, evaluator: EvaluatorAdapter, meta_agent: MetaAgentAdapter, source_builder: SourceBuilder, output_root: Path):
        self.graph = graph
        self.runner = runner
        self.evaluator = evaluator
        self.meta_agent = meta_agent
        self.source_builder = source_builder
        self.output_root = Path(output_root)

    def run_generation(self, *, batch_id: str, parent: SourceVersion | None = None) -> EvolutionRecord:
        if parent is None:
            selector = getattr(self.meta_agent, "select_parent", None)
            selected_id = selector(lineage_context=self.graph.snapshot()) if selector else None
            parent = self.graph.source_by_id(selected_id) if selected_id else (
                self.graph.records[-1].child if self.graph.records else self.graph.initial_parent
            )
        generation = len(self.graph.records) + 1
        parent_dir = self.output_root / f"generation_{generation:03d}" / "parent"
        parent_evidence = self.runner.run(parent, batch_id=batch_id, output_dir=parent_dir)
        parent_eval = self.evaluator.evaluate(parent_evidence)
        feedback = build_feedback(run_id=parent_evidence.run_id, source_version_id=parent.version_id, observations=list(parent_evidence.observations), metrics=parent_eval)
        intent = self.meta_agent.propose(parent=parent, feedback=feedback, lineage_context=self.graph.snapshot())
        child_dir = self.output_root / f"generation_{generation:03d}" / "child"
        child = self.source_builder.build(parent=parent, intent=intent, output_dir=child_dir)
        child_evidence = self.runner.run(child, batch_id=batch_id, output_dir=child_dir / "run")
        child_eval = self.evaluator.evaluate(child_evidence)
        review_data = self.meta_agent.review(intent=intent, parent=parent, child=child, evidence=child_evidence, evaluation=child_eval)
        from .models import Review
        review = Review(**review_data)
        record = EvolutionRecord(
            record_id=f"gen_{generation:03d}_{intent.intent_id}",
            generation=generation,
            parent=parent,
            child=child,
            intent=intent,
            child_evidence=child_evidence,
            review=review,
            previous_record_sha256=self.graph.head_sha256,
        )
        self.graph.append(record)
        (self.output_root / "lineage.jsonl").parent.mkdir(parents=True, exist_ok=True)
        (self.output_root / "lineage.jsonl").write_text(self.graph.to_jsonl(), encoding="utf-8")
        return record
