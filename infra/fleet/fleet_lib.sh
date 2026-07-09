#!/usr/bin/env bash
# Shared config + helpers for the Nxcleus MI300X fleet scripts (infra/fleet/).
#
# The AMD Dev Cloud is a separate control plane reached via the AMD API host; the SAME doctl
# token authenticates both api.digitalocean.com and api-amd.digitalocean.com (verified 2026-07-09).
# All values are env-overridable so nothing here is a hardcode you can't escape.
#
# Sourced by fleet_up.sh / fleet_down.sh / fleet_status.sh / fleet_watchdog.sh — not run directly.

# ── verified account facts (2026-07-09 read-only probe; see infra/fleet/README.md) ───────────
AMD_API="${AMD_API:-https://api-amd.digitalocean.com}"
FLEET_REGION="${FLEET_REGION:-atl1}"                 # MI300X Dev Cloud is atl1-ONLY
FLEET_TAG="${FLEET_TAG:-nxcleus-fleet}"

# MI300X shapes carry a -devcloud suffix (NOT the bare slugs in older spec drafts).
SIZE_1X="${SIZE_1X:-gpu-mi300x1-192gb-devcloud}"     # $1.99/hr  — self-serve on-demand
SIZE_8X="${SIZE_8X:-gpu-mi300x8-1536gb-devcloud}"    # $15.92/hr — catalog-orderable (capacity-gated)

# "AMD AI/ML Ready Image" — GPU drivers + Docker preinstalled; newest AMD base (2026-07-08).
GPU_IMAGE="${GPU_IMAGE:-gpu-amd-base}"

# vLLM ROCm serving image — corrected gfx94X-dcgpu tag (bare gfx942 is a 404 on Docker Hub).
VLLM_ROCM_IMAGE="${VLLM_ROCM_IMAGE:-rocm/vllm:rocm7.13.0_gfx94X-dcgpu_ubuntu24.04_py3.13_pytorch_2.10.0_vllm_0.19.1}"

# SSH key (imported to DO as nxcleus-deploy; same key as the control VM).
SSH_KEY_NAME="${SSH_KEY_NAME:-nxcleus-deploy}"
SSH_KEY_FILE="${SSH_KEY_FILE:-$HOME/.ssh/nxcleus_deploy}"

# Where nodes self-register. Defaults to the live control VM.
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-https://165-245-152-181.sslip.io}"

# Repo root (this file is infra/fleet/fleet_lib.sh).
FLEET_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${FLEET_LIB_DIR}/../.." && pwd)"

# ── logging ──────────────────────────────────────────────────────────────────────────────────
c_info='\033[1;36m'; c_warn='\033[1;33m'; c_err='\033[1;31m'; c_off='\033[0m'
log()  { printf "${c_info}[fleet]${c_off} %s\n" "$*"; }
warn() { printf "${c_warn}[fleet] WARN${c_off} %s\n" "$*" >&2; }
die()  { printf "${c_err}[fleet] FATAL${c_off} %s\n" "$*" >&2; exit 1; }

# ── doctl wrappers ─────────────────────────────────────────────────────────────────────────
doctl_amd() { doctl "$@" --api-url "${AMD_API}"; }   # GPU fleet lives on the AMD API

require_doctl() {
  command -v doctl >/dev/null 2>&1 || die "doctl not found (brew install doctl; doctl auth init)"
  doctl account get --api-url "${AMD_API}" >/dev/null 2>&1 \
    || die "doctl not authed against the AMD API (run: doctl auth init)"
}

# profile -> droplet size slug
profile_size() {
  case "$1" in
    P1)     printf '%s' "${SIZE_1X}" ;;
    P2|P3)  printf '%s' "${SIZE_8X}" ;;
    *)      return 1 ;;
  esac
}

# Resolve the DO SSH key id for the named key (fleet droplets get the same deploy key).
ssh_key_id() {
  doctl_amd compute ssh-key list -o json 2>/dev/null \
    | python3 -c "import json,sys; ks=json.load(sys.stdin); print(next((str(k['id']) for k in ks if k['name']=='${SSH_KEY_NAME}'), ''))"
}

# ADMIN_TOKEN for node registration — read from repo .env WITHOUT printing it.
admin_token() {
  [ -f "${REPO_ROOT}/.env" ] || { printf ''; return; }
  grep '^ADMIN_TOKEN=' "${REPO_ROOT}/.env" | head -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//'
}

# HF token for gated/model downloads on the droplet — from the standard hf cache path.
hf_token() {
  if [ -f "${HOME}/.cache/huggingface/token" ]; then
    tr -d '[:space:]' < "${HOME}/.cache/huggingface/token"
  fi
}

ssh_fleet() {   # ssh_fleet <ip> <remote-cmd...>
  local ip="$1"; shift
  ssh -i "${SSH_KEY_FILE}" -o StrictHostKeyChecking=no -o ConnectTimeout=15 "root@${ip}" "$@"
}

# List fleet droplet rows as: id<TAB>name<TAB>status<TAB>publicIP<TAB>size
fleet_droplets_tsv() {
  doctl_amd compute droplet list --tag-name "${FLEET_TAG}" -o json 2>/dev/null | python3 -c "
import json,sys
try: ds=json.load(sys.stdin)
except Exception: ds=[]
for d in ds:
    ip=next((n['ip_address'] for n in d.get('networks',{}).get('v4',[]) if n['type']=='public'),'-')
    print('\t'.join([str(d['id']), d['name'], d['status'], ip, d['size']['slug']]))
"
}
