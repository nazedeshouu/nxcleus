# Nxcleus Wireframe Kit — Shared Agent Brief

You are one of a fleet of agents each producing ONE self-contained themed wireframe HTML
page for the Nxcleus platform. Read this whole file first, then build only YOUR page.
Consistency across the fleet comes from everyone obeying this contract exactly.

**Nxcleus** = an adaptive-sovereign platform. A customer describes an automation they want;
the platform runs it through a **0–7 build pipeline** (seat-based model routing across
LOCAL MI300X / AMD-hosted Fireworks / EXTERNAL Anthropic), keeping raw data behind a
data boundary, and delivers a **versioned, audited automation process** into an Operations
registry that can be re-run on new data with a warranty. Full glossary: `docs/specs/00-INDEX.md`.

These are **mid-fi wireframes**: themed to look like the shipping product (sealed-midnight),
but their JOB is to expose *every functional step, field, label, and control* and to mark
**what is actually functional vs. planned vs. stub**, so the team can iterate on function next
session. Fidelity of layout matters; pixel perfection does not. Label everything.

---

## 1. Non-negotiable output rules

1. Write exactly one file to the path given in your task. Overwrite if it exists.
2. The page MUST be self-contained: inline the ENTIRE contents of
   `docs/wireframes/_kit.css` verbatim inside a single `<style>` block in `<head>`.
   (Read that file; paste it. Do not `<link>` to it.) Do not invent a second palette.
3. Do NOT emit `<!DOCTYPE>` wrappers differently than the skeleton below — follow it exactly,
   including the `<!--WF:START slug-->` / `<!--WF:END-->` markers (an assembler concatenates
   pages by these markers — pages without them break the combined view).
4. Use ONLY the `wf-` component classes from the kit (`.wf-panel`, `.wf-field`, `.wf-input`,
   `.wf-btn`, `.wf-badge`, `.wf-chip`, `.wf-steps`, `.wf-note`, `.wf-table`, `.wf-ledger`, …).
   If you need a one-off style, add a `<style>` rule scoped under `#wf-<slug>` — never restyle
   a `.wf-` class globally.
5. Every page carries: the top-bar shell, a legend, a page header with the real route, the
   mocked screen, and a **status ledger** footer (§5). No lorem ipsum — use realistic Nxcleus
   content (real seat names, real endpoint paths, plausible KYC/AML sample data).
6. Static mock only — no JS behavior required. `cursor:default` on controls (kit already does this).

---

## 2. The status vocabulary — label EVERYTHING

Every screen region and every interactive control gets one status. Put a `<span class="wf-badge …">`
on section headers and `<sup class="wf-tag …">` on individual controls where it clarifies.

| Badge | Class | Means |
|---|---|---|
| ● FUNCTIONAL | `fn` | Wired end-to-end: frontend calls a real backend endpoint that exists and returns real data. |
| ◈ PLANNED | `plan` | Designed / speced but not built, OR UI exists but backend endpoint is missing. |
| ◌ STUB / MOCK | `stub` | Renders from fixtures / hardcoded demo data, or presenter-only, or placeholder. |

