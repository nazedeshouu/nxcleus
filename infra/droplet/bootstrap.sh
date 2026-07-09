#!/usr/bin/env bash
# Nxcleus MI300X droplet bootstrap — idempotent.
#
# Brings up one fleet profile on an AMD Dev Cloud 8x (or 1x) MI300X droplet:
#   1. preflight (env, tooling, GPUs)
#   2. pull the ROCm vLLM container image
#   3. download the profile's models from HuggingFace (gated Gemma -> loud failure)
#   4. render docker-compose.gen.yml from infra/fleet.yaml (render_compose.py)
#   5. docker compose up -d  (one vLLM instance per GPU partition + the node agent)
#   6. the node agent self-registers with the control plane on startup (02 §9, 07 §5.1)
#
# --dry-run validates config + renders compose WITHOUT GPUs/Docker/network — runs on a Mac.
#
# Serving image (spec 11 §8 / Docker Hub rocm/vllm): the current ROCm 7.13.0 + vLLM 0.19.1
# train (May 2026). MI300X == gfx942 (CDNA3); the gfx942 sibling tag must be confirmed to
# pull at first boot (the registry query surfaced the gfx110X/gfx120X siblings of this exact
# train). Override with VLLM_ROCM_IMAGE. Upstream alternative: vllm/vllm-openai-rocm.
#
# Usage:
#   ./bootstrap.sh --profile P2 --control-plane-url https://api.nxcleus.example
#   ./bootstrap.sh --dry-run                 # validate + render only (no GPUs)
set -euo pipefail

# ── config (env-overridable) ─────────────────────────────────────────────────
PROFILE="${PROFILE:-P2}"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://localhost:8080}"
VLLM_ROCM_IMAGE="${VLLM_ROCM_IMAGE:-rocm/vllm:rocm7.13.0_gfx942_ubuntu24.04_py3.13_pytorch_2.10.0_vllm_0.19.1}"
DRY_RUN=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_OUT="${SCRIPT_DIR}/docker-compose.gen.yml"

# ── args ─────────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --control-plane-url) CONTROL_PLANE_URL="$2"; shift 2 ;;
    --image) VLLM_ROCM_IMAGE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[bootstrap] WARN\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[bootstrap] FATAL\033[0m %s\n' "$*" >&2; exit 1; }

# Pick a python for the renderer/validator: prefer uv (Mac dev), else python3.
py() {
  if command -v uv >/dev/null 2>&1; then
    uv run --with pyyaml python "$@"
  else
    python3 "$@"
  fi
}

# ── 1. preflight ─────────────────────────────────────────────────────────────
log "profile=${PROFILE} control_plane=${CONTROL_PLANE_URL} dry_run=${DRY_RUN}"
log "validating infra YAMLs"
py "${INFRA_DIR}/validate_config.py" || die "infra config validation failed"

log "rendering compose plan for ${PROFILE}"
py "${SCRIPT_DIR}/render_compose.py" \
  --profile "${PROFILE}" \
  --image "${VLLM_ROCM_IMAGE}" \
  --control-plane-url "${CONTROL_PLANE_URL}" \
  --out "${COMPOSE_OUT}"

if [ "${DRY_RUN}" -eq 1 ]; then
  log "DRY RUN — compose rendered to ${COMPOSE_OUT}. Skipping GPU/Docker/network steps."
  log "instances planned:"
  grep -E 'container_name:' "${COMPOSE_OUT}" | sed 's/^/    /'
  log "dry-run OK"
  exit 0
fi

command -v docker >/dev/null 2>&1 || die "docker not found on this host"
command -v rocm-smi >/dev/null 2>&1 || warn "rocm-smi not found — is this an MI300X host?"
[ -n "${HF_TOKEN:-}" ] || warn "HF_TOKEN unset — gated model downloads (Gemma) will 403"
[ -n "${ADMIN_TOKEN:-}" ] || warn "ADMIN_TOKEN unset — node registration will be rejected"

log "GPU inventory:"
rocm-smi --showproductname 2>/dev/null || warn "could not query GPUs"

# ── 2. pull the ROCm vLLM image ──────────────────────────────────────────────
log "pulling ${VLLM_ROCM_IMAGE} (large; first boot only)"
docker pull "${VLLM_ROCM_IMAGE}" || die \
  "could not pull ${VLLM_ROCM_IMAGE}. MI300X is gfx942 — confirm the current gfx942 tag on
   hub.docker.com/r/rocm/vllm/tags and re-run with --image, or use vllm/vllm-openai-rocm."

# ── 3. download models from HuggingFace (gated Gemma -> loud failure) ─────────
mkdir -p /data/hf-cache
log "downloading models for ${PROFILE} (cache: /data/hf-cache)"
HF_IDS="$(py "${SCRIPT_DIR}/render_compose.py" --profile "${PROFILE}" \
  --image "${VLLM_ROCM_IMAGE}" --control-plane-url "${CONTROL_PLANE_URL}" \
  | grep -oE 'vllm serve [^ ]+' | awk '{print $3}' | sort -u || true)"
for hf in ${HF_IDS}; do
  case "${hf}" in accounts/*|claude-*) continue ;; esac   # hosted ids, not HF repos
  log "  hf download ${hf}"
  if ! HF_HUB_ENABLE_HF_TRANSFER=1 docker run --rm \
        -e HF_TOKEN="${HF_TOKEN:-}" -v /data/hf-cache:/root/.cache/huggingface \
        "${VLLM_ROCM_IMAGE}" \
        python3 -c "from huggingface_hub import snapshot_download as s; s('${hf}')"; then
    case "${hf}" in
      google/gemma-*)
        die "Gemma repo ${hf} download failed (403?). These are GATED — accept the license at
             https://huggingface.co/${hf} with the account behind HF_TOKEN, then re-run." ;;
      *) die "model download failed for ${hf}" ;;
    esac
  fi
done

# ── 4/5. launch vLLM instances + node agent (idempotent) ─────────────────────
log "starting vLLM instances + node agent via docker compose"
export HF_TOKEN ADMIN_TOKEN NODE_NAME="${NODE_NAME:-B}"
docker compose -f "${COMPOSE_OUT}" up -d --remove-orphans

log "waiting for vLLM /health (up to 15 min for the brain to load)"
deadline=$(( $(date +%s) + 900 ))
while :; do
  pending=0
  while IFS= read -r port; do
    curl -fsS "http://localhost:${port}/health" >/dev/null 2>&1 || pending=$((pending+1))
  done < <(grep -oE '"[0-9]+:[0-9]+"' "${COMPOSE_OUT}" | tr -d '"' | cut -d: -f1 | sort -u)
  [ "${pending}" -eq 0 ] && { log "all vLLM instances healthy"; break; }
  [ "$(date +%s)" -ge "${deadline}" ] && { warn "${pending} instance(s) not healthy after 15 min — check 'docker compose logs'"; break; }
  sleep 10
done

# ── 6. node agent self-registers on its own startup; nudge as a fallback ─────
log "node agent will self-register with ${CONTROL_PLANE_URL}/api/admin/nodes/register"
log "bootstrap complete for profile ${PROFILE}"
