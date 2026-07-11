# Demo video — shot list & narration (~3:00)

Record: QuickTime → New Screen Recording, full-screen Chrome, hide bookmarks bar (⌘⇧B),
100% zoom, mic on. One take is fine — judges value clarity over polish. Speak slower
than feels natural.

Prep (before recording): open these tabs in order, all logged-in/loaded:
1. https://nxcleus.tech (landing)
2. https://nxcleus.tech/build/job_01KX840Q9KSG0FEYG8P61PB3SN (hero run cockpit)
3. https://nxcleus.tech/operations
4. https://nxcleus.tech/operations/prc_01KX8592AFXKCV0Y7E7F4Z6BTN (registered KYC process)
5. https://nxcleus.tech/traces (egress/routing view — the boundary-proof beat)

---

**0:00–0:20 · Landing (tab 1)**
Slow scroll through the hero.
> "Enterprises can't send customer data to frontier AI. So their internal processes stay
> manual — or get automated by consultants for a hundred thousand dollars a run. This is
> Nxcleus: describe an internal process in plain language, and get it running inside
> your walls."

**0:20–1:20 · Build cockpit (tab 2) — the hero run**
Walk the completed stages top to bottom. Pause on stage 0 (sanitized brief) and the
certifier amendments.
> "Here's a real run: KYC onboarding — screen new customers against OFAC and EU
> sanctions lists. Stage zero strips every piece of PII and produces a sanitized brief.
> That brief is the ONLY thing that ever leaves the building — it goes to GPT-5.6, our
> frontier planner, exactly once."
> "The plan comes back — and a certifier model running inside the boundary, on AMD,
> audits and amends it against the full raw context the planner never saw. The small
> model corrects the big one before anything gets built."
> "Then the local fleet builds the process, and an adversarial QA swarm — oracle and
> inspectors — attacks it before it's allowed to register."

**1:20–1:50 · Operations registry + process detail (tabs 3→4)**
Click into the process; show invoice/economics and the batch-run results.
> "The finished process lands in the operations registry and runs live batches. In our
> insurer demo it flagged 136 of 138 planted compliance patterns. Cost to plan, certify,
> build, QA and register this process: fifty-four cents of compute, with exactly one
> frontier call. And every run after that? Nine-tenths of a cent per applicant — zero
> frontier calls, forever. That's the consultant replaced by a line item."

**1:50–2:20 · The boundary proof (tab 5 — /traces)**
Show the egress/routing view: rows are LOCAL (MI300X) and AMD_HOSTED (Fireworks, badged);
EXTERNAL rows are planner-only. Then flip the Sovereign toggle.
> "Don't take the privacy claim on faith — audit it. The egress ledger records every
> model call: EXTERNAL equals the planner, and nothing else. And if even one sanitized
> call is too many: Sovereign Mode. Zero external calls. Fully air-gapped."

**2:20–2:45 · AMD fleet**
Fleet node A panel (in the build cockpit / traces): live MI300X telemetry — ~181GB VRAM
in use, utilization, power — plus the Fireworks fallback badge.
> "Everything inside the boundary runs on AMD Instinct MI300X — vLLM on ROCm, on our own
> fleet — with Fireworks AI, also AMD-hosted, as the availability fallback. AMD silicon
> isn't a footnote here; it IS the inside of the walls."

**2:45–3:00 · Close (back to tab 1)**
> "Nxcleus. Describe an internal process. Get it running inside your walls. Live now at
> nxcleus dot tech."

---

Cut-for-time order if over 3:15: trim 0:20 beat narration first, then drop the sandbox
mention entirely (it's not in the shot list anyway). Never cut the egress-ledger or AMD
beats — one is the product, the other is the disqualification gate.
