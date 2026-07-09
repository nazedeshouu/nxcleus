#!/usr/bin/env bash
# fleet_watchdog.sh — "the fleet is up but idle, and idle 8x = a rehearsal per hour" guard (07 §5.4).
#
# Every run it asks the control plane two questions: are GPU nodes registered, and is any job/run
# actually in flight? Registered + idle for longer than IDLE_MINUTES -> Discord alert (once per idle
# episode). With --destroy-idle it also tears the fleet down automatically (off by default — an alert
# is safe, an auto-destroy mid-rehearsal is not).
#
# Install on the control VM as a cron (every 5 min):
#   */5 * * * * IDLE_MINUTES=30 /root/nxcleus/infra/fleet/fleet_watchdog.sh >> /var/log/nxcleus-watchdog.log 2>&1
#
# Usage: infra/fleet/fleet_watchdog.sh [--destroy-idle] [--once]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/fleet/fleet_lib.sh
. "${HERE}/fleet_lib.sh"

IDLE_MINUTES="${IDLE_MINUTES:-30}"
DESTROY_IDLE=0
STATE_FILE="${WATCHDOG_STATE:-/var/lib/nxcleus/fleet-watchdog.state}"

while [ $# -gt 0 ]; do
  case "$1" in
    --destroy-idle) DESTROY_IDLE=1; shift ;;
    --once) shift ;;   # accepted for symmetry; this script is single-shot by design
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done

mkdir -p "$(dirname "${STATE_FILE}")" 2>/dev/null || true
now="$(date +%s)"

discord_url() {
  [ -n "${DISCORD_WEBHOOK_URL:-}" ] && { printf '%s' "${DISCORD_WEBHOOK_URL}"; return; }
  [ -f "${REPO_ROOT}/.env" ] && grep '^DISCORD_WEBHOOK_URL=' "${REPO_ROOT}/.env" | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//'
}
notify() {   # notify <message>
  local url; url="$(discord_url)"
  if [ -n "${url}" ]; then
    curl -fsS -m 8 -H 'Content-Type: application/json' \
      -d "$(python3 -c "import json,sys; print(json.dumps({'content': sys.argv[1]}))" "$1")" \
      "${url}" >/dev/null 2>&1 || warn "discord post failed"
  fi
  log "$1"
}

# What is actually BILLING? Prefer the real AMD droplet count (accurate $/hr); fall back to
# control-plane nodes excluding loopback stubs (the dev_seed stub node registers as 127.0.0.1).
NODE_COUNT=0; NODE_SRC="none"
if command -v doctl >/dev/null 2>&1 && doctl account get --api-url "${AMD_API}" >/dev/null 2>&1; then
  NODE_COUNT="$(fleet_droplets_tsv | grep -c . || true)"
  NODE_SRC="AMD droplets"
else
  FLEET_JSON="$(curl -fsS -m 8 "${CONTROL_PLANE_URL}/api/fleet" 2>/dev/null || echo '{}')"
  NODE_COUNT="$(printf '%s' "${FLEET_JSON}" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
nodes=d.get('nodes', d if isinstance(d,list) else [])
live=[n for n in nodes if n.get('status') in (None,'ready','registered','draining')
      and n.get('ip') not in ('127.0.0.1','localhost','::1')]
print(len(live))" 2>/dev/null || echo 0)"
  NODE_SRC="control-plane nodes (no doctl)"
fi

if [ "${NODE_COUNT}" -eq 0 ]; then
  log "no billing fleet (${NODE_SRC}) — no GPU spend to guard. resetting idle timer."
  printf 'last_busy=%s\nalerted=0\n' "${now}" > "${STATE_FILE}"
  exit 0
fi

# any job in flight? (non-terminal, non-parked statuses)
ACTIVE="$(curl -fsS -m 8 "${CONTROL_PLANE_URL}/api/jobs" 2>/dev/null | python3 -c "
import json,sys
BUSY={'intake','planning','certifying','building','consolidating','qa','delivering','running'}
try: d=json.load(sys.stdin)
except Exception: d=[]
jobs=d if isinstance(d,list) else d.get('jobs',[])
print(len([j for j in jobs if j.get('status') in BUSY]))" 2>/dev/null || echo 0)"

# load prior state
last_busy="${now}"; alerted=0
if [ -f "${STATE_FILE}" ]; then
  # shellcheck disable=SC1090
  . "${STATE_FILE}" 2>/dev/null || true
fi

if [ "${ACTIVE}" -gt 0 ]; then
  log "fleet busy (${NODE_COUNT} node(s), ${ACTIVE} active job(s)) — clock reset."
  printf 'last_busy=%s\nalerted=0\n' "${now}" > "${STATE_FILE}"
  exit 0
fi

idle_secs=$(( now - last_busy ))
idle_min=$(( idle_secs / 60 ))
log "fleet IDLE: ${NODE_COUNT} node(s) registered, 0 active jobs, idle ${idle_min}m (threshold ${IDLE_MINUTES}m)"

if [ "${idle_min}" -ge "${IDLE_MINUTES}" ]; then
  if [ "${alerted}" != "1" ]; then
    notify "⚠️ Nxcleus fleet idle ${idle_min}m — ${NODE_COUNT} MI300X node(s) up, no active jobs. ~\$15.92/hr burning. Tear down with fleet_down.sh."
    printf 'last_busy=%s\nalerted=1\n' "${last_busy}" > "${STATE_FILE}"
  fi
  if [ "${DESTROY_IDLE}" -eq 1 ]; then
    notify "🛑 auto-destroying idle fleet (--destroy-idle)."
    "${HERE}/fleet_down.sh" --yes || warn "auto-destroy failed — tear down manually"
  fi
else
  printf 'last_busy=%s\nalerted=%s\n' "${last_busy}" "${alerted}" > "${STATE_FILE}"
fi
