#!/usr/bin/env bash
# Canonical deploy/redeploy wrapper for the Nxcleus control VM.
#
# Guarantees Caddy's auto-HTTPS site list is always set, so a bare `docker compose up` can never
# silently fall back to `localhost` (which would drop the Let's Encrypt certs).
#   - NXCLEUS_DOMAIN = the PRIMARY hostname (drives APP_BASE_URL). From infra/vm/domain.
#   - NXCLEUS_SITE   = comma-separated Caddy site list = primary domain + every host in
#                     infra/vm/extra_hosts (e.g. the sslip host), so the old URL never breaks.
# Precedence for the primary: exported NXCLEUS_DOMAIN > infra/vm/domain file > localhost.
#
# Swap the primary domain later with ONE change: `echo nxcleus.tech > infra/vm/domain` then rerun.
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

# Compose the Caddy site list: primary domain first, then any extra hosts (one per line), deduped.
# localhost (dev) stays single-host — no LE, no extra hosts.
NXCLEUS_SITE="${NXCLEUS_DOMAIN}"
if [ "${NXCLEUS_DOMAIN}" != "localhost" ] && [ -f "${HERE}/extra_hosts" ]; then
  while IFS= read -r h; do
    h="$(printf '%s' "${h}" | tr -d '[:space:]')"
    [ -z "${h}" ] && continue
    [ "${h}" = "${NXCLEUS_DOMAIN}" ] && continue
    NXCLEUS_SITE="${NXCLEUS_SITE}, ${h}"
  done < "${HERE}/extra_hosts"
fi
export NXCLEUS_SITE

# Dedicated landing + platform hosts (their own Caddy site blocks, separate from NXCLEUS_SITE).
# Default = amd./amdplatform. prefix on the primary domain (=> amd.localhost in dev, internal cert,
# no ACME). Override by exporting NXCLEUS_LANDING_HOST / NXCLEUS_PLATFORM_HOST before running.
: "${NXCLEUS_LANDING_HOST:=amd.${NXCLEUS_DOMAIN}}"
: "${NXCLEUS_PLATFORM_HOST:=amdplatform.${NXCLEUS_DOMAIN}}"
export NXCLEUS_LANDING_HOST NXCLEUS_PLATFORM_HOST

echo "[deploy] NXCLEUS_DOMAIN=${NXCLEUS_DOMAIN}  NXCLEUS_SITE=${NXCLEUS_SITE}"
echo "[deploy] NXCLEUS_LANDING_HOST=${NXCLEUS_LANDING_HOST}  NXCLEUS_PLATFORM_HOST=${NXCLEUS_PLATFORM_HOST}"
cd "${ROOT}"
exec docker compose -f infra/vm/docker-compose.yml "$@"
