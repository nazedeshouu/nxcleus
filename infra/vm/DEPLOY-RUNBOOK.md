# Deploy runbook — multi-host cutover (amd / amdplatform)

Exact ordered commands for the final deploy wave. Puts the two new subdomains live while keeping the
existing hosts working. **Run top to bottom.** Anything in `<angle brackets>` is a value you supply.

## Topology this deploy establishes

| Host | Behavior | Cert |
|---|---|---|
| `amd.nxcleus.tech` | Marketing landing at `/`. Platform paths (`/build* /operations* /sandbox* /config* /traces* /replay* /login* /gallery*`) → **302** to `https://amdplatform.nxcleus.tech{uri}`. `/api/*` proxied (harmless). | Let's Encrypt |
| `amdplatform.nxcleus.tech` | Full app. `/` → **302** `/build` (lands on the cockpit). `/api/*` (SSE-safe) + SPA static. | Let's Encrypt |
| `nxcleus.tech` | Everything served, **no redirects** (unchanged). | Let's Encrypt |
| `165-245-152-181.sslip.io` | Everything served, **no redirects** (unchanged shared link). | Let's Encrypt |

Both new hosts are A records → `165.245.152.181`. **A host whose DNS isn't live yet only fails its
own cert — the others still issue** (Caddy issues per-host, no on-demand needed). Deploy can proceed
before DNS propagates; the new-host smoke checks just wait for DNS + cert.

## Coordinates

- **Mac (build + rsync source):** repo root `~/Projects/amd-hackathon` (referred to as `$REPO`).
- **VM:** `ssh -i ~/.ssh/nxcleus_deploy root@165.245.152.181`, repo at `/root/nxcleus`.
- deploy.sh derives the two new hosts automatically from `infra/vm/domain` (= `nxcleus.tech`):
  `NXCLEUS_LANDING_HOST=amd.nxcleus.tech`, `NXCLEUS_PLATFORM_HOST=amdplatform.nxcleus.tech`.
  **No new VM-local files needed.** (Override by exporting those two vars before `deploy.sh` if ever
  the prefixes change.)

---

## 0. Preflight (Mac)

```bash
cd "$REPO"
# The seed corpus is gitignored but MUST ship. Confirm all 8 DBs exist locally BEFORE building.
ls infra/seeds/out/*.db | wc -l          # expect 8 (bank clinic exchange freight insurer lawfirm ledger market)
# If 0 or missing: regenerate first (deterministic, minutes):
#   uv run --project backend python scripts/seed.py
```

## 1. Build the frontend (Mac)

Static output is arch-independent; build on the Mac.

```bash
cd "$REPO/frontend"
npm ci                # or: npm install
npm run build         # tsc -b && vite build  ->  writes frontend/dist
ls dist/index.html    # sanity
```

## 2. Snapshot for rollback, then rsync working tree → VM

Snapshot the current live artifacts on the VM first (cheap, enables instant rollback):

```bash
ssh -i ~/.ssh/nxcleus_deploy root@165.245.152.181 '
  cd /root/nxcleus
  infra/vm/backup_sqlite.sh                                  # consistent DB snapshot -> /root/nxcleus-backups
  cp -a frontend/dist frontend/dist.prev 2>/dev/null || true
  for f in Caddyfile docker-compose.yml deploy.sh; do cp -a infra/vm/$f infra/vm/$f.prev; done
'
```

Rsync the working tree. **The seed DBs and `frontend/dist` are gitignored but must ride — so do NOT
use `--exclude-from=.gitignore` / `--filter=':- .gitignore'` (that is the empty-corpus trap).** No
`--delete`: additive sync is safe and cannot drop the VM-local `.env` / `domain` / `extra_hosts`.

```bash
cd "$REPO"
rsync -avz \
  -e "ssh -i ~/.ssh/nxcleus_deploy -o StrictHostKeyChecking=accept-new" \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude '.env' \
  --exclude 'infra/vm/domain' \
  --exclude 'infra/vm/extra_hosts' \
  ./ root@165.245.152.181:/root/nxcleus/
```

