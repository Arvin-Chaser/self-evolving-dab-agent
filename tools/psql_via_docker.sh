#!/usr/bin/env bash
set -euo pipefail
container="${DAB_POSTGRES_CONTAINER:-dab-postgres}"
if docker info >/dev/null 2>&1; then
  docker_cmd=(docker)
elif command -v docker.exe >/dev/null 2>&1 && docker.exe info >/dev/null 2>&1; then
  docker_cmd=(docker.exe)
else
  echo "Neither WSL docker nor Windows docker.exe can reach Docker Desktop" >&2
  exit 127
fi

args=("$@")
for ((i=0; i<${#args[@]}; i++)); do
  if [[ "${args[$i]}" == "-f" && $((i + 1)) -lt ${#args[@]} ]]; then
    src="${args[$((i + 1))]}"
    if [[ -f "$src" ]]; then
      dst="/tmp/dab_psql_$(basename "$src")_$$.sql"
      "${docker_cmd[@]}" cp "$src" "$container:$dst" >/dev/null
      args[$((i + 1))]="$dst"
    fi
  fi
done

exec "${docker_cmd[@]}" exec -i "$container" psql "${args[@]}"
