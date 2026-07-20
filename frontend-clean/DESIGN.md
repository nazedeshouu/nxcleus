# Nxcleus — Design Direction

Short and decisive. The build follows this doc; if the build and this doc disagree, this doc is wrong and gets updated.

## 0. The one idea

**The boundary is the brand.** Nxcleus sells sovereignty: your data never leaves your walls, and only a sanitized brief ever crosses to a frontier model. The entire design language makes *inside-the-walls vs. outside* legible at a glance. Cool, luminous, sealed interior; muted, cooler exterior; a single precise threshold between them. Everything that reads as "safe / local / yours" is cool-bright; the one thing that leaves is small, outlined, and visibly sanitized.

Two temperatures, one wall (redesign, 2026-07-09):

- **Landing** (`/`) — the daylight approach to a sealed system. Light editorial, layered generated imagery, film grain, island nav. Trust-first for a bank's compliance officer. `VARIANCE 6 / MOTION 5 / DENSITY 3`.
- **The platform** (everything behind "Enter the platform") — *inside the walls*. The entire app chrome lives in sealed midnight (`[data-temp="inside"]`): luminous cyan telemetry, mono numerals, a faint architectural field behind the panels. Crossing into the app IS crossing the boundary; the wedge band on the landing is the one glimpse inside. Sovereign Mode deepens the same interior to absolute dark + teal seal. `DENSITY 7` in the cockpit.

## 1. Brand token

Product name is an open decision (O1 → resolved: **Nxcleus**). It lives in exactly one place: `src/brand/brand.ts` (`BRAND.name`) + `<Logo/>`. The final name is a one-file change. Nothing else hardcodes the string.

## 2. Type

Self-hosted, no CDNs. `font-display: swap`, woff2, subsetted.

- **Lenia Sans** — display + UI. Weights: 300 / 400 / 500 / 600 / 700 / 900, plus Italic (400) and SemiBold Italic (600) for in-family emphasis. Emphasis inside a headline is italic of the *same* family, never a swapped serif.
- **CS Arcel Mono** — data, code, ledger, telemetry, seq numbers, costs, hashes, GPU stats. This is the "machine truth" voice; anything numeric or audit-grade is mono. Tabular numerals on.

Scale (fluid, clamp-based; see `tokens.css`): display `clamp(2.6rem, 6vw, 5rem)` → body `1rem` → micro `0.75rem`. Display is `letter-spacing: -0.02em`, `line-height: 1.02`. Body `line-height: 1.6`, `max-width: 66ch`.

## 3. Color system

Cool near-white base, one deep-cyan accent, temperature-coded zones. Not AI-purple, not a gradient hero.

**Neutrals**
- ink `#0c1417` (cool near-black; never pure `#000`)
- paper `#f6fafb` · surface `#ffffff` · surface-sunk `#eef4f7`
- hairline `#d8e3e8` · muted text `#5b6b72`

**Accent (the one accent, used identically everywhere)**
- accent `#1c7aa3` (deep cyan-blue) · accent-strong `#125b7d` · accent-pale `#dceff6` · accent-mid `#8cc5dd`

**Zones** (temperature = position relative to the wall)
- `LOCAL` cool blue `#1c7aa3` — inside the walls, the home color
- `AMD_HOSTED` amber `#cf8a3a` — Fireworks fallback, warm, "hosted but ours," badged as demo infra
- `CUSTOM` slate-indigo `#5b6b90` — BYOK endpoints
- `EXTERNAL` graphite `#57636b` — the one designed-in crossing; neutral, cooler, unmistakably *outside*

**Data class**
- `RAW` — filled ink chip, lock glyph. Sealed. Reads as heavy, contained. Never leaves LOCAL.
- `SANITIZED` — outlined, cool, light. The only thing that crosses the wall.

**Semantic**
- verify/success green `#2f9e6b` (certified, passed, green-flag)
- warn amber `#cf8a3a` (budget, fallback-serving)
- violation red `#e5484d` — *a red that means it.* Only `egress.violation` and hard blocks. Never decorative.

