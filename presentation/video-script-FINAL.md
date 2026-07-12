# Nxcleus — demo video · FINAL shoot script

**Runtime ≤ 2:45 · one pass · every pixel is a REAL job from tonight (no fixtures, no replays).**
Numbers-first narration, short lines, speak slow. Record full-screen Chrome, bookmarks hidden, 100% zoom.

Real jobs used (all live on localhost tonight):
- **LIVE build** started ON CAMERA at the top — read `{{LIVE_JOB_ID}}` from the `/build/{jobId}` URL at shoot time → approve its quote gate on camera, then `/build/{{LIVE_JOB_ID}}/map` fans out the real module DAG (money shot).
- **Fresh build** `job_01KXC2S4FNG39Z8PQNKKDZJM0A` (0→7 done, 1 frontier call, **$0.538**, goal fulfilled) → process `prc_01KXC39DJGDNCEQ098YGKCC293`, run flagged **138/138**, new judge-readable report.
- **Tested v1 process** `prc_01KXBWVWH90X32B01BKS2BZPQV` — for the LIVE on-camera batch.
- **Fallback if the KYC build stalls** on the degraded fleet: launch the **insurer sandbox build** instead — faster (~5–6 min), same single external call, real unit fan-out on the map.

---

## Shot list + narration

### Scene 0 · Launch a real build — LIVE ON CAMERA  ⭐ (do this the instant you hit record)
`localhost:5173/build` · **0:00–0:12 (12s)**
**Screen / actions:** the `/build` composer IS the new-build form. Paste the KYC prompt (below) into the textarea (optional title), click **"Start the build"** (lightning button) → lands on `/build/{jobId}` — **read that jobId out of the URL; it's `{{LIVE_JOB_ID}}` for the map tab.** Intake auto-confirms (no click). The build runs off-screen (planning → certify → quote gate) through Scenes 1–2.
> "Before I say anything — let's have it build a KYC onboarding process, live." *(click Start)*

**KYC prompt — paste verbatim:**
> We onboard retail banking customers and must run KYC/AML screening end to end. For each applicant: OCR their uploaded ID document, screen the name and date of birth against OFAC and EU consolidated sanctions lists plus PEP and adverse-media sources, compute a weighted risk score, and return an approve / review / reject decision with the evidence behind it. Produce an auditable case file per applicant — the matched lists, the score breakdown, and the decision rationale — that a compliance reviewer can drill into, plus a summary of counts by decision. Applicant: Maria Alvarez, DOB 1988-04-12, ID document DL-338291045, email m.alvarez@northgate.co. Governance: never let raw applicant names, dates of birth, or document numbers leave the local boundary — see our data-handling policy; the case file a reviewer sees must reference redacted/tokenized identifiers only.

### Scene 1 · Landing — the problem
`localhost:5173/` · **0:12–0:27 (15s)**
**Screen:** hero, one slow scroll through the boundary section. Egress monitor reads 0 external calls.
> "Banks, insurers, hospitals — the companies with the most to automate can't send data to frontier AI. Nxcleus builds the process and runs it **inside their walls**."

### Scene 2 · The real build — single external call
`localhost:5173/build/job_01KXC2S4FNG39Z8PQNKKDZJM0A` · **0:27–1:02 (35s)**
**Screen:** the completed build. Walk it top-down — Stage 0 sanitized brief ("masked N identifiers"), Stage 1 flagged as the one EXTERNAL call, Stage 2 certifier checks streaming green. Build stages 4/5 render dimmed (skipped on a detection run) — that's correct, don't dwell.
> "A real build from tonight. Stage zero seals every identifier into a sanitized brief. That brief is the **only** thing that leaves the building — one frontier call, and only one. The plan comes back and a certifier, running inside the boundary on AMD, audits and amends it against the raw context the planner never saw. Whole build: **fifty-four cents**, goal fulfilled."

