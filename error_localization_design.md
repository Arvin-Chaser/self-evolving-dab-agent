# Error Localization Design

This project uses an 8-stage schema to localize failures in a Data Agent / Text-to-SQL agent execution process.

The goal is not only to know that the final answer is wrong, but to identify which stage of the agent pipeline likely caused the failure.

## 8-Stage Agent Execution Schema

### S1: Task Understanding

The agent interprets the user query and extracts the main task intent.

Common errors:
- intent_misunderstanding
- constraint_misunderstanding
- wrong_target_object
- wrong_task_scope

Example:
The question asks for CPC group codes, but the agent looks for patent numbers.

---

### S2: Data / Schema Grounding

The agent identifies the required databases, tables, files, fields, and domain objects.

Common errors:
- missing_required_data_source
- wrong_database_selection
- wrong_table_selection
- wrong_field_selection
- entity_grounding_error
- schema_grounding_error

Example:
The agent should use `publicationinfo.cpc`, but uses an unrelated field.

---

### S3: Planning / Decomposition

The agent decomposes the task into executable substeps.

Common errors:
- missing_substep
- wrong_subtask_order
- incomplete_plan
- unnecessary_subtask
- wrong_intermediate_target

Example:
The agent forgets to include an EMA calculation step.

---

### S4: Tool / Dependency Planning

The agent decides which tools to use and whether subtasks depend on one another.

Common errors:
- false_dependency_error
- missing_dependency_error
- wrong_execution_order
- tool_pipeline_misuse
- wrong_tool_selection

Example:
The agent assumes query2 depends on query1 even though they are independent.

---

### S5: Query / Code Generation

The agent writes SQL, Python, or other executable code.

Common errors:
- sql_generation_error
- python_generation_error
- wrong_join
- wrong_filter
- wrong_projection
- wrong_group_by
- syntax_error

Example:
The generated SQL uses `SELECT *` when only names are required.

---

### S6: Execution

The generated query/code/tool call is executed.

Common errors:
- database_connection_error
- missing_file
- table_not_found
- column_not_found
- runtime_error
- timeout
- memory_error
- validator_runtime_error

Example:
The required database file is missing.

---

### S7: Transformation / Calculation

The agent transforms intermediate data and performs computations.

Common errors:
- aggregation_error
- counting_error
- formula_error
- ranking_error
- temporal_parsing_error
- granularity_level_error
- calculation_error

Example:
The agent uses the wrong EMA smoothing factor.

---

### S8: Answer Synthesis / Validation

The agent constructs the final answer and the validator checks it.

Common errors:
- output_completeness_error
- output_format_error
- output_alignment_error
- missing_required_item
- extra_unrelated_item
- validator_expectation_mismatch

Example:
The final answer misses a required CPC code.

## Surface Error vs Root Cause

A validator error is usually a surface symptom, not necessarily the root cause.

Example:

Validation feedback:
`Missing CPC code: A22B`

Surface error:
- Stage: S8 Answer Synthesis / Validation
- Type: output_completeness_error
- Evidence: Missing CPC code: A22B

Possible upstream root causes:
- S2 Data / Schema Grounding
- S3 Planning / Decomposition
- S6 Execution
- S7 Transformation / Calculation

Without intermediate execution traces, the root cause should be marked as unknown or low-confidence.

## Error Record Format

Each failed case should produce a structured error record:

```json
{
  "surface_error": {
    "stage": "S8_answer_synthesis_validation",
    "type": "output_completeness_error",
    "subtype": "missing_required_item",
    "evidence": "Missing CPC code: A22B"
  },
  "root_cause_hypothesis": {
    "stage": "unknown",
    "type": "unknown_without_execution_trace",
    "confidence": "low",
    "reason": "Only final validation feedback is available."
  },
  "possible_upstream_stages": [
    "S2_data_schema_grounding",
    "S3_planning_decomposition",
    "S6_execution",
    "S7_transformation_calculation"
  ],
  "target_modules": [
    "answer_synthesis",
    "execution_trace_logging"
  ]
}