**Sovereign Mode** — a serious, unmistakable state change, not a color swap. The already-dark interior deepens to `#03090c` and every accent re-tints to the sealed teal `#3fd8c4` ("zero external calls"). It should feel like *shields up*, calm and absolute.

**Theme mechanics (locked).** All module CSS speaks semantic tokens only (`--paper/--surface/--hairline/--text-muted/washes`). `tokens.css` remaps the full set under `[data-temp="inside"]` (platform midnight) and `[data-temp="inside"][data-sovereign="true"]` (sovereign teal). Dark blocks that must stay dark in every theme use `--seal`/`--seal-on`, never `--ink` as a fill. `--glow-accent` is the luminous box-shadow, a no-op in light. A fixed film-grain overlay lives on `body::after` (alpha baked into the SVG).

## 4. Materiality & shape

- One radius scale: 4 / 8 / 12 / 16, pills for interactive chips. No mixed systems.
- Cards only where elevation is real hierarchy. Elsewhere: hairlines, `divide`, negative space. The cockpit uses 1px lines over boxes.
- Shadows tinted cool (`rgba(12,20,23,·)`), never pure black. Sparingly.
- No random borders, no glassmorphism-on-everything. Glass reserved for the sovereign-mode overlay and the sticky status bar only.

## 5. Motion (respect `prefers-reduced-motion`)

- Landing `MOTION 5`: entrance fades + 16px rise on hero and section reveals (IntersectionObserver, `once`), CTA press `translateY(-1px)`, the boundary diagram animates the sanitized brief crossing the wall once on view. Easing `cubic-bezier(0.16,1,0.3,1)`. Every animation is motivated (hierarchy / story / feedback).
- Build view: motion = *state truth.* Stage focus slides as `job.stage_changed` fires; streamed deltas type in; egress pings pulse once; the violation banner is the only alarming motion, and it earns it. No idle loops except the "live" heartbeat dot on the connection indicator.
- All motion collapses to static under reduced-motion.

## 6. Imagery

Raster art uses exact palette anchors: `hero-archive-crossing.jpg` is the full-bleed archive threshold in the hero; `wedge-dark.webp` is the midnight landing wedge; `inside-field.webp` is the quieter platform backdrop; `field-light.webp` closes the landing CTA. Abstract architectural sovereignty only: no robots, brains, or circuit-board clichés. No text in images. Below-the-fold assets are lazy. Functional icons and diagrams stay SVG/DOM (Phosphor, one family). The boundary diagram is DOM/SVG because it communicates data and animates once.

## 7. Per-view layout intent

### 7.1 Landing (`/`)
Narrative spine = the pitch from `IDEA.md`, in order:
1. **Hero** — one-viewport, full-bleed archive threshold: copy anchored bottom-left, actions on the same baseline, and a compact boundary monitor in the open upper-right field. Primary CTA "Enter the platform" + secondary "Judge sandbox". AMD/ROCm/vLLM credibility line present (legible < 30s).
2. **The boundary moment** — the hero diagram: raw context stays sealed in LOCAL; a single *sanitized brief* crosses to EXTERNAL; Sovereign Mode = zero crossings. Animated once on view. This is the astonish beat.
3. **The lifecycle** — Build once / Operate forever / Refine on demand. Three phases, not three equal cards; a horizontal timeline with weight on "Operate forever."
4. **Money slide** — frontier intelligence as capex not marginal cost: a small honest chart, build cost once vs. flat per-run local opex, vs. competitors paying tokens *and* surrendering data every run.
5. **The wedge** — "We operate where external AI is banned." Full-width statement.
6. **How it runs on AMD** — MI300X fleet, vLLM/ROCm, model BoM drives GPU provisioning; live-telemetry teaser.
7. **CTA** — into the platform + judge sandbox. One contact/entry intent, one label.

