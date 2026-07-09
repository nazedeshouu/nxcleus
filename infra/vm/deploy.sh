#!/usr/bin/env bash
# Canonical deploy/redeploy wrapper for the Nxcleus control VM.
#
# Guarantees the auto-HTTPS domain is always set for Caddy's ${NXCLEUS_DOMAIN} substitution,
# so a bare `docker compose up` can never silently fall back to `localhost` (which would drop
# the Let's Encrypt cert). Precedence: exported NXCLEUS_DOMAIN > infra/vm/domain file > localhost.
#
# Swap to the real domain later with ONE change: `echo nxcleus.com > infra/vm/domain` then rerun.
#
# Usage (from anywhere):
#   infra/vm/deploy.sh up -d --build      # build + (re)start
#   infra/vm/deploy.sh ps | logs -f | down
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # infra/vm
ROOT="$(cd "${HERE}/../.." && pwd)"                     # repo root

if [ -z "${NXCLEUS_DOMAIN:-}" ] && [ -f "${HERE}/domain" ]; then
  NXCLEUS_DOMAIN="$(tr -d '[:space:]' < "${HERE}/domain")"
fi
: "${NXCLEUS_DOMAIN:=localhost}"
export NXCLEUS_DOMAIN

echo "[deploy] NXCLEUS_DOMAIN=${NXCLEUS_DOMAIN}"
cd "${ROOT}"
exec docker compose -f infra/vm/docker-compose.yml "$@"