### Scene 3 · Approve the quote, then the fan-out draws itself — LIVE  ⭐ money shot
`localhost:5173/build/{{LIVE_JOB_ID}}` → `/build/{{LIVE_JOB_ID}}/map` · **1:02–1:24 (22s)**
**Screen / actions:** the build has planned and certified and **PARKED at its quote gate** — panel "Quote — your approval gate" shows an estimated range and "nothing is spent until you approve". **Click "Approve quote" on camera** (the human-in-the-loop beat — ignore the "Abort" button beside it). Then open `/build/{{LIVE_JOB_ID}}/map`: the **conductor fans out the module DAG in real topological waves — OCR → sanctions/PEP → risk score → decision** — planner alone in the dashed sovereign band as the one EXTERNAL hop. Nodes light up live.
**Camera:** the quote gate lands ~4–6 min in and the whole build is ~7–10 min on tonight's degraded fleet — **cut the wait in the edit**; never refresh the map, let it animate as it advances.
> "It quotes the build before spending a token — I approve it, on camera. Then it builds itself: the planner crossed the boundary once, and now a fleet of specialist models fans out in parallel — OCR, sanctions screening, risk scoring — live, on AMD MI300X. Nothing pre-rendered."

### Scene 4 · The boundary, proven
`localhost:5173/traces?scope=job:job_01KXC2S4FNG39Z8PQNKKDZJM0A&seat=planner` · **1:24–1:46 (22s)**
**Screen:** the planner's EXTERNAL call to `gpt-5.6-sol` — open it: REASONING blocks + the sanitization receipt. Every other row is AMD_HOSTED.
> "Don't trust the privacy claim — audit it. Every call is logged with its zone. **Exactly one** is EXTERNAL: the planner, carrying only the sanitized brief. Everything else is AMD-hosted, inside the walls."

### Scene 5 · Live, unscripted — run it on camera
`localhost:5173/operations/prc_01KXBWVWH90X32B01BKS2BZPQV` (signed in) · **1:46–2:32 (46s)**
**Screen / actions:**
1. Click **"Run a batch"** (needs sign-in). It runs ~75s — **flip to the traces tab while it runs (no dead air), cut the wait in the edit.**
2. **Reload the process page once**, then scroll to the runs section. New run row: **138/138**, **$0.025**, **0 frontier calls**.
3. Click the run row → **"Compare with planted patterns"** → panel reads **137 of 137 planted caught · 1 flagged-not-planted · 0 missed**.
> "Now live, on a tested process. I run a batch — no edits, real data." *(over traces while it runs)* "It comes back in about a minute: **138 flagged**, **two and a half cents**, **zero frontier calls**." *(compare panel)* "Against what the sandbox planted: **every planted pattern caught, zero missed** — one borderline case flagged on top, which is exactly what a review queue should do."
> ⚠️ During the compare panel, say "137 of 137 planted" — **never** "138 of 138 planted".

### Scene 6 · Close
back to `localhost:5173/` · **2:32–2:44 (12s)**
> "Built and verified in one pass, one call out of the building, every run after it fully local — on AMD. Nxcleus. Describe a process, get it running inside your walls."

*(Optional +5s only if under 2:30: `localhost:5173/traces?scope=job:job_01KXBZR3HPSQAV0K671XE9SBX4&seat=trust` — v2 `fleet.local` LOCAL rows: "with our own MI300X attached, even boundary seats serve locally — a live run doing exactly that.")*

---

## Guardrails (do not drift)
- "**Exactly one / one external call**" — provable in Scene 4.
- Compare panel: "**137 of 137 planted caught, 0 missed, 1 borderline**". Never "138 of 138 planted". The run *row* 138/138 is fine (that's flagged units).
- The adversarial audit here is the **certifier**, not an oracle/QA swarm — say "certifier audits and amends".
- These runs served **AMD-hosted** (Fireworks/AMD MI300X). Say "AMD-hosted"; own-fleet MI300X is the architecture/scale claim (and the optional Scene 5b v2 rows).

---

## PRE-FLIGHT (read only this)
1. Sign in at `localhost:5173`, window 1280×720, 100% zoom, bookmarks hidden.
2. **First on camera:** start the live KYC build from `/build` (Scene 0), then open its `/build/{{LIVE_JOB_ID}}/map` tab and **leave it — never refresh** (it's the Scene 3 cutback).
3. Other tabs in order: `/` · `/build/job_01KXC2S4FNG39Z8PQNKKDZJM0A` · `/traces?scope=job:job_01KXC2S4FNG39Z8PQNKKDZJM0A&seat=planner` · `/operations/prc_01KXBWVWH90X32B01BKS2BZPQV`.
4. On the operations tab confirm **"Run a batch"** is visible (= signed in); batch ~75s + **reload after**.
5. Record one pass; cut only wait time in the edit.