At least 4 distinct layout families; ≤ 2 eyebrows total; zero em-dashes; no scroll cues; no decorative dots; hero fits one viewport.

### 7.2 Build view (`/build/:jobId`) — mission control
Composed, choreographed, not 12 equal boxes. Persistent frame + stage-driven hero focus:
- **Top:** stage rail (0-7, live), goal pin ("what we promised"), connection + sovereign indicators, quote/cost meter.
- **Center (stage-driven hero):** whatever the current stage makes primary — intake dialogue + sanitization report at stage 0; plan stream + BoM at 1-2; wave board with worker panels at 4; validation wall + defect board at 5-6; delivery at 7.
- **Left rail:** amendment log (hash-chained audit ticker), consults with sanitization receipts.
- **Right rail:** GPU telemetry strip (the AMD-legible-in-30s surface) + egress/network monitor (violation = unmissable red banner across the top).
The UI state for a job **is a fold of its events** (`reduce(events) -> view`), which makes replay and ×16 fixtures free and identical to live.

## 8. Stack

React 18 + TS + Vite. react-router. TanStack Query for REST. Custom event-fold store (plain reducer, no library) so the same fold serves live SSE, `VITE_MOCK=1` fixtures, and the future replay player. Styling: hand-authored CSS tokens + CSS Modules — a distinctive system, no Tailwind default look, no component-library skins.

---

# Wave 2 handoff (fresh-agent onboarding)

Wave 1 is green-flagged. This section is self-contained so a new frontend agent can execute Wave 2 without the prior transcript. Read §0-8 above first (the design system is locked; extend it, do not restyle it).

## Environment & commands
- Node 24 + npm (no pnpm). From `frontend/`: `npm install`, `npm run dev` (defaults to :5173; Wave-1 used `-- --port 5273`), `npm run build`, `npx tsc --noEmit -p tsconfig.app.json`.
- **API base is relative `/api`** (spec 06). `vite.config.ts` proxies `/api` → `http://localhost:8000` in dev (override `VITE_PROXY_TARGET`); Caddy does the same in prod. Set `VITE_API_BASE` only to point at a non-same-origin host. `VITE_MOCK=1` forces fixtures everywhere.
- Backend serves at `:8000`; when it is up, REST/SSE just work through the proxy, no code change.

## File map (everything is in `frontend/`, the sole ownership zone)
- `src/lib/events.ts` — the whole 06 §3 catalog typed: `NxEvent` discriminated union + every payload interface. **Seam decisions ruled in our favor and now locked**: amendments carry `prev_hash`+`hash`; `telemetry.gpu` is per-GPU rows with `{node,gpu,vram_used_gb,vram_total_gb,util,power_w,toks_per_s}`; `boundary.sanitized` is `{findings[],never_leaves[],brief_tokens}`; `model.call` splits `tokens_in`/`tokens_out`; REST envelopes `GET /jobs`→`{jobs[]}`, `/config/public`→`{sovereign,fallback_serving,profile,demo}`.
- `src/store/jobStore.ts` — `JobView` shape + `foldEvent(view, ev)` + `foldEvents(events)`. Pure reducer; returns a new top-level ref per event; dedupes by `seq` (idempotent replay/reconnect); has a `never` exhaustiveness guard so a new event type won't compile until it has a fold case.
- `src/store/useJobStream.ts` — the hook that picks source (live SSE vs fixture player) and folds into React state. Returns `{view, conn, mock, inject}`.
- `src/api/` — `config.ts` (base + demo token in localStorage), `client.ts` (typed REST for 06 §2; Wave 2 adds `/processes`, `/runs`, `/sandbox`, `/models`, `/connections`, `/seats`, `/economics`), `sse.ts` (EventSource wrapper: `from_seq` replay-then-tail + native `Last-Event-ID` reconnect + heartbeat watchdog; reusable for `/runs/{id}/events`, `/fleet/telemetry`, `/egress/stream`, `/replay/{scope}`).
- `src/fixtures/` — `kycJob.ts` (full stage-0→7 KYC stream + `sovereignViolationEvent()`), `player.ts` (`playEvents(events, onEvent, {speed})` honoring relative timestamps).
- `src/components/build/` — the cockpit: `build.css` (namespaced `.bv-*`, imported once by BuildView), `Panel.tsx` primitive, `TopStrip`, `IntakePanel`, `PlanPanel`, `AuditRail`, `WaveBoard`, `QaPanels` (ValidationWall/DefectBoard/DeliveryMoment), `Telemetry`, `EgressMonitor`.
- `src/components/shell/` — `PlatformLayout` (nav + sovereign/fallback/connection surfaces + `data-sovereign` chrome), `DemoUnlock`, `usePublicConfig`.
- `src/components/ui/` — `ZoneBadge`, `DataClassChip`, `Reveal`. `src/components/landing/` — `BoundaryDiagram` (interactive Sovereign toggle).
- `src/routes/` — `Landing`, `JobList`, `BuildView`, `Placeholder` (Operations/Gallery/Sandbox are Placeholder stubs to replace).
- `src/brand/` — `brand.ts` (`BRAND.name`), `Logo.tsx`. `src/styles/` — `tokens.css` / `fonts.css` / `base.css`. `src/assets/img/` — hero webp set + og.

