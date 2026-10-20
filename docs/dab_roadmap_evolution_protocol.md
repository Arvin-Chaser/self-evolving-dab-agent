# DAB roadmap evolution protocol

This is the active single-lineage protocol for improving a data-agent harness
on a frozen, non-full DAB evolution batch before evaluating generalization on
the full benchmark.

The lifecycle is:

```text
compact roadmap snapshot
  -> 3-5 sealed competing intent hypotheses
  -> independent intent selection
  -> sealed mechanism intent
  -> source-only candidate workspace
  -> source admission
  -> fixed-batch DAB evaluation
  -> trace-backed result
  -> fact-only causal diagnosis
  -> compact append-only roadmap node
```

`experiments/dab_roadmap_protocol.py` owns the campaign state machine. It does
not silently promote every candidate. Source reuse is an evidence-backed
annotation; the next generation independently selects its code and evidence
parents. Information from a failed generation remains in the graph even when
its code is not inherited.

## Information boundary

The diagnosis Meta agent receives the compact result and roadmap and emits no
next-step recommendation. Its causal card covers opportunity, integration,
activation, delivery, model uptake, downstream behavior, and task effect;
every link is marked `positive`, `measured_zero`, `unknown`, or `confounded`.
The card also records the failure boundary, falsified and unsupported claims,
excluded equivalence classes, and open discriminators.

After diagnosis is appended, a fresh Meta invocation generates three to five
complete competing intents without ranking them. A second fresh invocation
compares that sealed pool and selects one ID without editing or merging the
proposals. The pool, every rejection reason, and the final selection are
content-bound to the sealed intent and retained as immutable artifacts. No
fixed intervention-scale or mechanism-family taxonomy is imposed.

Each graph node contains the compact causal diagnosis and intent-competition
summary plus immutable links to the sealed intent, candidate reference, result,
full diagnosis, hypothesis pool, selection, and batch summary. Detailed
evidence is therefore available without placing every historical trace in the
default context.

The coding meta-agent receives a bounded source snapshot, sealed intent, source
tree manifest, optional mechanism contract, and read-only upstream dispatch
source. It does not receive benchmark answers, validators, credentials, prior
formal traces, or held-out outcomes.

## Time limits

Diagnosis, hypothesis generation, intent selection, and candidate coding/repair
are Codex meta-agent calls with no subprocess wall-clock deadline. Candidate generation passes
`timeout=0` explicitly. DAB data-agent runs remain bounded by
`max_agent_iterations`, because that is part of the evaluated agent protocol
rather than a deadline on the meta-agent.

## Candidate evaluation

An admitted candidate is evaluated from its own source snapshot, not by
patching the shared checkout. Use the shared virtual environment explicitly:

```bash
/srv/text2sql/.venv/bin/python \
  CAMPAIGN/generations/gen_001/candidate_workspace/repo/experiments/run_multi_query_baseline.py \
  --python /srv/text2sql/.venv/bin/python \
  --batch FROZEN_EVOLUTION_BATCH.json \
  --registry /srv/text2sql/dab_corpus/registry.json \
  --dab-root /srv/text2sql/external/DataAgentBench_official \
  --dab-upstream-root /srv/text2sql/external/DataAgentBench_official \
  --output-root CAMPAIGN/evaluations \
  --run-id gen_001 \
  --use-base-db-description \
  --skip-observer \
  --max-iterations 20
```

The batch runner now resolves registry paths against the deployed DAB root and
records the exact candidate runner hashes and interpreter in its summary.

## Required gates

A generation cannot advance unless:

1. the intent is hash-bound to the current code parent and roadmap snapshot;
2. the candidate passes changed-file, compile, entrypoint, and claim-to-source
   admission checks;
3. the result uses exactly the frozen evolution query IDs;
4. the diagnosis supplies every causal-chain link without a recommended patch;
5. the intent comes from a validated 3-5 proposal pool and the independent
   selector accounts for every proposal exactly once; and
6. the append-only roadmap hash chain verifies after the new node is written.

The full DAB set must not be supplied to intent selection or candidate coding.
It is reserved for evaluating the frozen best candidate after the evolution
campaign has reached a satisfactory result.
