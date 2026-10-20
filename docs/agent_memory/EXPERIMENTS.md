# Experiment Ledger

This ledger records observed results, not causal claims. “Strict” uses the denominator shown for that line.

## Research Graph baseline line (current)

All rows use the same frozen 56-task, base-description, no-hint protocol and a 1200-second per-task wall limit unless explicitly noted. Primary metric is strict/56.

| Gen | Ended / completed / timeout / other | Strict/56 | Mechanism evidence | Status and source |
| --- | --- | ---: | --- | --- |
| G0 | 56 / 50 / 6 / 0 | 33/56 | root control | Verified: `g000_evidence.json` |
| G1 | 56 / 54 / 0 / 2 | 30/56 | reserve bound 5/56 | Verified: `g001_evidence.json` |
| G2 | 56 / 54 / 2 / 0 | 30/56 | lifecycle localization untested for pre-event failure | Verified: `g002_graph.json` |
| G3 | 56 / 54 / 2 / 0 | 35/56 | supported structural concordance | Verified: `g003_safe_snapshot/g003_evidence.json`; attempt 1 DNS incident preserved |
| G4 | 56 / 53 / 3 / 0 | 34/56 | contradicted alignment prediction | Verified: `g004_safe_snapshot/g004_evidence.json` |
| G5 | 56 / 51 / 5 / 0 | 30/56 | supported diagnostics; reason-code subclaim remained untested | Verified: `g005_safe_snapshot/g005_evidence.json` |
| G6 | 56 / 53 / 3 / 0 | 37/56 | supported coarse timeout localization | Verified: `g006_safe_snapshot/g006_evidence.json`; highest observed score, not causal |
| G7 | 56 / 52 / 4 / 0 | 32/56 | supported last-pre-exec elapsed localization | Verified: `g007_safe_snapshot/g007_graph.json` |
| G8 | 56 / 53 / 3 / 0 | 35/56 | supported preterminal audit structure | Verified: `g008_safe_snapshot/g008_evidence.json` |
| G9 | 56 / 54 / 2 / 0 | 35/56 | supported later-turn gate structure | Verified: `g009_safe_snapshot/g009_evidence.json` |
| G10 | repaired view 56 / 55 / 1 / 0 | 32/56 supplementary; original 27/56 | contradicted directional outcome | Verified: `g010_safe_snapshot/g010_evidence.json`; user-authorized two-run repair, not one valid uninterrupted run |
| G11 | 56 / 53 / 3 / 0 | 35/56 | **untested**: authored record 0, guidance binding 0 | Verified: `g011_solution_loop_safe_snapshot/g011_solution_loop_evidence.json` |
| G12 | no formal run | none | bounded no-task runtime admission passed; no benchmark measurement | `g012_admission_005`; formal evaluation unauthorized |

G0-G11 Graphs are closed and immutable. G12 is not a formal Graph generation yet.

## G12 no-task evidence

- Interface investigation 1: 26 passed; bounded substrate feasible, action-specific interface still open.
- Interface investigation 2: 41 passed; structured action/status/opaque target visible in synthetic fixtures; real-model behavior unknown.
- Formal candidate full suite: 149 passed.
- Focused G12 suite: 33 passed.
- Candidate surface: 37/37 hashes independently rechecked; combined SHA matched.
- Formal run/benchmark/deployment: none. Provider/network access occurred only for the bounded synthetic admission described next.

Runtime admission history on 2026-10-20:

- Attempt 002 is preserved as an invalid probe attempt: its control detector included inherited G11 generic guidance and its 3-call live path ended without a valid record. It is not a G12 mechanism result.
- Attempts 003 and 004 failed in preflight before any provider call and remain preserved in the remote synthetic scratch.
- Attempt 005 passed in 3 real DeepSeek calls with no benchmark or database access: record attempts 1, accepted records 1, visible unique refs 1, directives 1. The directive was strictly parsed, exactly matched the runtime text and sidecar fields, and carried `acquire_evidence / empty_step / accepted / step / step_2 / none / evidence_gap / current`.
- The first classifiable post-directive action was `acquisition`, classified `consistent`. This is structural behavior only, not semantic correctness or benchmark benefit.
- The programmed enabled/disabled control matched dispatch arguments/results, termination, final result, and LLM-call count. Scoring did not run; the mechanism initiated zero tool calls; no answer was forced; no wall timeout was extended. Timing remains measurement-only.
- Sidecar, summary, and receipt privacy scans passed. Raw synthetic context remains only in isolated remote base logs and was not copied into the research package.
- Recheck: 149 focused passes; child full suite 302 passes and 5 failures; parent full suite 269 passes and the same 5 failures. No new test failure was introduced.

