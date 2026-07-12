# Nxcleus — demo video · shoot script

**Runtime target: ~3:00** (safe band 2:45–3:15). Track 3 sets no length rule; keep it tight.
**Record against local dev** — `http://localhost:5173`. Prod (amd.nxcleus.tech) is live, but local has the seeded corpora + golden run.
Screen recording, full-screen Chrome, bookmarks bar hidden (⌘⇧B), 100% zoom, one clean voice track.
Speak slower than feels natural; numbers land harder than adjectives.

> **Golden run — locked** (insurer duplicate-claim, live `MODEL_MODE=auto`, all URLs in `presentation/golden-run.md`):
> build `job_01KXBWJB2Q4W05GYQP8Y94V4TV` · process `prc_01KXBWVWH90X32B01BKS2BZPQV` · run-map `/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV/map`.
> Result: **138/138 planted flagged** (needs_review 138, ok 0, error 0), `report.html` + `export.csv` both 200. Egress ledger **EXTERNAL 1 / AMD_HOSTED 13**, mock 0, total **$0.41**, wall **5m13s** (intake 55s · plan 43s · certify 152s · fan-out 46s · deliver 17s). Planner = `openrouter openai/gpt-5.6-sol` as **flagship primary** (not a fallback badge).
>
> ⚠️ **This run's non-planner seats served on Fireworks (AMD_HOSTED, demo-exception badge), NOT self-hosted MI300X.** Narration must not say "MI300X served this run" — say **"AMD-hosted"** for this run, and keep own-fleet MI300X as an architecture/scale claim.

---

## Pre-roll tab order (open, logged-in, fully loaded, in this order)

1. `http://localhost:5173/` — landing
2. `http://localhost:5173/sandbox` — company + prompt picker (Cascadia Mutual pre-selected)
3. `http://localhost:5173/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV` — the completed golden run, stages 0→7 green
4. `http://localhost:5173/build/job_01JKYCDEMO0000000000000001/map` — KYC build fixture map (fan-out beat) · then `http://localhost:5173/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV/map` — live golden detection map
5. `http://localhost:5173/traces` — egress ledger (boundary proof)
6. `http://localhost:5173/operations/prc_01KXBWVWH90X32B01BKS2BZPQV` — registry + economics

