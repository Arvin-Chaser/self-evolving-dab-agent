"""Runtime plumbing for unattended DAB meta-agent calls, with live logs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import urllib.request


def resolve_codex(executable: str) -> str:
    requested = Path(executable)
    if requested.is_file():
        return str(requested)
    found = shutil.which(executable)
    if found and Path(found).suffix.lower() not in {'.ps1', '.cmd', '.bat'}:
        return found
    candidates = list((Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI/Codex/bin").glob("*/codex.exe"))
    if candidates:
        return str(max(candidates, key=lambda path: path.stat().st_mtime))
    found = shutil.which("codex")
    if found:
        return found
    raise RuntimeError("Codex executable unavailable; refresh the configured installation path")


def meta_environment(profile: str | None) -> dict[str, str]:
    """Use the selected provider's environment key and existing configured auth hook."""
    from experiments.dab_api_routing import routed_meta_environment
    env = routed_meta_environment(profile) or os.environ.copy()
    if profile == 'deepseek-standalone-dab':
        # Dedicated route already binds executable/config/credential. No inherited
        # desktop auth hook or extra /models request is used for this runtime.
        from experiments.dab_meta_standalone_runtime_v1 import validate, HOME
        validate()
        if Path(env.get('CODEX_HOME','')).resolve() != HOME.resolve():
            raise RuntimeError('Dedicated Meta route unavailable; no desktop fallback')
        return env
    config_dir = Path(env.get("CODEX_HOME") or (Path.home() / ".codex"))
    base_path = config_dir / "config.toml"
    base = tomllib.loads(base_path.read_text(encoding="utf-8")) if base_path.exists() else {}
    overlay_path = config_dir / f"{profile}.config.toml" if profile else None
    overlay = tomllib.loads(overlay_path.read_text(encoding="utf-8")) if overlay_path and overlay_path.exists() else {}
    provider_id = overlay.get("model_provider", base.get("model_provider", "openai"))
    providers = {**base.get("model_providers", {}), **overlay.get("model_providers", {})}
    provider = providers.get(provider_id, {})
    env_key = provider.get("env_key")
    if env_key and not env.get(env_key):
        # A previous research profile already defines the explicitly configured
        # credential hook. Reuse that hook only for the same API endpoint.
        hooks = [item.get("auth") for item in providers.values()
                 if item.get("base_url") == provider.get("base_url") and isinstance(item.get("auth"), dict)]
        if not hooks:
            raise RuntimeError(f"Missing provider credential environment variable: {env_key}")
        hook = hooks[0]
        proc = subprocess.run([hook["command"], *hook.get("args", [])],
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=max(15, hook.get("timeout_ms", 5000) / 1000), check=False)
        if proc.returncode:
            raise RuntimeError(f"Configured provider credential hook failed (exit {proc.returncode})")
        value = proc.stdout.strip().lstrip("\ufeff")
        if value.startswith("{"):
            payload = json.loads(value)
            value = payload.get("access_token") or payload.get("token") or payload.get("api_key") or ""
        if not isinstance(value, str) or not value or any(char.isspace() for char in value):
            raise RuntimeError("Configured credential hook returned an invalid token")
        env[env_key] = value
    if provider.get("base_url") and env_key:
        request = urllib.request.Request(provider["base_url"].rstrip("/") + "/models",
                                         headers={"Authorization": "Bearer " + env[env_key]})
        try:
            class NoCredentialRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    raise RuntimeError("Provider credential redirects are prohibited")
            opener = urllib.request.build_opener(NoCredentialRedirect())
            with opener.open(request, timeout=20) as response:
                data = json.load(response)
        except Exception as exc:
            raise RuntimeError(f"Provider connectivity preflight failed: {type(exc).__name__}") from None
        model = overlay.get("model", base.get("model"))
        if model and model not in {entry.get("id") for entry in data.get("data", [])}:
            raise RuntimeError(f"Configured model is unavailable: {model}")
    env.pop("PYTHONPATH", None)
    return env


def run_logged_command(command: list[str], *, cwd: Path, prompt: str,
                       stdout_path: Path, stderr_path: Path,
                       env: dict[str, str], timeout: float | None = None) -> subprocess.CompletedProcess:
    """Write logs as the process runs; None keeps model calls free of deadlines."""
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                stdout=out, stderr=err, text=True, encoding="utf-8")
        try:
            proc.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
    # Candidate admission needs only a bounded diagnostic tail, never a full log.
    with stderr_path.open("rb") as stream:
        stream.seek(max(0, stderr_path.stat().st_size - 8000))
        tail = stream.read().decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(command, proc.returncode, "", tail)
