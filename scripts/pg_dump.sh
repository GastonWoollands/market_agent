#!/usr/bin/env bash
set -euo pipefail
# Custom-format dump of the Compose Postgres volume. Restore with scripts/pg_restore.sh.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data/backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-data/backups/market_agent_${STAMP}.dump}"
docker compose exec -T db pg_dump -U market -d market_agent -Fc > "$OUT"
echo "wrote $OUT"
