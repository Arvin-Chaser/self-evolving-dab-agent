from pathlib import Path


path = Path("/home/ecs-user/workspace/text2sql/external/harness_baselines/agentic-harness-engineering/pyproject.toml")
text = path.read_text()
text = text.replace(
    '    "nexau @ git+https://github.com/nex-agi/NexAU.git@v0.3.9",',
    '    "nexau",',
)
text = text.replace(
    '    "harbor @ git+https://github.com/Curry09/harbor-LJH.git",',
    '    "harbor",',
)
needle = 'agent_debugger_core = { path = "agents/evolve_agent/skills/agent-debugger-cli/_source" }'
replacement = (
    needle
    + '\n'
    + 'nexau = { path = "/home/ecs-user/workspace/text2sql/external/vendor/NexAU-0.3.9" }\n'
    + 'harbor = { path = "/home/ecs-user/workspace/text2sql/external/vendor/harbor-LJH-88f855f9babfe40d05ae322c166aa27751930694" }'
)
if needle not in text:
    raise SystemExit("Expected AHE source mapping was not found.")
path.write_text(text.replace(needle, replacement))
