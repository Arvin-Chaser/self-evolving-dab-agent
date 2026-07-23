# Full-trace observer architecture

## Why this exists

The current research goal is to test whether fine-grained feedback helps a meta-agent evolve better DAB data agents. Earlier iterations mixed several things together: deterministic analyzers, fixed evidence packs, hand-written error categories, and meta-agent repair prompts. That made the feedback useful, but too pre-shaped.

The new architecture separates the pipeline into three layers:

```text
DAB DataAgent execution
  -> full_execution_trace.jsonl
  -> Fine-Grained ObserverAgent feedback
  -> MetaAgent repair seed / archive selection / candidate generation
```

## Layer 1: full execution trace

`experiments/run_dab_tool_agent.py` produces `full_execution_trace.jsonl` during run normalization.

This file is intended to be a stable, deterministic behavior record. It should capture what happened, not decide why it happened. Current event families include LLM requests/responses, tool call start/end, and agent termination.

This layer is deliberately not the main place for human-designed failure taxonomies. It is closer to a flight recorder.

## Layer 2: Fine-Grained ObserverAgent

`experiments/run_fine_grained_observer_agent.py` reads raw run behavior, especially `full_execution_trace.jsonl`, and asks an LLM observer to produce flexible fine-grained feedback.

The observer output includes:

- `failure_narrative`
- `evidence_chain`
- `inferred_failure_mechanisms`
- `answer_quality_shape`
- `repair_affordances`
- `logging_gaps`
- `next_observation_requests`
- `confidence`

The important point: the observer is the component that generates fine-grained feedback. It is not just comparing parent/child after another analyzer has already decided the failure category.

## Layer 3: MetaAgent usage

`experiments/run_meta_agent_evolution_loop.py` injects the observer output into `repair_seed.json` as:

- `observer_generated_feedback`
- `observer_generated_feedback_path`
- `observer_raw_behavior_input_path`
- `fine_grained_feedback.observer_generated_feedback`

The meta-agent can then use this feedback to decide what to repair. In future experiments, the meta-agent should also be allowed to evolve observer-facing prompt/scripts, so the feedback-generation process itself can improve without hard-coding a fixed human taxonomy.

## Experimental comparison groups

A clean research comparison should include at least three modes:

1. Result-only evolution: meta-agent sees answer correctness/metrics only.
2. Full-trace direct evolution: meta-agent reads the full trace directly, similar in spirit to very raw trace exposure.
3. Observer-feedback evolution: observer reads full trace and generates compact, flexible fine-grained feedback for the meta-agent.

This lets us test whether the observer layer is better than both coarse correctness-only feedback and unfiltered trace dumping.

## Legacy boundary

The old one-shot `generated_solve.py` chain and fixed evidence-pack builders are archived under `legacy/cleanup_20260724_observer_trace_realign/`. Active code should not import them.