The build is pre-captured — you are **walking a finished run**, not waiting on one. (This golden run took 5m13s; you can't film it live in a 3-min video.) Optional live-batch variant is in REHEARSAL.md.

---

## Shot list + narration

### Scene 1 · The problem — Landing
`localhost:5173/` · **0:00–0:22 (22s)**
**Screen:** Land on the hero. Slow single scroll to the boundary diagram (LOCAL / EXTERNAL). Egress monitor reads **0 external calls**.
**Camera:** steady, no cursor jitter. Let the hero breathe for 2s before you speak.

> "Banks, insurers, hospitals, law firms — the companies with the most to automate are the ones forbidden to send their data to frontier AI. So the work stays manual, or a consultant rebuilds it for six figures. Nxcleus is a third option: describe a process in plain language, and get it running **inside your walls**."

---

### Scene 2 · Cross the boundary — Enter the platform → Sandbox
`localhost:5173/` → `localhost:5173/sandbox` · **0:22–0:42 (20s)**
**Screen:** Click **Enter the platform**. Editorial light landing gives way to the sealed-midnight interior — hold on that transition for a beat, it's the brand moment. Land on the sandbox. Click **Cascadia Mutual** (the insurer). Click the first suggested prompt so it fills the composer: *"Flag duplicate claims filed against the same policy for one incident — same incident date, amounts within 5%, different claim IDs."*
**Camera:** don't linger on the raw-data browser; narrate the seal instead.

> "Cross into the platform and you're inside the walls — this is where real data lives, and it never leaves. Here's a live corpus: an insurer with hundreds of thousands of claims. I'll ask it to find duplicate claims filed for the same incident."

---

### Scene 3 · The single external call — Build cockpit
`localhost:5173/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV` · **0:42–1:32 (50s)**
**Screen:** Open the completed golden run. Walk stages **top to bottom**. Pause on **Stage 0** (the sanitized brief — "masked N identifiers, sealed in LOCAL"), then **Stage 1** flagged as the single EXTERNAL call, then **Stage 2** certifier with its check list streaming green. The serving panel shows the **AMD-hosted** badge (this run served on Fireworks/AMD MI300X, not the local fleet) — fine to show, don't call it "our node".
**Camera:** scroll deliberately; each stage gets ~1s of stillness before you name it.

> "Stage zero strips every identifier and produces a sanitized brief. That brief is the **only** thing that ever leaves the building — it goes to one frontier planner, GPT-5.6, **exactly once**. Stage one, one call out."
>
> "The plan comes back, and a certifier model — running **inside** the boundary, on AMD — audits it against the full raw context the planner never saw, and amends it. On this run it ran seven independent checks and corrected the plan before anything was built. The small local model checks the big external one."

---

### Scene 4 · The fleet, mapped — Architecture map  ⭐ hero shot (two beats)
`localhost:5173/build/job_01JKYCDEMO0000000000000001/map` → `localhost:5173/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV/map` · **1:32–2:00 (28s)**

The map renders two shapes; show both so the fan-out beauty and the live run are each honest.

**Beat 1 · build-job fan-out (~14s).** Open the **KYC build fixture** map (a replay/fixture surface — deterministic, no backend, redraws mid-run on load). Node graph draws itself: Planner → Certifier → a **conductor fanning out to a wave of specialist coder nodes and fanning back in**, wave by wave, edges energizing. This is the dramatic multi-agent shape — a *build* job.
**Beat 2 · the live golden run (~14s).** Cut to the golden insurer map (**LIVE** badge). A detection job is a straight line, not a fan-out: **Intake·Boundary → Planner (alone in the dashed "sovereign boundary" band) → Certifier → the detection node ("scans the corpus & flags — 138 flagged") → Deliverable.** Click a node → its Claude-Code-style transcript (model + zone header).
**Camera:** let beat 1 redraw once, then cut cleanly to beat 2. Don't scrub within a beat.

> "Every run draws itself as a live graph. On a build job, a conductor fans the work across a fleet of specialist models, wave by wave, then converges it back to one result." *(cut to beat 2)* "On this live insurer run it's a straight line — only the planner crosses the boundary, that dashed band — then the process scans the whole corpus and flags all 138. Every node is a model call you can open and read, line by line, all on AMD."

---

### Scene 5 · The boundary, proven — Traces / egress ledger
`localhost:5173/traces` · **2:00–2:24 (24s)**
**Screen:** The egress ledger. Filter to the **planner** seat → the lone **EXTERNAL** row routing to `openai/gpt-5.6-sol`; click it to show the sanitized payload in the reader. Every other row badged **AMD_HOSTED** (this run: **EXTERNAL 1 / AMD_HOSTED 13**). Then flip the **Sovereign Mode** toggle.
**Camera:** hover the EXTERNAL row so the "sanitized" tag is legible.

> "Don't take the privacy claim on faith — audit it. Every model call is logged with its destination zone. EXTERNAL equals the planner, and nothing else. And if even one sanitized call is too many, Sovereign Mode rebinds the planner onto the local fleet — zero external calls, fully sealed."

---

### Scene 6 · The result + the economics — Registry
`localhost:5173/operations/prc_01KXBWVWH90X32B01BKS2BZPQV` · **2:24–2:50 (26s)**
**Screen:** The delivered process, ACTIVE in the registry. Show the run result — **138 candidates, all 138 flagged** (needs_review 138 / ok 0) — then the invoice card split AMD_HOSTED / EXTERNAL (**$0.41 total**), and **1 boundary crossing at build / 0 at run**.
**Camera:** rest on the 138/138 figure, then the invoice split.

> "The finished process lands in the operations registry and runs live batches. Against the insurer corpus it surfaces **138 duplicate-claim candidates** and flags every one for review — reasoning over the records, not string-matching. The build made **exactly one call out of the building**; every batch it runs after is fully local — **zero frontier calls, forever.** That's the consultant turned into a line item."

> **This golden run is a clean 138/138 sweep** (needs_review 138, ok 0) — say "138 candidates, every one flagged". Do **not** say "136 of 138" (backend bench, not this run). Fine to let the **$0.41** total show; the durable claim is structural — **1 external call at build, 0 at run.** (If you fall back to the prod ids in the reference block, their flagged counts differ — 110 / 59 — so read the card.)

---

### Scene 7 · AMD + close
`localhost:5173/build/job_01KXBWJB2Q4W05GYQP8Y94V4TV` (telemetry panel) → `localhost:5173/` · **2:50–3:05 (15s)**
**Screen:** Show the **AMD-hosted** serving badge on the serving/traces panel (the AMD_HOSTED rows), then cut back to the landing hero.
**Camera:** end on the hero, still.

> "Every model call inside the walls runs on AMD — this run on **AMD-hosted MI300X** through Fireworks, and at scale on our own MI300X fleet, vLLM on ROCm. AMD silicon isn't a footnote here; it **is** the inside of the walls. Nxcleus. Describe a process. Get it running inside your walls."

---

## Cut-for-time order (if over 3:15)
1. Trim Scene 1 to the first two sentences.
2. Shorten the Scene 3 certifier line to one sentence.
3. **Never cut** Scene 4 (archmap — the differentiator), Scene 5 (egress ledger — the product thesis), or the AMD line in Scene 7 (the disqualification gate).

## Accuracy guardrails (do not drift off these on camera)
- Say **"single / one external call"** — verified, and provable in /traces.
- **Numbers must match the on-screen card.** The golden run is a **clean 138/138 sweep** (needs_review 138, ok 0) — say "138 candidates, every one flagged". **Do not say "136 of 138"** (backend bench, not this run). The **$0.41** total is fine to show; don't invent a per-applicant cent figure — say "one call at build, zero at run".
- **AMD serving (hard guardrail).** This run's non-planner seats served on **Fireworks (AMD_HOSTED)**, not the self-hosted fleet — say **"AMD-hosted MI300X"** for this run and keep own-fleet MI300X as an architecture/scale claim. Don't point at a live self-hosted node and say it served this job.
- The adversarial layer that runs on this insurer path is the **certifier (7 checks)** and the parallel per-candidate judges — **not** the oracle/inspector QA swarm (that path is for custom code builds, and does not fire on a sandbox corpus run). Narrate "certifier audits and amends" and "fleet judges each candidate" — don't claim an oracle attacked this run.
- Local corpora must be seeded before recording (see REHEARSAL.md) or the flagged count reads 0 — the one blocker that killed a prior rehearsal.

## Real live runs on record (reference / fallback ids, from the verification agent)
These are real completed insurer duplicate-claim runs on the **live/prod** backend (frontier_calls=0 at run). Use only if recording against the live URL (prod is live); otherwise the local run-capture agent's ids are canonical.
- **insurer-4** — build `job_01KX88SJ2YA8600BCKCS3901CS` · process `prc_01KX89XQMF07RBGZRXNBMEV5PP` · run `run_01KX89A9XPXY8T5GZDNFR6F1SN` · 138 units, **110 needs-review** / 28 ok · run ~10m, run $1.51, build capex $2.15.
- **insurer-3** — build `job_01KX87MHRGTPH0XYEMQHXSYB8D` · process `prc_01KX88KWRXMCTWWHGZ688GCP7K` · run `run_01KX8858KYWH8ZRRX5V2MQN4MZ` · 138 units, **59 needs-review** / 79 ok · run ~7m, run $1.11, build capex $1.75.
