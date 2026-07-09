#!/usr/bin/env bash
# fleet_status.sh — what's running, what it's costing, and what the control plane sees.
#
# Cross-references two truths: (1) droplets that EXIST on the AMD account (billing), and (2) nodes
# REGISTERED with the control plane (schedulable). A droplet in (1) but not (2) is burning money
# without serving — exactly what the idle watchdog guards against.
#
# Usage: infra/fleet/fleet_status.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/fleet/fleet_lib.sh
. "${HERE}/fleet_lib.sh"

require_doctl

echo "── AMD account: droplets tagged '${FLEET_TAG}' (region ${FLEET_REGION}) ──"
ROWS="$(fleet_droplets_tsv)"
if [ -z "${ROWS}" ]; then
  echo "  (none — fleet is down; \$0/hr GPU spend)"
else
  printf '    %-12s %-22s %-9s %-16s %s\n' ID NAME STATUS IP SIZE
  hourly=0
  while IFS=$'\t' read -r id name status ip size; do
    printf '    %-12s %-22s %-9s %-16s %s\n' "${id}" "${name}" "${status}" "${ip}" "${size}"
    case "${size}" in
      "${SIZE_8X}") hourly=$(python3 -c "print(${hourly}+15.92)") ;;
      "${SIZE_1X}") hourly=$(python3 -c "print(${hourly}+1.99)") ;;
    esac
  done <<< "${ROWS}"
  echo "  ESTIMATED SPEND: \$${hourly}/hr  (\$$(python3 -c "print(round(${hourly}*24,2))")/day if left up)"
fi

echo
echo "── control plane: ${CONTROL_PLANE_URL}/api/fleet ──"
if curl -fsS -m 8 "${CONTROL_PLANE_URL}/api/fleet" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
nodes=d.get('nodes', d if isinstance(d,list) else [])
if not nodes:
    print('  (no nodes registered)'); sys.exit(0)
for n in nodes:
    gpus=n.get('gpus') or n.get('gpus_json') or '[]'
    ng = len(json.loads(gpus)) if isinstance(gpus,str) else len(gpus)
    print(f\"  {n.get('name','?'):4} {n.get('status','?'):9} ip={n.get('ip','?'):16} gpus={ng}\")
"; then :; else echo "  (control plane unreachable)"; fi
