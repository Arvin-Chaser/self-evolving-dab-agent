#!/usr/bin/env bash
set -euo pipefail
container="${DAB_POSTGRES_CONTAINER:-dab-postgres}"
exec docker exec -i "$container" psql "$@"
