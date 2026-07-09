# Control VM — deploy notes (spec 01 §1–2)

The always-on control plane: FastAPI + SQLite + Caddy on a **DigitalOcean s-2vcpu-4gb** (same
account / region / `doctl` as the MI300X fleet). **It runs zero LLM inference** — every token is
generated on AMD silicon (the fleet or the Fireworks fallback). This is the product architecture, not
a hackathon convenience (lift the §2 paragraph into the README + deck).

## First deploy

```bash
# on the VM (native amd64 — images build here; this repo's dev Mac is arm64/colima, no buildx)
git clone <repo> nxcleus && cd nxcleus
cp .env.example .env    # fill ANTHROPIC_API_KEY, FIREWORKS_API_KEY, DIGITALOCEAN_ACCESS_TOKEN, ADMIN_TOKEN
export NXCLEUS_DOMAIN=nxcleus.example.com   # for auto-HTTPS; omit for localhost
docker compose -f infra/vm/docker-compose.yml up -d --build
```

- API at `https://$NXCLEUS_DOMAIN/api`, OpenAPI at `/docs`. SSE streams flush immediately (Caddy
  `flush_interval -1`).
- SQLite + packages live in the `platform-data` volume (`/data`). Nightly `sqlite3 .backup` cron is
  cheap insurance before demo days (05 §6).
- `MODEL_MODE=auto`: real backends when a fleet node is registered + healthy or keys are present,
  else MockClient (badged). Set `mock` to run fully offline, `live` to require real backends.

## Fleet + node agents

The 8× MI300X droplet is booted separately (`infra/droplet/`, the AI engineer's zone). Node agents
self-register against `POST /api/admin/nodes/register` (X-Admin-Token) and the control plane polls
their `/telemetry` every 2 s. In dev, `scripts/stub_node.py` stands in for a real agent.

## Ports

| Port | Service |
|---|---|
| 80/443 | Caddy (auto-HTTPS) |
| 8000 | uvicorn (internal; not exposed to the host) |
| 9100 | node agent `/telemetry` (on fleet nodes, polled by the control plane) |
