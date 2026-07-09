#!/usr/bin/env bash
# fleet_up.sh — provision ONE MI300X droplet for a packing profile and bring the fleet up on it.
#
#   P1 -> 1x MI300X ($1.99/hr)    trust/oracle/inspector local; GLM+coder on Fireworks fallback
#   P2 -> 8x MI300X ($15.92/hr)   the hero profile: the whole fleet local on one droplet
#   P3 -> 8x MI300X ($15.92/hr)   wide fan-out (brain FP8)
#
# SAFETY: creating a GPU droplet BILLS IMMEDIATELY and is gated on the orchestrator's explicit go
# (team brief). This script therefore REFUSES to create anything unless you pass --yes (or set
# FLEET_CONFIRM=1). --dry-run validates + renders the launch plan with NO API calls that spend.
#
# Usage:
#   infra/fleet/fleet_up.sh P2 --dry-run                 # validate + show the plan, spend nothing
#   infra/fleet/fleet_up.sh P2 --yes                     # actually create + bootstrap (after the go)
#   FLEET_CONFIRM=1 infra/fleet/fleet_up.sh P1
# Options: --image <vllm-img> --gpu-image <base> --region <slug> --control-plane-url <url>
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/fleet/fleet_lib.sh
. "${HERE}/fleet_lib.sh"

PROFILE=""
DRY_RUN=0
CONFIRM="${FLEET_CONFIRM:-0}"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    P1|P2|P3)            PROFILE="$1"; shift ;;
    --profile)           PROFILE="$2"; shift 2 ;;
    --dry-run)           DRY_RUN=1; shift ;;
    --yes|--confirm)     CONFIRM=1; shift ;;
    --image)             VLLM_ROCM_IMAGE="$2"; shift 2 ;;
    --gpu-image)         GPU_IMAGE="$2"; shift 2 ;;
    --region)            FLEET_REGION="$2"; shift 2 ;;
    --control-plane-url) CONTROL_PLANE_URL="$2"; shift 2 ;;
    -h|--help)           usage; exit 0 ;;
    *) die "unknown arg: $1 (see --help)" ;;
  esac
done

[ -n "${PROFILE}" ] || { usage; die "profile required (P1|P2|P3)"; }
SIZE="$(profile_size "${PROFILE}")" || die "bad profile ${PROFILE}"
DROP_NAME="nxcleus-fleet-$(printf '%s' "${PROFILE}" | tr '[:upper:]' '[:lower:]')"

print_plan() {
  local price="\$1.99/hr"; [ "${SIZE}" = "${SIZE_8X}" ] && price="\$15.92/hr"
  cat <<PLAN
  droplet name     : ${DROP_NAME}
  size             : ${SIZE}   (${price})
  region           : ${FLEET_REGION}
  base image       : ${GPU_IMAGE}
  vLLM ROCm image  : ${VLLM_ROCM_IMAGE}
  control plane    : ${CONTROL_PLANE_URL}
  tag              : ${FLEET_TAG}
  ssh key          : ${SSH_KEY_NAME} (${SSH_KEY_FILE})
PLAN
}

# ── dry run: validate the render plan locally (no GPU, no API spend) ─────────────────────────
if [ "${DRY_RUN}" -eq 1 ]; then
  log "DRY RUN — profile ${PROFILE}. Plan:"; print_plan
  log "validating fleet render via bootstrap.sh --dry-run (no GPU/Docker/network)"
  bash "${REPO_ROOT}/infra/droplet/bootstrap.sh" \
    --dry-run --profile "${PROFILE}" --image "${VLLM_ROCM_IMAGE}"
  log "would run: doctl compute droplet create ${DROP_NAME} --region ${FLEET_REGION} \\"
  log "             --size ${SIZE} --image ${GPU_IMAGE} --tag-names ${FLEET_TAG} \\"
  log "             --ssh-keys <${SSH_KEY_NAME}> --wait --api-url ${AMD_API}"
  log "dry-run OK — nothing created."
  exit 0
fi

# ── spend guard ──────────────────────────────────────────────────────────────────────────────
require_doctl
if [ "${CONFIRM}" != "1" ]; then
  warn "REFUSING to create a ${SIZE} droplet without explicit confirmation."
  warn "GPU creation is gated on the orchestrator's go. Re-run with --yes (or FLEET_CONFIRM=1)."
  log  "Plan that --yes would execute:"; print_plan
  exit 3
fi

KEY_ID="$(ssh_key_id)"; [ -n "${KEY_ID}" ] || die "ssh key '${SSH_KEY_NAME}' not on the account"

log "creating ${DROP_NAME} (${SIZE}) in ${FLEET_REGION} — BILLING STARTS NOW"
IP="$(doctl_amd compute droplet create "${DROP_NAME}" \
      --region "${FLEET_REGION}" --size "${SIZE}" --image "${GPU_IMAGE}" \
      --ssh-keys "${KEY_ID}" --tag-names "${FLEET_TAG}" --wait -o json \
    | python3 -c "import json,sys; d=json.load(sys.stdin)[0]; print(next(n['ip_address'] for n in d['networks']['v4'] if n['type']=='public'))")"
[ -n "${IP}" ] || die "droplet created but no public IP resolved — check 'fleet_status.sh'"
log "droplet up at ${IP}; waiting for SSH"

for _ in $(seq 1 40); do
  ssh_fleet "${IP}" true 2>/dev/null && break
  sleep 6
done
ssh_fleet "${IP}" true 2>/dev/null || die "SSH never came up on ${IP}"

log "syncing infra/ to the droplet"
ssh_fleet "${IP}" 'mkdir -p /root/nxcleus/infra'   # rsync won't create missing parent dirs (macOS rsync has no --mkpath)
rsync -az -e "ssh -i ${SSH_KEY_FILE} -o StrictHostKeyChecking=no" \
  --exclude '__pycache__' --exclude '*.pyc' --exclude 'docker-compose.gen.yml' \
  "${REPO_ROOT}/infra/" "root@${IP}:/root/nxcleus/infra/"

log "writing droplet secret env (root-only; passed via stdin, not argv)"
ADMIN="$(admin_token)"; HFT="$(hf_token)"
[ -n "${HFT}"   ] || warn "no HF token found (~/.cache/huggingface/token) — gated model DLs will 403"
[ -n "${ADMIN}" ] || warn "no ADMIN_TOKEN in .env — node registration will be rejected"
ssh_fleet "${IP}" "umask 077; cat > /root/fleet.env" <<EOF
export HF_TOKEN='${HFT}'
export ADMIN_TOKEN='${ADMIN}'
export NODE_NAME='${NODE_NAME:-B}'
EOF

log "running bootstrap.sh on the droplet (pull image, download models, launch vLLM + node agent)"
ssh_fleet "${IP}" ". /root/fleet.env && cd /root/nxcleus && bash infra/droplet/bootstrap.sh \
   --profile '${PROFILE}' --control-plane-url '${CONTROL_PLANE_URL}' --image '${VLLM_ROCM_IMAGE}'"

log "verifying node self-registration with the control plane"
for _ in $(seq 1 20); do
  if curl -fsS -m 6 "${CONTROL_PLANE_URL}/api/fleet" 2>/dev/null | grep -q "${IP}"; then
    log "node registered ✅  (${IP} visible in ${CONTROL_PLANE_URL}/api/fleet)"; break
  fi
  sleep 6
done

log "fleet up: ${DROP_NAME} @ ${IP} (profile ${PROFILE}). Tear down with: infra/fleet/fleet_down.sh"