Verify the corpus made it across:

```bash
ssh -i ~/.ssh/nxcleus_deploy root@165.245.152.181 'ls /root/nxcleus/infra/seeds/out/*.db | wc -l'   # expect 8
```

## 3. Set the login passwords in the VM `.env` (secrets — never committed)

The `api` service loads these via `env_file: ../../.env`; the compose `environment:` block passes them
through (key-only, so it never clobbers the `.env` value). `.env` already has `ADMIN_TOKEN`, so
`AUTH_SECRET` is **optional** (session signing falls back to `ADMIN_TOKEN` → sessions already persist
across restarts). Append only the keys that aren't already present — **never echo the values.**

```bash
ssh -i ~/.ssh/nxcleus_deploy root@165.245.152.181
# on the VM:
umask 077
cd /root/nxcleus
# check what's already set (names only):
grep -oE '^AUTH_[A-Z_]+=' .env || echo '(no AUTH_* yet)'
# append the ones you need (edit with a real editor or a heredoc; choose strong values):
cat >> .env <<'EOF'
AUTH_ADMIN_PASSWORD=<strong-admin-password>
AUTH_JUDGE_PASSWORD=<strong-judge-password>
# AUTH_SECRET=<optional 32+ hex; only if you want to rotate away from ADMIN_TOKEN>
# AUTH_SIGNUP_CODE=<optional invite code; set => POST /api/auth/signup requires it, unset => open self-serve signup (role 'judge')>
EOF
```

`AUTH_SIGNUP_CODE` flows through `env_file` like the other `AUTH_*` secrets — no compose change needed.
Self-serve signup only functions once auth is enabled (i.e. one of the passwords above is set).

> Alternative (equivalent): `export AUTH_ADMIN_PASSWORD=... AUTH_JUDGE_PASSWORD=...` in the deploy
> shell before step 4 — the key-only compose entries pick up an exported value and it wins over `.env`.
> Pick one path; the `.env` path is canonical (matches every other secret on this box).

## 4. Build image + (re)start the stack (VM)

Always via the wrapper — it composes `NXCLEUS_SITE` **and** the two new host vars and guarantees
auto-HTTPS never falls back to localhost.

```bash
cd /root/nxcleus
infra/vm/deploy.sh up -d --build
```

Expect the wrapper to print (confirms the new hosts are wired):

```
[deploy] NXCLEUS_DOMAIN=nxcleus.tech  NXCLEUS_SITE=nxcleus.tech, 165-245-152-181.sslip.io
[deploy] NXCLEUS_LANDING_HOST=amd.nxcleus.tech  NXCLEUS_PLATFORM_HOST=amdplatform.nxcleus.tech
```

## 5. Watch cert issuance for the two new hosts (VM)

```bash
infra/vm/deploy.sh logs -f caddy
# look for:  "certificate obtained successfully" {"identifier":"amd.nxcleus.tech"}
#       and: "certificate obtained successfully" {"identifier":"amdplatform.nxcleus.tech"}
# Ctrl-C once both appear. If a new host's DNS hasn't propagated, Caddy retries in the background —
# nxcleus.tech + the sslip host keep serving throughout. Re-check with the smoke tests below.
```

## 6. Post-deploy smoke checks (Mac or anywhere)

