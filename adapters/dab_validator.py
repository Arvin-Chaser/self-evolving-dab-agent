import importlib.util
from pathlib import Path


def load_validate_function(validate_path: Path):
    validate_path = Path(validate_path).resolve()

    if not validate_path.exists():
        raise FileNotFoundError(f"validate.py not found: {validate_path}")

    spec = importlib.util.spec_from_file_location(
        "dab_validate_module",
        validate_path,
    )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "validate"):
        raise AttributeError(f"No validate() function found in {validate_path}")

    return module.validate


def run_dab_validation(validate_path: Path, llm_output: str) -> dict:
    validate_fn = load_validate_function(validate_path)

    try:
        passed, reason = validate_fn(llm_output)
    except Exception as e:
        return {
            "passed": False,
            "reason": f"validator_runtime_error: {repr(e)}",
        }

    return {
        "passed": bool(passed),
        "reason": str(reason),
    }
