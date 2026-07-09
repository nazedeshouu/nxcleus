#!/usr/bin/env bash
# fleet_down.sh — drain + DESTROY every MI300X droplet tagged nxcleus-fleet.
#
# Draining first (POST /api/admin/nodes/{id}/drain) lets in-flight stages fail over cleanly to the
# Fireworks fallback before the GPUs vanish. Destroying stops the $/hr clock — run this the moment a
# demo/rehearsal ends. Idempotent: no droplets = nothing to do.
#
# Usage:
#   infra/fleet/fleet_down.sh --dry-run     # show what WOULD be destroyed
#   infra/fleet/fleet_down.sh               # drain + destroy (asks once unless --yes)
#   infra/fleet/fleet_down.sh --yes         # no prompt (for the idle watchdog / cron)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/fleet/fleet_lib.sh
. "${HERE}/fleet_lib.sh"

DRY_RUN=0; ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)       DRY_RUN=1; shift ;;
    --yes|--confirm) ASSUME_YES=1; shift ;;
    --control-plane-url) CONTROL_PLANE_URL="$2"; shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

require_doctl

ROWS="$(fleet_droplets_tsv)"
if [ -z "${ROWS}" ]; then log "no droplets tagged '${FLEET_TAG}' — nothing to tear down."; exit 0; fi

log "fleet droplets tagged '${FLEET_TAG}':"
printf '%s\n' "${ROWS}" | while IFS=$'\t' read -r id name status ip size; do
  printf '    %s  %-22s  %-8s  %-16s  %s\n' "${id}" "${name}" "${status}" "${ip}" "${size}"
done

if [ "${DRY_RUN}" -eq 1 ]; then log "DRY RUN — would drain then destroy the above. Nothing changed."; exit 0; fi

if [ "${ASSUME_YES}" != "1" ]; then
  printf '\033[1;33m[fleet]\033[0m Destroy ALL of the above? [y/N] '
  read -r ans; case "${ans}" in y|Y|yes) ;; *) die "aborted"; ;; esac
fi

# 1) drain registered nodes (best-effort) so seats fail over before the GPUs disappear
ADMIN="$(admin_token)"
NODE_JSON="$(curl -fsS -m 8 "${CONTROL_PLANE_URL}/api/fleet" 2>/dev/null || echo '{}')"
printf '%s\n' "${ROWS}" | while IFS=$'\t' read -r _id _name _status ip _size; do
  node_id="$(printf '%s' "${NODE_JSON}" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
nodes=d.get('nodes',d if isinstance(d,list) else [])
print(next((n['id'] for n in nodes if n.get('ip')=='${ip}'), ''))" 2>/dev/null)"
  if [ -n "${node_id}" ]; then
    log "draining node ${node_id} (${ip})"
    curl -fsS -m 8 -X POST -H "X-Admin-Token: ${ADMIN}" \
      "${CONTROL_PLANE_URL}/api/admin/nodes/${node_id}/drain" >/dev/null 2>&1 \
      || warn "drain call failed for ${node_id} (destroying anyway)"
  fi
done

# 2) destroy the droplets (stops billing)
printf '%s\n' "${ROWS}" | while IFS=$'\t' read -r id name _status _ip _size; do
  log "destroying ${name} (${id})"
  doctl_amd compute droplet delete "${id}" --force || warn "delete failed for ${id} — check the AMD dashboard"
done

log "fleet torn down. Confirm with: infra/fleet/fleet_status.sh"
