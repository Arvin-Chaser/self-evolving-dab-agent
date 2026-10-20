# Intent-to-candidate source workspace

This opt-in path targets the pre-evaluation bottleneck: turn a sealed DAB intent
into a coherent, executable source patch. It does not run DAB questions or make
an A/B comparison. It does not alter the historical M2.6 campaign.

`experiments/intent_candidate_workspace.py` has three steps:

1. `prepare` verifies the intent and bounded parent source-tree hash, copies only active DAB source,
   prompts, adapters, and tests, and writes a compact implementation brief. It
   excludes datasets, answer files, logs, old campaigns, and credentials from
   the candidate source snapshot. If available, it also provides the single
   upstream `DataAgent.py` source file as read-only dispatch-path context.
2. `generate` optionally runs Codex in that workspace and makes one in-place
   repair attempt after a failed source preflight. The model and profile can be
   selected explicitly. On Windows, its task specifies the tested direct
   `codex --codex-run-as-apply-patch` route for edits; the `.bat` wrapper,
   inline Python writes, and `Set-Content` are not the candidate edit path.
   This is a coding session, not a DAB evaluation.
3. `audit` checks the changed-file scope, requires a mapping from mechanism
   claims to changed implementation source, compiles changed Python, and runs
   the exact `experiments/run_dab_tool_agent.py --help` script entrypoint. It
   writes `candidate.patch`, `candidate_admission.json`, and, on failure,
   `repair_task.md`.

Example using the archived Gen8 sealed intent only as a workspace smoke input:

```powershell
$campaign = 'experiments/dab_fixed_signal_feedback/key_handoff_harness_v2/meta_memory_v1/intent_sealed_open_implementation_v1_20260926'
$workspace = 'tmp/intent_candidate_workspace_gen8'
python experiments/intent_candidate_workspace.py prepare --intent "$campaign/frozen_inputs/sealed_intent.json" --parent-source "$campaign/frozen_inputs/parent_candidate_007.py" --mechanism-contract "$campaign/mechanism_contract.json" --output $workspace
python experiments/intent_candidate_workspace.py generate --workspace $workspace --model YOUR_CODING_MODEL
python experiments/intent_candidate_workspace.py audit --workspace $workspace
```

New multi-file roadmap campaigns omit `--parent-source`. In that mode the
sealed intent is bound to a canonical hash of the entire bounded active source
surface copied into the candidate repository. The legacy single-file option is
retained only to replay historical sealed intents.

`generate` has no wall-clock deadline by default. Pass a positive `--timeout`
only for an explicitly bounded diagnostic run.

The workspace is a source-level information boundary, not an OS-level read
isolation mechanism: the coding model must honor its `AGENTS.md` boundary.
`source_preflight_passed` is not proof that the mechanism works or that query
accuracy improved. Before any formal evaluation, inspect the source patch and
run mechanism-focused tests against the actual dispatch path.

On the 2026-09-28 DeepSeek trial, the verified direct patch route produced a
standalone `granularity_selector.py`, but the bounded session did not integrate
it into the active runner or provide a claim-to-source report. The audit
rejected the candidate; no formal DAB evaluation was run. This distinguishes
the repaired Windows edit path from the still-open intent-to-candidate quality
problem. The audit subprocess explicitly decodes UTF-8 output because Windows
locale decoding can otherwise crash while reading a non-ASCII patch.
