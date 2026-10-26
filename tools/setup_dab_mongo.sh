#!/usr/bin/env bash
set -euo pipefail

# Start a local MongoDB container for DAB mongo-backed queries and restore the
# BSON dumps that are already materialized in external/DataAgentBench_sparse.
#
# This script assumes the `mongo:7` image is available locally or Docker can
# pull it. If Docker Hub auth is blocked, pull the image from Docker Desktop
# after fixing proxy/mirror settings, then rerun this script.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAB_ROOT="${DAB_ROOT:-$ROOT/external/DataAgentBench_sparse}"
CONTAINER="${DAB_MONGO_CONTAINER:-dab-mongo}"
IMAGE="${DAB_MONGO_IMAGE:-mongo:7}"
PORT="${DAB_MONGO_PORT:-27017}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker CLI not found" >&2
  exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Mongo image '$IMAGE' is not available locally; attempting docker pull..."
  docker pull "$IMAGE"
fi

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Mongo container '$CONTAINER' already running."
elif docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "Starting existing Mongo container '$CONTAINER'."
  docker start "$CONTAINER" >/dev/null
else
  echo "Creating Mongo container '$CONTAINER' on localhost:$PORT."
  docker run -d --name "$CONTAINER" -p "$PORT:27017" "$IMAGE" >/dev/null
fi

echo "Waiting for MongoDB to accept commands..."
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" mongosh --quiet --eval 'db.runCommand({ ping: 1 }).ok' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$CONTAINER" mongosh --quiet --eval 'db.runCommand({ ping: 1 })'

restore_dump() {
  local db_name="$1"
  local dump_dir="$2"
  if [ ! -d "$dump_dir" ]; then
    echo "WARN: dump dir missing: $dump_dir" >&2
    return 0
  fi
  echo "Restoring db '$db_name' from $dump_dir"
  docker exec "$CONTAINER" mongosh --quiet --eval "db.getSiblingDB('$db_name').dropDatabase()" >/dev/null
  docker run --rm --network host -v "$dump_dir:/dump:ro" "$IMAGE" \
    mongorestore --host 127.0.0.1 --port "$PORT" --db "$db_name" /dump
}

restore_dump "cve_descriptions" "$DAB_ROOT/query_cve/query_dataset/descriptions/cve_descriptions"
restore_dump "yelp_db" "$DAB_ROOT/query_yelp/query_dataset/yelp_business/yelp_db"
restore_dump "articles_db" "$DAB_ROOT/query_agnews/query_dataset/agnews_articles/articles_db"
restore_dump "civic_db" "$DAB_ROOT/query_civic_unstructured/query_dataset/civic_docs_dump/civic_db"
restore_dump "domain_docs_db" "$DAB_ROOT/query_krama/query_dataset/domain_docs/domain_docs_db"
restore_dump "usaspending_descriptions" "$DAB_ROOT/query_usaspending/query_dataset/descriptions/usaspending_descriptions"

echo "MongoDB databases:"
docker exec "$CONTAINER" mongosh --quiet --eval 'db.adminCommand({ listDatabases: 1 }).databases.map(d => d.name + ":" + Math.round(d.sizeOnDisk/1024) + "KB").join("\n")'

echo "Done."
