# Control VM — deploy notes (spec 01 §1–2)

The always-on control plane: FastAPI + SQLite + Caddy on a **DigitalOcean s-2vcpu-4gb**. **It runs
zero LLM inference** — every token is generated on AMD silicon (the MI300X fleet or the Fireworks
fallback). This is the product architecture, not a hackathon convenience (lift the 01 §2 paragraph
into the README + deck).

## Live deployment (as provisioned 2026-07-09)

| Thing | Value |
|---|---|
| Droplet | `nxcleus-control` — s-2vcpu-4gb, image `docker-20-04`, **region `nyc1`** |
| Reserved IP | `165.245.152.181` (rebuild-safe; DNS/URL survive a droplet rebuild) |
| Live URL | **https://165-245-152-181.sslip.io** (real Let's Encrypt cert via Caddy) |
| SSH | `ssh -i ~/.ssh/nxcleus_deploy root@165.245.152.181` (key fp SHA256 `qnyrsiccet2lPrT+OHZU26eD4Nv4+P1AepnNiLZ+K1s`) |
| Repo on VM | `/root/nxcleus` (rsync of the working tree; `.env` scp'd here, never committed) |

> **Region note (spec 01 §1 divergence):** 01 §1 assumed the VM shares the fleet's region. Reality:
> the MI300X Dev Cloud is **atl1-only**, and **atl1 offers no standard droplet sizes** (verified on
> both `api.digitalocean.com` and `api-amd.digitalocean.com`). The VM therefore lives in `nyc1`, the
> nearest US-East region that sells `s-2vcpu-4gb` (~15–20 ms RTT to atl1) — fine for a network-bound
> control plane. Fleet scripts (`infra/fleet/`) target atl1.

## Deploy / redeploy

Always deploy via the wrapper — it guarantees the auto-HTTPS domain is set (a bare `docker compose
up` would fall back to `localhost` and drop the cert):

```bash
# on the VM
cd /root/nxcleus
infra/vm/deploy.sh up -d --build     # build the API image (native amd64) + (re)start api + caddy
infra/vm/deploy.sh ps                # status
infra/vm/deploy.sh logs -f caddy     # follow logs
```

The domain is read from `infra/vm/domain` (VM-local, not committed). **Swapping to nxcleus.com is a
one-line change:** `echo nxcleus.com > infra/vm/domain && infra/vm/deploy.sh up -d`, then point an A
record at the reserved IP — Caddy fetches the new cert on the next request. The Caddyfile itself
needs no edit (it reads `{$NXCLEUS_DOMAIN}`).

- Frontend: prebuilt `frontend/dist` is bind-mounted into Caddy at `/srv/www` and served at `/`
  (static output is arch-independent, so it may be built on any machine). SPA deep-links fall back
  to `index.html`. Rebuild the frontend and rerun `deploy.sh up -d` to publish a new UI.
- API is **not** published to the host (`expose: 8000`, not `ports:`) — reachable only through Caddy
  over the compose network. `curl localhost:8000` on the host will (correctly) refuse; test via the
  public URL or `docker compose exec`.
- `MODEL_MODE=auto`: real backends when a fleet node is registered + healthy or keys are present,
  else MockClient (badged). `mock` = fully offline; `live` = require real backends.

## `.env` on the VM (secrets — scp'd to `/root/nxcleus/.env`, never committed)

`env_file: ../../.env` loads these into the api container; `environment:` in the compose file wins
over any duplicate. Every var has a dev default in `backend/app/config.py`, so the app boots without
a full `.env`. What the **control plane** actually uses:

| Var | Purpose on the VM |
|---|---|
| `ANTHROPIC_API_KEY` | planner seat (default mode) — the one designed-in external call |
| `FIREWORKS_API_KEY` | Fireworks fallback bindings (P0 / fleet-down) — keeps the URL alive |
| `FIREWORKS_BASE_URL` | override for the Fireworks endpoint (default `https://api.fireworks.ai/inference`) |
| `ADMIN_TOKEN` | admin endpoints + node self-registration (`X-Admin-Token`) |
| `DIGITALOCEAN_ACCESS_TOKEN` | not required by the API; used by `infra/fleet/` from the operator shell |
| `DISCORD_WEBHOOK_URL` | optional — idle-fleet + budget alerts |
| `SOVEREIGN_DEFAULT`, `ALLOW_RAW_ON_AMD_HOSTED`, `FIREWORKS_DAILY_BUDGET_USD`, `SANDBOX_*` | policy/budget knobs (01 §6) |

Set by the **compose file** (not `.env`): `SQLITE_PATH=/data/platform.db`, `DATA_DIR=/data`,
`MODEL_MODE=auto`, `APP_BASE_URL=https://$NXCLEUS_DOMAIN`. `HF_TOKEN*` is a **fleet/droplet** concern
(model downloads) — not needed on the control VM.

## Seed the demo feed

Runs the seed script in mock mode against the live DB volume (stop api first for SQLite
single-writer safety; the static landing page stays up):

```bash
cd /root/nxcleus
docker compose -f infra/vm/docker-compose.yml stop api
docker compose -f infra/vm/docker-compose.yml run --rm --no-deps \
  -w /app -e PYTHONPATH=/app -e MODEL_MODE=mock \
  -v /root/nxcleus/scripts:/app/scripts api python scripts/dev_seed.py
infra/vm/deploy.sh start api
```

## Backups (spec 05 §6)

`infra/vm/backup_sqlite.sh` takes a consistent `sqlite3 .backup` snapshot of the `platform-data`
volume, gzips it to `/root/nxcleus-backups/`, and keeps the newest 7. Installed as a **root cron at
04:07 daily**. Run on demand before a demo: `infra/vm/backup_sqlite.sh`.

## Reboot survival

Both services are `restart: unless-stopped` and the resolved env (incl. `NXCLEUS_DOMAIN`) is baked
into each container at create time, so a VM reboot brings the stack — and the same URL/cert — back
with no operator action. Docker starts on boot (systemd). Verified with a live reboot.

## Fleet + node agents

The MI300X droplet is booted separately from **`infra/fleet/`** (`fleet_up.sh <P1|P2>` /
`fleet_down.sh` / `fleet_status.sh`, targeting atl1 via `--api-url https://api-amd.digitalocean.com`).
Node agents self-register against `POST /api/admin/nodes/register` (`X-Admin-Token`) and the control
plane polls their `/telemetry` every 2 s. In dev, `scripts/stub_node.py` stands in for a real agent.

## Ports

| Port | Service |
|---|---|
| 80/443 | Caddy (auto-HTTPS; 80 → 308 → 443) |
| 8000 | uvicorn (compose-internal only; not host-published) |
| 9100 | node agent `/telemetry` (on fleet nodes, polled by the control plane) |
