# infra/fleet/ — MI300X fleet automation + AMD account visibility report

One-command control of the elastic MI300X fleet, plus the read-only findings that make the "one
command" correct. **No script here creates a GPU droplet without an explicit `--yes`** — creation is
gated on the orchestrator's go (an idle 8× burns ~$15.92/hr, a rehearsal an hour).

## Scripts

| Script | Does | Spends? |
|---|---|---|
| `fleet_up.sh <P1\|P2\|P3>` | Create ONE MI300X droplet for the profile (atl1), sync `infra/`, run `bootstrap.sh` (pull vLLM image, download models, launch vLLM + node agent), verify the node self-registers. | **Only with `--yes`**. `--dry-run` validates + renders, spends nothing. |
| `fleet_down.sh` | Drain registered nodes (clean failover to Fireworks), then destroy every `nxcleus-fleet` droplet. Stops the clock. | Destroys (asks once; `--yes` for cron). |
| `fleet_status.sh` | Cross-references billing droplets (AMD account) vs registered nodes (control plane) + est. $/hr. | No — read-only. |
| `fleet_watchdog.sh` | Nodes billing + no active job > `IDLE_MINUTES` → Discord alert (once/episode); `--destroy-idle` also tears down. | No (unless `--destroy-idle` fires). |
| `fleet_lib.sh` | Shared config/helpers (sourced, not run). All values env-overridable. | — |

```bash
# rehearsal / demo (AFTER the orchestrator's go)
infra/fleet/fleet_up.sh P2 --dry-run     # sanity-check the plan first
infra/fleet/fleet_up.sh P2 --yes         # create + bootstrap the 8× hero profile
infra/fleet/fleet_status.sh              # what's up, what it costs
infra/fleet/fleet_down.sh                # the instant it's over — STOP THE CLOCK
```

The watchdog belongs on the control VM as a cron (install doctl there first for the accurate
droplet-based signal + the `--destroy-idle` path):

```bash
*/5 * * * * IDLE_MINUTES=30 /root/nxcleus/infra/fleet/fleet_watchdog.sh >> /var/log/nxcleus-watchdog.log 2>&1
```

`DISCORD_WEBHOOK_URL` (env or repo `.env`) enables the alert; without it the watchdog still logs.

---

## AMD account GPU visibility report (read-only probe, 2026-07-09)

Token authenticates BOTH `api.digitalocean.com` and `api-amd.digitalocean.com`; account active
("My AMD Team"), **droplet limit 10**.

### MI300X shapes — exact slugs (the fleet uses these)
| Shape | Slug | $/hr | Self-serve? |
|---|---|---|---|
| 1× MI300X (192 GB) | `gpu-mi300x1-192gb-devcloud` | $1.99 | **Yes** — `available: true, regions: ["atl1"]`; listed in atl1's per-region inventory |
| 8× MI300X (1536 GB) | `gpu-mi300x8-1536gb-devcloud` | $15.92 | **NO — request/allocation-gated** (see below) |

> Correction vs early spec drafts (02 §5): the slugs carry a **`-devcloud`** suffix. The bare
> `gpu-mi300x1-192gb` / `gpu-mi300x8-1536gb` names are the GA (standard-billing) shapes, not the
> hackathon-credit dev-cloud shapes.

**8× verdict — request-gated, not self-serve (high confidence, two agreeing read-only signals):**
- The 8× size object reports `available: true` but **`regions: null`** — while the 1× on the *same*
  AMD API reports `regions: ["atl1"]`. So regions DO populate here; the 8× simply has no enabled
  region, meaning a create call has nowhere to land. `available: true` = catalog-orderable, not
  creatable.
- atl1's per-region size inventory lists the 1× and **omits** the 8×.
- Not quota-gated (`droplet_limit: 10`, we use 1) and not hard-disabled — it's a capacity/allocation
  grant. **The human must request 8× MI300X dev-cloud capacity in atl1** (AMD Dev Cloud console GPU
  section, or the hackathon organizers/AMD) before P2/P3 can boot. `fleet_up.sh P2 --yes` will fail
  at the create step until then — do not use it as a probe.
- Nuance: DO's public marketing lists the **GA** `gpu-mi300x8-1536gb` (standard billing) as
  self-serve in atl1 — a possible fallback IF the ~$100 credit covers the GA shape (unconfirmed).

### Region
**MI300X is `atl1` (Atlanta) only.** No other region lists an mi300x size. `atl1` sells **no
standard droplet sizes** on either API — which is why the control VM lives in `nyc1` (nearest US-East,
~15–20 ms) rather than co-located (spec 01 §1 divergence, documented in `infra/vm/README.md`).

### Base image for the droplet
`gpu-amd-base` — "AMD AI/ML Ready Image" (GPU drivers + Docker; newest AMD base, 2026-07-08). Other
options seen: `amddeveloperclou-rocm724` (ROCm 7.2.4), `amddeveloperclou-vllm0230rocm724`
(vLLM 0.23.0). **Host ROCm tops out at 7.2.4**; our serving container is ROCm 7.13.0 — a newer
userspace on the host kernel driver. First-boot validation item: confirm the 7.13 container runs on
the `gpu-amd-base` amdgpu driver, else fall back to `vllm/vllm-openai-rocm` or a 7.2.4-train image.

### vLLM ROCm serving image — CORRECTED
Pinned tag `rocm/vllm:rocm7.13.0_gfx942_...` **does not exist (Docker Hub 404).** MI300X = gfx942 is
published under AMD's datacenter-family tag: **`rocm/vllm:rocm7.13.0_gfx94X-dcgpu_ubuntu24.04_py3.13_pytorch_2.10.0_vllm_0.19.1`**
(verified 200). Corrected in `infra/droplet/bootstrap.sh`, `render_compose.py`, and spec 11 §8.

### HuggingFace Gemma gate — CLEAR
`google/gemma-4-31B-it` and `google/gemma-4-26B-A4B-it` both resolve `config.json` **HTTP 200**
(with and without token), `gated: false`, `model_type: gemma4`. **No license wall, no pending
clicks** — the droplet model download will not 403. (bootstrap.sh keeps its gated-repo loud-failure
guard regardless, harmless if it never fires.)