Status: **bounded no-task runtime admission passed; not benchmark-evaluated and not promoted**. Sources: both G12 `independent_verification.json` files, the formal `implementation_manifest.json`, source admission 001, and runtime admission 005.

Independent research control subsequently reviewed `g012_admission_005` and accepted the bounded no-benchmark admission as PASSED. This acceptance does not authorize or imply a formal 56-task evaluation, benchmark effect, Graph promotion, or G13 implementation.

## Older half-56 campaign (historical)

Campaign: `dataset17_half56_deepseek_v1_20261011`. Its historical reporting often used strict/non-timeout-completed; do not compare those rates directly with strict/56 above.

| Run | Result | Main interpretation |
| --- | --- | --- |
| Baseline v2 | 53 completed; 3 operator-terminated IMDb tasks; 33 strict, 50 strict-evaluated | Historical control; 33/53 user denominator or 33/56 all-task denominator must be labeled |
| Gen1 | 50 completed, 6 timeout; 33/47 strict-evaluated | No task gain |
| Gen2 | 52 completed, 4 timeout; 29/49 strict | SQL memo replayed 0 times; integrated but not activated |
| Gen3 | 52 completed, 4 timeout; 30/49 strict | Error-observation-triggered repair; first candidate violated the sealed scope and was revised before evaluation |
| Gen4 | 52 completed, 4 timeout; 27/49 strict | Ledger active, but 493 extraction fail-opens and very large contexts |
| Gen5 | 51 completed, 5 timeout; 27/48 strict | Six provider/protocol errors |
| Gen6 | 50 completed, 6 timeout; 35/47 strict; 35/50 user denominator | Historical best of this campaign; protocol fixed, but long trajectories remained |
| Gen7 | 52 completed, 4 timeout; 32/50 strict | Governor reached only 7/52; source guard missed the known long case |
| Gen8 | 50 completed, 6 timeout; 27/50 strict user denominator | Cost-normalized trigger; repair count 0; worse than Gen6 |
| Gen9 | 48 completed, 8 timeout; 30/48 strict user denominator | 1 mechanism trigger in 2,673 checks; 62.5% |
| Gen10 | 51 completed, 5 timeout; 34/51 strict | 0 usable labels/mismatches/notes; integrated not activated |
| Gen11 | 50 completed, 6 timeout; 35/50 strict | Historical tie with Gen6 on user denominator |
| Gen12 | 49 completed, 7 timeout; 33/46 strict-evaluated | Referent-scoped dispatch obligation; did not exceed Gen6/Gen11 on the fixed cohort |
| Gen13 | 50 completed, 6 timeout; 31/50 strict | 150 probes, 34 literals, 0 confirmed; no gain |
| Gen14 | 52 completed, 4 timeout; 32/52 strict | Runtime recovery activated, but below baseline; separate hint ablation is not no-hint Graph evidence |
| Gen15 original | 56 completed, 0 timeout; 5/56 strict | Handoff mechanism effectively did not operate: 0 context rebuilds/composition requests in the original run |
| Gen16 | 48 completed, 8 timeout; 28/48 strict | Digest mechanism; no validated gain |
| Gen17 | 48 completed, 8 timeout; 29/48 strict | Referent materialization observed but no validated gain |
| Gen18 | 50 completed, 6 timeout; 32/50 strict | Corrected re-execution count 0 |
| Gen19 | 48 completed, 8 timeout; 32/48 strict | 2,312 observations mined, 228 failures, 0 repairs/re-executions |

Sources: current `generations/gen_XXX/result.json` files and session checkpoints `S:21792`, `S:30590`, `S:33437`, `S:41464`, `S:42907`, `S:46874`, `S:49382`, `S:52505`. Status: **historical artifact-backed**, but not re-run during migration.

### Gen15 repair-branch lessons

- r1 was stopped after widespread DeepSeek 503; it is invalid infrastructure evidence, not a formal score.
- r2: 12/52 strict; r4: 9/56; r5: 16/56; r6: 12/55; r7: 12/55; r8: 12/54.
- Repairs progressively established seal/rebuild, Phase B delivery, bounded verification compression, and protocol invariants, but task performance stayed poor.
- The result overturned the belief that making a complex handoff mechanism reachable necessarily improves answers.

Sources: session `S:52505`, `S:56491`, `S:59494`, `S:60790`, `S:61923`, `S:63129`, `S:64125`. Status: **historical, completed/invalid status preserved per branch**.

## Invalid or special cases that must remain separate

- G3 attempt 1: DNS/API connection failure; hypothesis not tested.
- G10 original: five pre-model PostgreSQL load failures; original score preserved; repaired view explicitly supplementary.
- Gen15 r1: provider 503 and manual stop; no terminal formal result.
- Official-hint ablation: separate input ablation, not part of no-hint Research Graph evidence.
- Any mixed recovery or selected rerun must not replace the original frozen run.