## Store/fold architecture (reuse this pattern for every event-driven view)
The UI state for any scope IS `reduce(events)`. To build a new live view (a run, the fleet, the sandbox queue): define its `View` slice + `foldX(view, ev)` in the same style, then a `useXStream(id)` hook mirroring `useJobStream` (SSE via `openEventStream` when live, `playEvents` over a fixture when mock). Components read the folded view; they never touch the socket. This is why the same code path serves live, fixtures, and replay.

## Replay player = the fixture player, generalized (cheap win)
`playEvents()` already replays any ordered `NxEvent[]` at a speed multiplier through the fold. The replay route just fetches `GET /replay/{scope}` (09 §6), feeds the returned events to `playEvents` with a transport bar (play/pause/seek/speed) driving `foldEvents(events.slice(0, cursor))`. No new fold, no new components — reuse `BuildView`'s panels with the folded view.

## Wave 2 build list (priority order)
1. **Operations registry** (`/operations`, `/processes/{id}`): registry table (`GET /processes`), process detail with versions/tickets/cost-trend, version diff (`/versions/{v}/diff`), run-a-batch (`POST /processes/{id}/runs`, demo-gated), live run view via `/runs/{id}/events` (fold `run.*`/`warranty.ticket`/`review.decided` — slices already exist in the store).
2. **Judge sandbox** (`/sandbox`): three companies (`/sandbox/companies`), browsable mock tables (`/tables/{t}?page=`), suggested + freeform prompt → `POST /sandbox/runs` → opens a process-mode BuildView; queue via `/sandbox/queue` + `sandbox.*` events. This is the judge-run centerpiece.
3. **Money-slide economics** page (`/economics/summary`, 10 §6) — promote the landing chart to real data.
4. **Replay player** (see above).
5. **Gallery** (`/gallery`): the five demos as launchable seed kits.
6. **Seat-config / BYOK UI** (`/models`, `/connections`, `/seats/{seat}/binding`): capability-flag registry + connection add + seat rebinding; `config.*` events already fold. Key material is write-only/masked (06).
7. **Process-mode Build view variant**: stage rail already skips 4/5 when `mode==="process"`; add the corpus fan-out board (unit-per-worker grid) and the aggregation dashboard.

## Guardrails (do not regress)
- Only `SANITIZED` ever shows crossing to `EXTERNAL`; `RAW` chips stay sealed/LOCAL. Keep the boundary legible.
- Zero em-dashes in any rendered copy. One accent. Landing stays light; cockpit stays dense.
- `fonts/` at repo root is READ-ONLY source; copy into `frontend/`, never modify it.
- Respect `prefers-reduced-motion` (all motion already gates on it).