**How to decide (the rubric — do this, don't guess):**
- Open your screen's route file in `frontend/src/routes/*.tsx` (mapping in §4).
- If it imports from `../api/client` and calls a method that maps to an endpoint present in the
  **implemented endpoint list (§3)** → that data path is **FUNCTIONAL**.
- If the route imports from `fixtures` and renders that → **STUB** (note: several routes have a
  live-with-fixture-fallback pattern; if it prefers live and only falls back, mark FUNCTIONAL
  with a STUB-fallback note).
- If it renders `Placeholder.tsx` → **PLANNED**.
- If a control's endpoint is NOT in §3 → **PLANNED**.
- SSE-driven live regions: FUNCTIONAL if the route wires `sse`/EventSource to a real
  `/events` or `/egress/stream` channel (§3).
- When genuinely unsure, mark **PLANNED** and say why in the ledger. Be conservative and honest —
  the team relies on these labels being correct.

Cross-check intent against the relevant spec (§4) so PLANNED items are the *designed* behavior,
not something you invented.

---

## 3. Implemented backend endpoints (ground truth — from FastAPI routers)

If an endpoint is here, its data path can be FUNCTIONAL. If a control needs one that's absent, it's PLANNED.

```
GET  /api/health · /api/config/public · /api/manifest
Jobs:      GET /jobs · GET /jobs/{id} · GET /jobs/{id}/events(SSE) · /jobs/{id}/plan · /jobs/{id}/quote
           POST /jobs · /jobs/{id}/messages · /jobs/{id}/answers · /jobs/{id}/policy
                /jobs/{id}/confirm-spec · /jobs/{id}/approve-quote · /jobs/{id}/abort
Processes: GET /processes · /processes/{id} · /processes/{id}/versions/{v}/diff
                /processes/{id}/package/{v}/{path}
           POST /processes/{id}/instantiate · /processes/{id}/refine · /processes/{id}/runs
Runs:      GET /runs/{id} · /runs/{id}/events(SSE) · /runs/{id}/units · /runs/{id}/report
                /runs/{id}/export.csv · /runs/{id}/next-steps
           POST /runs/{id}/next-steps · /units/{id}/review
Sandbox:   GET /sandbox/companies · /sandbox/companies/{id}/tables · /sandbox/companies/{id}/tables/{t}
                /sandbox/companies/{id}/terms · /sandbox/queue
           POST /sandbox/runs
Config:    GET /connections · /models · /seats(implied via config) · /fleet · /fleet/telemetry
           POST /connections · /connections/{id}/models · DELETE /connections/{id}
           PUT  /seats/{seat}/binding · POST /admin/sovereign · /admin/nodes/register · /admin/nodes/{id}/drain
Economics: GET /economics/summary · /egress · /egress/stream(SSE) · /tickets · /tools · /traces · /traces/{id}
Replay:    GET /api/replay/{scope}
Proxy:     POST /proxy/complete  (process-runtime → control plane, model calls)
```

---

## 4. Route → file → spec → data-source map (recon)

| Route file | Live? | Data source | Governing spec |
|---|---|---|---|
| `Landing.tsx` (`/`) | SSE demo | marketing + demo stream | design plan; two-temp system |
| `JobList.tsx` (`/build`) | LIVE + fixtures fallback | `GET /jobs` | 03, 06 |
| `BuildView.tsx` (`/build/:jobId`) | fixtures + SSE | `GET /jobs/{id}` + `/events` SSE | **03 (stages 0–7)**, 07, 08, 10 |
| `Operations.tsx` (`/operations`) | LIVE + SSE | `GET /processes` | 04 |
| `ProcessDetail.tsx` (`/operations/:id`) | LIVE + SSE | `/processes/{id}`, `/runs/*`, diff, refine | 04, 10 |
| `Gallery.tsx` (`/gallery`) | LIVE + fixtures | `GET /processes` / replay list | 09 |
| `Replay.tsx` (`/replay/:kind/:id`) | — | `GET /api/replay/{scope}` | 09 §6 |
| `Sandbox.tsx` (`/sandbox`) | LIVE + SSE | `/sandbox/*` | 09 |
| `Config.tsx` (`/config`) | LIVE + SSE | `/connections`, `/models`, `/seats`, `/fleet` | 02 §7–8, 11, 01 |
| `Traces.tsx` (`/traces`) | LIVE + fixtures + SSE | `GET /traces`, `/egress/stream` | 06, 10 |

Read your route's `.tsx`, its CSS module (for the real section layout), and the components it
imports under `frontend/src/components/`. Read the governing spec section for the intended flow,
fields, and any not-yet-built behavior.

**Build pipeline stages (from spec `docs/specs/03-build-pipeline.md`)** — each is its own wireframe:
- Stage 0 — Intake: confidentiality policy (upload / type / **voice dictation → local Whisper**),
  context intake (codebase / database / files), mode classification, data-boundary decision.
- Stage 1 — Planning: the Plan JSON artifact (modules, waves, task_flags, model BoM).
- Stage 2 — Rehydration + Certification: certifier RAW access, constrained amendments, consult
  sanitization gate, **goal statement** emission.
- Stage 3 — Quote: deterministic quote engine (GPU-seconds, model rates), approve/decline.
- Stage 4 — Parallel codegen in waves: BoM panel, topological waves, **conductor** review between waves.
- Stage 5 — Consolidation (build mode) / aggregation (process mode).
- Stage 6 — Adversarial QA + goal check: defect board, Numeric Oracle, inspector loop, tickets.
- Stage 7 — Delivery → Operations registry: package manifest, invoice.

---

## 5. Page skeleton (copy this exactly; fill the middle)

```html
<!--WF:START {{SLUG}}-->
<section class="wf-page" id="wf-{{SLUG}}">
  <div class="wf-shell">
    <!-- header -->
    <div class="wf-crumb">Nxcleus · <b>{{SECTION e.g. Build Pipeline}}</b> · Wireframe</div>
    <h1 class="wf-title">{{Human screen name}} &nbsp;<span class="wf-route">{{/route/path}}</span></h1>
    <p class="wf-sub">{{One-sentence: what this screen is for, who uses it, when in the flow.}}</p>

    <!-- legend: always include, verbatim -->
    <div class="wf-legend">
      <span class="k"><span class="wf-badge fn">Functional</span> wired to a live endpoint</span>
      <span class="k"><span class="wf-badge plan">Planned</span> speced, not built</span>
      <span class="k"><span class="wf-badge stub">Stub</span> fixtures / presenter-only</span>
      <span class="k">Zones: <span class="wf-chip local">Local</span><span class="wf-chip amd">AMD</span><span class="wf-chip external">External</span> · Data: <span class="wf-chip raw">Raw</span><span class="wf-chip sanitized">Sanitized</span></span>
    </div>

    <!-- ==== THE WIREFRAME ==== build the real screen here with wf- components ==== -->

    <!-- status ledger: auditable evidence for every label on the page -->
    <div class="wf-ledger">
      <h4>Functional status ledger — evidence</h4>
      <table>
        <tr><td><span class="wf-badge fn">Functional</span></td><td>Jobs list</td><td class="ev">GET /jobs</td><td>JobList.tsx calls api.listJobs(); endpoint present.</td></tr>
        <!-- one row per meaningful region/control; cite the endpoint or file evidence -->
      </table>
    </div>
  </div>
</section>
<!--WF:END-->
```

Wrap that section in the full HTML document: `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Nxcleus WF — {{name}}</title>
<style> …paste _kit.css… </style></head><body>` then the **top-bar shell** (below) then the section, then `</body></html>`.

Top-bar shell (put ABOVE the `<section>`, verbatim, with the current nav item marked `.active`):
```html
<header class="wf-topbar">
  <div class="row" style="gap:24px">
    <span class="brand"><span class="mark"></span>Nxcleus</span>
    <nav class="wf-nav">
      <a href="00-index.html">Home</a>
      <a class="{{active if Build}}" href="02-build-jobs.html">Build</a>
      <a class="{{active if Operations}}" href="12-operations.html">Operations</a>
      <a class="{{active if Gallery}}" href="15-gallery.html">Gallery</a>
      <a class="{{active if Sandbox}}" href="17-sandbox.html">Sandbox</a>
      <a class="{{active if Config}}" href="18-config.html">Config</a>
    </nav>
    <!-- Your task message gives you the exact nav block + which item is .active; it supersedes this example's filenames. -->

  </div>
  <div class="right">
    <span class="wf-pill-sov">Standard</span>
    <span class="wf-pill-live"><i></i> Live</span>
  </div>
</header>
```

---

## 6. Quality bar
- Premium, world-class, trustworthy — NOT AI slop. Organic layout, intentional whitespace, real
  type hierarchy, hairlines not boxes-in-boxes, one accent. Match the density of a real console.
- Show realistic content: real seat names (`trust`, `planner`, `certifier`, `conductor`, `coder`,
  `consolidator`, `oracle`, `inspector`), real endpoints, plausible KYC/AML onboarding data
  (the flagship demo domain), real zone/data-class chips where the boundary is relevant.
- Every input has a `<label>`, placeholder, and hint where useful. Every button is labeled.
- Do not leave a control unlabeled and do not leave its status unmarked.

Your task message names your SLUG, output path, screen, nav-active item, and the spec sections to read.
Return one line: the path you wrote + a one-sentence summary of what you marked FUNCTIONAL vs PLANNED.
