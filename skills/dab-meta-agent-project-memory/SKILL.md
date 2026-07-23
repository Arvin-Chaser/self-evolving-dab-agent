---
name: dab-meta-agent-project-memory
description: Use when Codex-Qwen acts as the meta-agent for DAB/PATENTS data-agent prompt evolution. Provides project memory, current best-parent state, anti-regression rules, and candidate quality discipline for archive-based evolution.
---

# DAB Meta-Agent Project Memory

Use this skill before proposing any DAB/PATENTS data-agent prompt repair candidate.
This skill has priority over generic PATENTS prompt-repair heuristics when they conflict.

## Current Best Parent State

The current best parent lineage is the iter021 shadow parent:

- `data_agent_shadow_codex_qwen_patents_iter021_copy_data_block_repair_iter001_20260626_045925`

The best known parent run from this lineage already improved beyond parser bootstrapping:

- It parses CPCDefinition metadata.
- It has non-empty CPCDefinition rows.
- It has non-empty parents mappings.
- It can produce a non-empty answer.
- It reached roughly partial-answer quality, not empty-answer/parser-bootstrap quality.

Therefore, do not assume the current bottleneck is basic CPCDefinition parsing unless the active repair seed/runtime evidence explicitly says so.

## Anti-Regression Rules

If the parent already has a non-empty partial answer, avoid prompt changes that are likely to regress the child into empty-answer, parser failure, or generated-code runtime exceptions.

Bad candidate patterns include vague instructions such as:

- "only include symbols explicitly present in metadata with level == 5"
- "ensure the final output contains only level == 5 symbols"
- "strictly filter to metadata level 5"
- "do not include fallback-derived symbols"
- "avoid string-based fallback" without a concrete alternative tied to current runtime evidence

These may be valid only when the active seed proves that the current parent output contains non-level-5 or fallback-derived extra symbols and the patch also preserves the already-working parser path.

## Required Candidate Rationale

A useful patch_spec rationale must state all of the following:

- what the parent already does correctly;
- what concrete current failure remains;
- why the edit targets that remaining failure rather than re-solving an old parser/bootstrap failure;
- why the edit should preserve the non-empty partial-answer behavior.

If the candidate cannot explain this, output `no_op_failed`.

## Current Repair Focus Discipline

Prefer repairs tied to current parent/child delta and answer-diff evidence, such as:

- missing-vs-extra class analysis;
- EMA year calculation over filing years;
- ranking/tie handling;
- preserving correct parser and mapping coverage while narrowing a specific observed error;
- runtime logging that reveals why known missing gold codes were excluded.

Do not repeat old fixes for:

- quoted COPY headers;
- COPY data block termination;
- escaped parents parsing;
- generic CPC level definitions;
- stale `log_exception(exc)` API guidance;

unless the active runtime evidence shows that exact failure has reappeared.

## No-Op Rule

If the active context only supports a vague strict-filtering or generic level-5 instruction, output:

```json
{"status": "no_op_failed", "reason": "current evidence is insufficient for a safe improvement over the non-empty partial-answer parent"}
```

## Local WSL Network Memory

When running DAB/DataAgent or Qwen/DashScope smoke tests from WSL, do not rely on
the Windows TUN/fake-ip route alone. We observed `dashscope.aliyuncs.com`
resolving through a `198.18.x.x` fake-ip path where TCP connected but TLS failed
with `SSL_ERROR_SYSCALL` / `UNEXPECTED_EOF_WHILE_READING`.

Use the Windows proxy explicitly from WSL:

```bash
export http_proxy="http://172.17.240.1:17891"
export https_proxy="http://172.17.240.1:17891"
export HTTP_PROXY="http://172.17.240.1:17891"
export HTTPS_PROXY="http://172.17.240.1:17891"
export all_proxy="http://172.17.240.1:17891"
export ALL_PROXY="http://172.17.240.1:17891"
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="localhost,127.0.0.1,::1"
```

Windows-side proxy address is `127.0.0.1:17891`; WSL reaches it through
`172.17.240.1:17891`. A Windows `curl.exe` request through
`-x http://127.0.0.1:17891` reaching `HTTP/1.1 404 Not Found` for
`/compatible-mode/v1` is a successful network/TLS test; the path itself is not a
homepage.
