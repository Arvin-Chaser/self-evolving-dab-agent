from pathlib import Path


path = Path(
    "/home/ecs-user/workspace/text2sql/external/harness_baselines/agentic-harness-engineering/"
    "agents/evolve_agent/skills/agent-debugger-cli/_source/pyproject.toml"
)
text = path.read_text().replace(
    '    "nexau @ git+https://github.com/nex-agi/NexAU.git@v0.3.9",',
    '    "nexau",',
)
if "[tool.uv.sources]" not in text:
    text += "\n\n[tool.uv.sources]\n"
text += 'nexau = { path = "/home/ecs-user/workspace/text2sql/external/vendor/NexAU-0.3.9" }\n'
path.write_text(text)
