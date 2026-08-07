#!/usr/bin/env python3
"""Compatibility bridge for shared repair-launcher utilities.

The Qwen-specific launcher implementation was archived during the full-trace
observer cleanup. `run_codex_native_repair_launcher.py` still depends on its
shared sandbox/gate/profile helpers. Keep this tiny bridge until those helpers
are extracted into a dedicated `repair_launcher_common.py` module.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODULE = (
    ROOT
    / "legacy"
    / "cleanup_20260724_observer_trace_realign"
    / "experiments"
    / "run_codex_qwen_repair_launcher.py"
)

if not LEGACY_MODULE.exists():
    raise ImportError(f"Archived repair launcher helpers not found: {LEGACY_MODULE}")

_spec = importlib.util.spec_from_file_location("_legacy_codex_qwen_repair_launcher", LEGACY_MODULE)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load archived repair launcher helpers: {LEGACY_MODULE}")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

# The archived file was moved under legacy/, so its module-level ROOT would
# otherwise point at the legacy snapshot.  The active Codex-native launcher
# imports this bridge only for shared helper functions/profiles; all runtime
# paths must resolve against the current mainline repository.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_module.ROOT = ROOT
_module.META_AGENT_PROJECT_MEMORY_SKILL = ROOT / "skills/dab-meta-agent-project-memory/SKILL.md"
_module.DAB_TOOL_AGENT_ZERO_START_MEMORY_SKILL = ROOT / "skills/dab-tool-agent-zero-start-memory/SKILL.md"
_module.DAB_TOOL_AGENT_ZERO_START_REPAIR_SKILL = ROOT / "skills/dab-tool-agent-zero-start-repair/SKILL.md"
_module.PROFILE_SKILLS = {
    "data_agent_prompt_repair": ROOT / "skills/dab-data-agent-prompt-repair/SKILL.md",
    "data_agent_project_repair": ROOT / "skills/dab-patents-project-repair/SKILL.md",
    "data_agent_tool_repair": ROOT / "skills/dab-patents-project-repair/SKILL.md",
}

for _name in dir(_module):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_module, _name)