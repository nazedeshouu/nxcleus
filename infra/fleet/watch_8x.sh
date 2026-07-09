#!/usr/bin/env bash
# watch_8x.sh — poll the AMD API for the 8× MI300X shape becoming self-serve.
#
# The dev-cloud 8× (gpu-mi300x8-1536gb-devcloud) is capacity-gated: `available:true` but
# `regions:null` (no enabled region → create fails). This watcher fires ONCE when a region
# appears (i.e. it became orderable), so we can boot P2 (the 8× hero profile). Runs as a VM
# cron (doctl is authed on the VM). Alerts via DISCORD_WEBHOOK_URL if set, always logs + drops
# a flag file the operator/agent can check.
#
# Install:  */11 * * * * /root/nxcleus/infra/fleet/watch_8x.sh >> /var/log/nxcleus-8xwatch.log 2>&1
set -uo pipefail

AMD_API="${AMD_API:-https://api-amd.digitalocean.com}"
SIZE_8X="${SIZE_8X:-gpu-mi300x8-1536gb-devcloud}"
FLAG="${WATCH_8X_FLAG:-/root/nxcleus-8x-available.flag}"
ENV_FILE="${ENV_FILE:-/root/nxcleus/.env}"
TS="$(date -Is)"

regions="$(doctl compute size list --api-url "${AMD_API}" -o json 2>/dev/null | python3 -c "
import json,sys
try: sizes=json.load(sys.stdin)
except Exception: sizes=[]
for s in sizes:
    if s.get('slug')=='${SIZE_8X}':
        r=s.get('regions')
        print(','.join(r) if r else '')
        break
" 2>/dev/null)"

if [ -z "${regions}" ]; then
  echo "${TS} 8x still capacity-gated (regions empty)"
  exit 0
fi

# A region appeared — the 8x is orderable. Alert once (flag guards repeats).
echo "${TS} 8x NOW AVAILABLE in region(s): ${regions}"
if [ -f "${FLAG}" ]; then exit 0; fi
printf '%s available in: %s\n' "${TS}" "${regions}" > "${FLAG}"

url="${DISCORD_WEBHOOK_URL:-}"
[ -z "${url}" ] && [ -f "${ENV_FILE}" ] && url="$(grep '^DISCORD_WEBHOOK_URL=' "${ENV_FILE}" | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//')"
if [ -n "${url}" ]; then
  curl -fsS -m 8 -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json; print(json.dumps({'content': '🚀 MI300X 8x (${SIZE_8X}) is NOW self-serve in ${regions} — P2 hero profile can boot. (nxcleus 8x watcher)'}))")" \
    "${url}" >/dev/null 2>&1 || echo "${TS} discord post failed"
fi
