#!/usr/bin/env bash
# Run the backend tests that need a real Postgres server (pytest marker "postgres") against a
# disposable local container. The server listens on 127.0.0.1 only, uses a throwaway password
# generated for this run, keeps no volume and is removed on exit, pass or fail.
#   Extra arguments go to pytest, e.g. scripts/postgres-test.sh -k recreation
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../deploy/images.lock
source "$root/deploy/images.lock"
command -v docker >/dev/null || { echo "missing required tool: docker" >&2; exit 1; }

name="vyom-postgres-test-$$"
password="$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --rm --name "$name" -p 127.0.0.1::5432 \
  -e POSTGRES_PASSWORD="$password" "$POSTGRES_IMAGE" >/dev/null
port="$(docker port "$name" 5432/tcp | head -1 | sed 's/.*://')"

# The image restarts the server once after initialisation; wait for the final one.
for _ in $(seq 60); do
  if docker exec "$name" pg_isready -q -U postgres -h 127.0.0.1 2>/dev/null &&
    docker exec "$name" psql -qtA -U postgres -h 127.0.0.1 -c 'select 1' >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
[[ -n "${ready:-}" ]] || { echo "postgres did not become ready" >&2; exit 1; }

cd "$root/backend"
VYOM_TEST_DATABASE_URL="postgresql://postgres:$password@127.0.0.1:$port/postgres" \
  uv run pytest -m postgres -q "$@"
