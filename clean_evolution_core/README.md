# Clean Agent Evolution Core

This directory is the benchmark-neutral experimental core extracted from the
DAB evolution work. It contains the reusable evolution mechanism and leaves
task execution, scoring, datasets, prompts, credentials, and benchmark
validators to adapters supplied by a particular experiment.

The intended loop is:

1. Execute a parent source on a fixed development batch.
2. Record workflow and runtime observations.
3. Normalize observations into bounded feedback and evidence cards.
4. Let a meta-agent read the accumulated lineage and choose one mechanism to
   implement.
5. Create an isolated child source workspace and admit it after source checks.
6. Execute the child on the same batch and attach the execution evidence to
   that generation.
7. Review implementation, activation, behavioral effect, and task effect.
8. Write both parent and child source records to the append-only lineage. The
   next meta-agent reads this state and chooses which source to continue from.

The lineage does not create a node for a result. A result is evidence attached
to the child generation. A parent and a child are source versions; an intent,
execution evidence, and review describe the transition between them.

## Package layout

- `evolution_core/models.py`: immutable records and canonical hashing.
- `evolution_core/observer.py`: bounded JSONL workflow/runtime observation.
- `evolution_core/feedback.py`: benchmark-neutral feedback cards.
- `evolution_core/interfaces.py`: runner, evaluator, and meta-agent contracts.
- `evolution_core/workspace.py`: isolated source snapshots and admission.
- `evolution_core/lineage.py`: append-only parent/child lineage and selection
  context.
- `evolution_core/loop.py`: orchestration shell that delegates execution and
  scoring to adapters.
- `examples/minimal_workflow.py`: a small in-memory integration example.

## Adding a benchmark

Implement `RunnerAdapter.run`, `EvaluatorAdapter.evaluate`, and
`MetaAgentAdapter.propose`. Pass the adapters to `EvolutionLoop`. The adapter
may use a benchmark's own task manifest, database, validator, and prompt, but
those details must stay outside this package. ADB can therefore reuse this
workflow without importing DAB or PATENTS code.

## What is intentionally absent

There are no DAB query IDs, PATENTS/CPC rules, gold answers, validators,
benchmark prompts, Docker images, provider credentials, logs, traces, archived
candidates, or ADB bridge scripts in this export.

This directory is mirrored in the `clean_evolution_core/` directory of the
`Arvin-Chaser/self-evolving-dab-agent` GitHub repository. The export remains
benchmark-neutral and can be copied into an ADB adapter project without
importing DAB-specific files.
