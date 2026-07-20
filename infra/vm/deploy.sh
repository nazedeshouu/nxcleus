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
: "${CODEEXEC_IMAGE:=nxcleus/codeexec:py312}"
export CODEEXEC_IMAGE

# Dedicated landing + platform hosts (their own Caddy site blocks, separate from NXCLEUS_SITE).
# Default = amd./amdplatform. prefix on the primary domain (=> amd.localhost in dev, internal cert,
# no ACME). Override by exporting NXCLEUS_LANDING_HOST / NXCLEUS_PLATFORM_HOST before running.
: "${NXCLEUS_LANDING_HOST:=amd.${NXCLEUS_DOMAIN}}"
: "${NXCLEUS_PLATFORM_HOST:=amdplatform.${NXCLEUS_DOMAIN}}"
export NXCLEUS_LANDING_HOST NXCLEUS_PLATFORM_HOST

# Build the executor only for mutating Compose commands. Global flags and their values are skipped
# so a service named "up" passed to a read-only command cannot trigger a build accidentally.
COMPOSE_COMMAND=""
COMPOSE_ARGS=("$@")
arg_index=0
while [ "${arg_index}" -lt "${#COMPOSE_ARGS[@]}" ]; do
  arg="${COMPOSE_ARGS[${arg_index}]}"
  case "${arg}" in
    -f|--file|--env-file|--ansi|--parallel|--profile|--progress|--project-directory|-p|--project-name)
      arg_index=$((arg_index + 2))
      ;;
    --*=*|--compatibility|--dry-run|--*)
      arg_index=$((arg_index + 1))
      ;;
    *)
      COMPOSE_COMMAND="${arg}"
      break
      ;;
  esac
done

echo "[deploy] NXCLEUS_DOMAIN=${NXCLEUS_DOMAIN}  NXCLEUS_SITE=${NXCLEUS_SITE}"
echo "[deploy] NXCLEUS_LANDING_HOST=${NXCLEUS_LANDING_HOST}  NXCLEUS_PLATFORM_HOST=${NXCLEUS_PLATFORM_HOST}"
cd "${ROOT}"
if [ "${COMPOSE_COMMAND}" = "up" ] || [ "${COMPOSE_COMMAND}" = "build" ]; then
  echo "[deploy] building code-exec image ${CODEEXEC_IMAGE}"
  docker build -f backend/Dockerfile.codeexec -t "${CODEEXEC_IMAGE}" backend
fi
exec docker compose -f infra/vm/docker-compose.yml "$@"
