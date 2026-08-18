#!/usr/bin/env bash
set -euo pipefail
# Restore a custom-format dump from scripts/pg_dump.sh into the Compose Postgres volume.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DUMP="${1:?usage: scripts/pg_restore.sh data/backups/market_agent_YYYYMMDD.dump}"
docker compose exec -T db pg_restore --clean --if-exists -U market -d market_agent < "$DUMP"
echo "restored $DUMP"
