# Single-entry Meta workflow

Entry point: `experiments/dab_meta_pipeline_v1.py`.

This is the complete **Meta-side** chain, not a claimed complete Data/evolution
cycle: native health check → independent review → original validated Graph
append → independent full-Graph selector → original sealed intent → independent
coding → original source/frozen compatibility audits → at most two independent
same-intent repairs → original candidate admission → explicit Data handoff.
Mode `review` stops after Graph. Mode `candidate` starts at an already reviewed
Graph. Mode `review_then_candidate` connects both when the next generation has
separate human/campaign authority. No source implementation or research judgment
is supplied by the orchestration controller.

## One command, not alternating desktop/terminal sessions

After the actual native model/tool integration gate passes, use the bundled
Python to run the entry point with `--start`, `--campaign`,
`--run <campaign>/meta_workflows/<unique-name>`, `--mode`, `--authority`, and the
explicit `--review-generation` / `--candidate-generation` for that mode. This
prepares and runs in the same invocation. The command can be dispatched from
the desktop chat after normal scoped approval; no instruction to close Codex.
Running the same command again reuses **verified completed** receipts, not paid
sessions. An abandoned execution lock or dispatch without a completed receipt
requires reconciliation and is never replayed. `--status --campaign ...` is
model-free. Preparation refuses an active/admitted Gen9 and cannot authorize
Gen10 or alter campaign generation limits.

The entry point does not record a Data result, stage a runtime, upload keys,
launch evaluations, contact SSH, resume automations, or silently start a new
generation. Data must first have its final health/state audit and original
result recorded. A newly admitted child needs its own candidate-specific
runtime, source/input audit, and separately authorized evaluation dispatch.

## Windows native coexistence

Observed failure: legacy elevated setup refresh could not open the desktop
`node_repl.exe` ACL target (Windows sharing error 32). Merely removing an
environment variable did not prevent this. The old process-presence rule is
historical; the new entry measures actual native health instead.

New commands explicitly request both `windows.sandbox="mxc"` and
`features.prefer_mxc=true`, following the documented preference mechanism.
**Current deployment remains BLOCKED:** both actual model-driven probes still
entered legacy setup and failed. The preference flag did not resolve the
installed CLI's unified-exec path. Direct sandbox probes passed, but they do
not establish native model/tool integration. The entry point refuses any paid
stage before a real independently audited successful native integration proof.
These are child invocation settings, not edits to global config,
ACLs, accounts, firewall, approval policy or managed requirements. There is no
fallback to unelevated/full-access and no retry after command failure. Runtime
read/write, PowerShell, read-only write denial and disabled network denial are
tested before a model call. Actual native model/provider/permission/grant
metadata is still audited by the existing independent native verifier.

Evidence lives in fresh `tmp/mh_*/report.json` and
`tmp/meta_native_mxc_v1` / `tmp/meta_native_mxc_v2`. The failed first native probe
remains preserved. A standalone sandbox success is not sufficient evidence for
actual model-driven tools; check the latest native probe report separately.

## Failure routing and cost control

- Candidate validation failures produce compact synthetic diagnostics and seed
  a fresh independent repair session with the exact failed source and sealed
  intent. Failed attempts remain immutable. The selector is not rerun.
- Transport, permission, setup, infrastructure and ambiguous process failures
  stop; they do not trigger automatic API retries or candidate modification.
- Original tests/validators/protocols remain unchanged. Config changes are
  rejected except CLI-created trust-only records for exact newly prepared
  workspaces. No new project hooks or `.codex` layers are accepted.
- Stage intents precede effects; completed receipts bind actual artifacts.
  Evidence changes or unknown execution status fail closed.
- Full Graph and approved indexed safe details are available to Meta; benchmark
  identifiers, rows, answers and raw traces are not. Missing activation remains
  UNKNOWN; cross-model/runtime comparisons are not causal evidence.

Offline workflow fault tests: `tests/test_dab_meta_pipeline_v1.py`. These test the
entire control sequence and failures without real models, Graph mutations,
benchmark execution, credentials or network. They do not prove a future real
research generation will pass its candidate or provider gates.

Official implementation guidance:
https://learn.chatgpt.com/docs/windows/windows-sandbox
