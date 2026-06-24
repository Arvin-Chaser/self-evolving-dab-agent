# next_data_agent_repair_seed

- source_candidate: `codex_qwen_patents_iter003_v4_structured_patch_spec_retry2`
- case_id: `PATENTS_query1`
- selected_stage: `metadata_parser`
- selected_signal: `no_years_found`
- original_dab_validation_passed: `False`
- validation_reason: `missing_final_answer_file_or_empty_answer`

## Recommended goal

Repair the data-agent side for PATENTS_query1 so CPC level-5 mapping, filing-date year extraction, EMA/best-year calculation, and final answer generation produce a non-empty validated answer.

## Focus areas

- CPC definition metadata grounding
- CPC level-5 mapping logic
- filing_date year extraction
- EMA/best-year calculation path
- final_answer non-empty contract