```bash
# a) API health + corpus loaded (the rebuilt image now reports corpus)
curl -s https://amdplatform.nxcleus.tech/api/health
#   expect: {"status":"ok","app":"Nxcleus","model_mode":"auto","corpus":"ok"}   <- corpus:"ok" not "missing"

# b) Seed corpus non-empty — one real row, id 1
curl -s 'https://amdplatform.nxcleus.tech/api/sandbox/companies/bank/tables/accounts?page_size=1'
#   expect: {"rows":[{"id":1,...}]}

# c) Landing host serves the marketing page at / (NOT a redirect)
curl -sI https://amd.nxcleus.tech/ | head -1                 # expect: HTTP/2 200
curl -s  https://amd.nxcleus.tech/ | grep -qi '<title'; echo "landing html: $?"   # 0 = ok

# d) Landing host bounces a platform path to the platform host, path preserved
curl -sI 'https://amd.nxcleus.tech/build/xyz?a=1' | grep -iE 'HTTP|location'
#   expect: 302  +  location: https://amdplatform.nxcleus.tech/build/xyz?a=1

# e) Platform host lands on the cockpit
curl -sI https://amdplatform.nxcleus.tech/ | grep -iE 'HTTP|location'
#   expect: 302  +  location: /build

# f) Existing hosts unchanged (everything served, no redirect)
curl -sI https://nxcleus.tech/build | head -1                # expect: HTTP/2 200 (SPA served, no 302)
curl -s  https://165-245-152-181.sslip.io/api/health         # expect: {"status":"ok",...}

# g) Login roundtrip (auth wall live). Adjust the JSON to your api's login contract if it differs.
curl -s -i -X POST https://amdplatform.nxcleus.tech/api/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"admin","password":"<strong-admin-password>"}' | grep -iE 'HTTP|set-cookie'
#   expect: 200  +  a session Set-Cookie. Then judge/<judge-password> should also work; a wrong
#   password should 401.

# h) BYOK connections list is clean (no duplicate rows). Repeated dev BYOK registration accumulates
#    duplicate api_connections rows in platform.db (nothing in the app/seed path creates them — only
#    the POST /api/connections endpoint does). A fresh prod DB has none; verify before the demo:
curl -s -b cookies.txt https://amdplatform.nxcleus.tech/api/connections | python3 -c \
  'import sys,json,collections; r=json.load(sys.stdin); r=r if isinstance(r,list) else r.get("connections",[]); \
   d=collections.Counter((c.get("name"),c.get("base_url")) for c in r); \
   print("dupes:", {k:n for k,n in d.items() if n>1} or "none")'
#   If any dupes: on the VM, keep the newest per (name, base_url) and drop the rest —
#   docker compose exec <app> sqlite3 /data/platform.db "
#     DELETE FROM api_connections WHERE id NOT IN (
#       SELECT id FROM api_connections a WHERE created_at =
#         (SELECT MAX(created_at) FROM api_connections b WHERE b.name=a.name AND b.base_url=a.base_url));"
#   (back up first: infra/vm/backup_sqlite.sh)
```

All green → deploy is done. Clean up rollback snapshots when satisfied:
`ssh … 'cd /root/nxcleus && rm -rf frontend/dist.prev infra/vm/*.prev'`.

---

## Rollback

Fast (revert to the pre-deploy artifacts snapshotted in step 2 — no Mac needed):

```bash
ssh -i ~/.ssh/nxcleus_deploy root@165.245.152.181 '
  cd /root/nxcleus
  [ -d frontend/dist.prev ] && rm -rf frontend/dist && mv frontend/dist.prev frontend/dist
  for f in Caddyfile docker-compose.yml deploy.sh; do [ -f infra/vm/$f.prev ] && mv infra/vm/$f.prev infra/vm/$f; done
  infra/vm/deploy.sh up -d --build
'
```

- **Config only** (Caddy/compose misbehaves, app fine): restore the three `infra/vm/*.prev` files and
  `infra/vm/deploy.sh up -d` — skips the image rebuild.
- **DB corruption:** restore newest `/root/nxcleus-backups/*.gz` into the `platform-data` volume
  (see `infra/vm/backup_sqlite.sh` for the volume/path), then `deploy.sh up -d`.
- **Full config revert in git:** the multi-host change lives in `infra/vm/{Caddyfile,deploy.sh,
  docker-compose.yml}` — `git revert` the deploy commit on the Mac, re-run steps 1–4.

## Validation already done (pre-deploy, on the VM's caddy:2, stack untouched)

`caddy validate` on the fully env-substituted Caddyfile → **Valid configuration**. `caddy adapt`
confirmed the exact per-host routing in the table above (proxy targets, the `/`→`/build` and
platform-path→`amdplatform` 302s with `{uri}` preserved, legacy hosts redirect-free).
