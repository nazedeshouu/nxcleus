# Nxcleus Backend AI & Routing — Visualization Suite Brief (fresh unified set)

You are one of a fleet building a **fresh, unified** visual explanation of Nxcleus's backend AI
and routing logic. Goal: a team member (or judge) who has never seen the code understands, in one
sitting, **how a request flows through seats, backends, zones, the data boundary, the 0–7 pipeline,
and the meter**. One consistent narrative and visual language across all pages. Output to
`docs/viz-v2/`. These REPLACE the older `docs/viz/` set — build clearer, tighter, better.

Unlike the wireframes (which mock UI screens), these are **explainer / diagram** pages: flow
diagrams, decision trees, layered maps, worked examples. Build diagrams with semantic HTML + CSS
(and inline SVG for connectors/arrows where cleaner). Everything self-contained — no external assets.

## Shared visual language (consistency is the point)
- Inline the ENTIRE `docs/wireframes/_kit.css` verbatim in a `<style>` block (sealed-midnight palette,
  chips, panels). Add page-specific diagram CSS scoped under `#viz-<slug>`.
- Seats are always mono chips: `<span class="wf-chip seat">planner</span>`. The 8 seats:
  `trust · planner · certifier · conductor · coder · consolidator · oracle · inspector`.
- Zones always use zone chips + colors: `local` (MI300X) · `amd` (Fireworks, fallback only) ·
  `external` (Anthropic) · `custom` (BYOK). Data class: `raw` (never leaves LOCAL) · `sanitized`.
- One accent, hairlines, generous whitespace. Premium, legible, not slop. Label every node and edge.
- Top of each page: a one-paragraph plain-language "what you're looking at." Between diagrams, short
  connective prose. Cite the spec section each fact comes from (e.g. "spec 02 §7.4").
- Include at least one **worked example** per page (trace a concrete KYC/AML onboarding request
  through the mechanism), and call out the WHY, not just the what — the team refines pipelines from this.

## Ground-truth sources (read before drawing)
- `docs/specs/00-INDEX.md` (glossary + locked decisions D1–D14), `01` (architecture/zones/topology),
  `02` (seats & routing, capability flags, BYOK), `03` (pipeline stages 0–7, waves, conductor, consult gate),
  `05` (data model / event log), `07` (event-sourced orchestrator, fleet, budget guards),
  `08` (QA/oracle/inspectors), `10` (metering/quote/economics), `11` (model catalog + evidence).
- Backend code for accuracy: `backend/app/models/router.py`, `infra/seats.yaml`, `infra/models.yaml`,
  `infra/fleet.yaml`, `infra/rates.yaml`, orchestrator/engine under `backend/app/`. Verify names/flags
  against real files; if a spec and the code disagree, show the code's reality and note the divergence.

## The five pages (one agent each — stay in your lane, assume the others cover theirs)

1. `00-system-overview.html` — **The whole system on one page.** The map everything else zooms into.
   A request enters → stage pipeline spine (0–7) → for each stage, which seat runs on which zone,
   where the data boundary sits, where the meter ticks. Show the three-host topology (always-on VM
   control plane + elastic MI300X fleet + Fireworks fallback + external planner) and the core claim:
   "frontier intelligence without your data leaving your walls." This is the centerpiece — make it
   the clearest thing in the repo. Link to the other four.

2. `01-seats-and-routing.html` — **Seats → backends, and capability-aware routing.** The seat
   abstraction (code never names models), seat→backend binding table, the two routing layers: seat
   binding (02 §1–3) and capability-aware selection inside pooled seats (02 §7, D12) — task_flags →
   deterministic argmax over `models.yaml` capability flags. BYOK connections + user-configurable
   seat rebinding (02 §8, D13). Worked example: how a refactor step vs an SQL step vs a prose step
   route to different pooled members.

3. `02-data-boundary.html` — **The boundary is code, not policy.** RAW vs SANITIZED, the four zones,
   what may cross where (only SANITIZED → EXTERNAL). The sanitization gate at stage 0, the consult
   sanitization gate (03 §4.2), certifier/conductor RAW access (D9), RedactionPolicy intake (D11).
   Sovereign Mode = zero non-local calls (D7) — show the diff vs Standard. Worked example: trace what
   the planner actually sees (sanitized brief) vs what stays inside (raw plan, code, DB schemas).

4. `03-pipeline-orchestrator.html` — **The event-sourced engine.** Stage state machine 0–7, the
   custom asyncio engine (D3), topological **waves** in stage 4, the **conductor** reviewing wave
   outputs and issuing bounded amendments to not-yet-built regions (D8), amendments vs consults,
   worker pool + fleet manager + budget guards (07), replay/resumability from the event log (05).
   Worked example: a two-wave build where the conductor amends wave 2 before green-flagging.

5. `04-economics-metering.html` — **Follow the money & the tokens.** Meter events on every dispatch
   (10 §1), GPU-second attribution (honest approximation, 10 §2), rates config, the deterministic
   quote engine at stage 3, invoice at stage 7 + per refine, the money-slide summary
   (`GET /economics/summary`), budget guards/enforcement points. Worked example: a quote for a KYC
   onboarding process and the resulting invoice line items.

## Output
Each page: full self-contained HTML doc, `<section id="viz-<slug>">`, kit CSS inlined, a slim top
nav linking the five pages (`00-system-overview.html` … `04-economics-metering.html`) with the
current one marked active. Return one line: path written + one-sentence summary of what it shows.
Accuracy over polish where they conflict, but aim for both — this is judge- and team-facing.
