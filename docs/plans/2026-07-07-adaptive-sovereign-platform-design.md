# Adaptive Sovereign Process Platform — Consolidated Design v2

**Status:** locked after reframe brainstorm, 2026-07-07. **Supersedes** [`2026-07-07-enterprise-software-factory-design.md`](2026-07-07-enterprise-software-factory-design.md) (v1); carries its architecture forward with the framing, lifecycle, and scope changes recorded here.
**Track:** AMD Hackathon ACT II, Track 3 (Unicorn / Open Innovation). Deadline **Jul 11, 2026, 21:00 KT (UTC+5)**.
**Team:** duo, near full-time.
**Working title:** TBD — "factory" is now wrong for two reasons: the Factory.ai brand collision, and the product is a lifecycle platform, not a factory.

## v2.1 addendum — spec session, 2026-07-08 (authoritative deltas)

Five decisions from the 2026-07-08 technical-spec session revise this document. Where the body below conflicts, **the list here and the specs win** (details: [`../specs/00-INDEX.md`](../specs/00-INDEX.md) D7–D11).

1. **Full-local except the planner (D7).** Fireworks is no longer a designed-in seat home — consolidation (stage 5) and the Sovereign-Mode planner both move to the self-hosted MI300X fleet (node B GLM). Fireworks remains only as the badged availability fallback that keeps the live URL up between fleet sessions. The product claim sharpens: *the sanitized stage-1 planning conversation is the only thing that ever leaves customer-controlled hardware; Sovereign Mode removes even that.* §3's stage table is superseded accordingly (stage 5 runs LOCAL; stage 1 sovereign runs LOCAL).
2. **Confidentiality-policy intake (D11).** Stage 0 gains a first-class input: the customer's terms-of-use / "never leak" rules — uploaded as a document, typed, or dictated (local Whisper; the recording never leaves the box). `trust` distills it into a structured RedactionPolicy that governs sanitization alongside the always-on PII baseline; the sensitivity report cites the customer's own clauses. Stage 0 also formally ingests codebases (local code map, sanitized rendition for the planner) and database schemas (structure only, never rows).
3. **Certifier sees everything (D9).** Stage 2 receives the full raw context — original prompt verbatim, files, code map, real schemas — and **rehydrates** the plan to production specificity after certification. Legal because everything downstream of stage 1 is now local (delta 1); consults going back to the planner pass a sanitization gate. This is the pass the frontier could never do, run by the model that can see what the frontier couldn't.
4. **Goal anchor (D10).** Stage 2 pins a plain-language **goal statement** derived from the original (raw) ask. The conductor checks drift against it every wave; stage 6 ends with a **goal-fulfillment check** — the deliverable is judged against the original ask, not the drifted plan; the verdict ships in the package.
5. **Conductor wave review (D8).** Stage 4 executes the DAG in topological waves; between waves a local GLM `conductor` seat reviews outputs against plan + goal and may issue bounded, hash-chained amendments to not-yet-built regions (rework orders for built ones) before green-flagging the next wave. The engine stays deterministic (D3 stands): *the certified plan is the orchestrator's mind, the engine its hands, the conductor its eyes.*
6. **Capability-aware routing (D12, added 2026-07-09).** Models aren't interchangeable, so a second routing layer sits under the seat abstraction: every servable model carries **capability flags** in a registry (`infra/models.yaml` + catalog spec 11 — who runs what, where, when); the planner tags every module/step with `task_flags`; the pool scheduler deterministically routes each task to the best-flagged member (refactors → the editor model, SQL → the data model, prose/extraction → warm Gemma seats). Unflagged tasks fall back to round-robin; the BoM panel shows each routing decision and why.
7. **BYOK connections + configurable seats (D13, added 2026-07-09).** Customers add their own API keys in the UI, point each at an OpenAI-compatible endpoint, register one or more models under it, and tag each with the same capability flags — custom models join the routing registry as first-class citizens. Every seat's model is user-configurable (Fable 5 is the default planner, not a hardcode). The boundary is enforced per connection: SANITIZED ceiling by default; RAW and Sovereign eligibility only via explicit boundary attestation ("this endpoint is inside my walls") — which is also how the "runs on your metal or your trusted provider" deployment story is expressed in config.
8. **Model picks locked (D14, 2026-07-09, evidence in spec 11).** Local **GLM-4.6** is the sovereign brain (certifier/conductor/consolidator/sovereign planner) with **hosted GLM-5.2 as its fallback binding**; capability-diverse coder pool (Qwen3-Coder-Next / Qwen3.6-27B / Devstral-Small-2); Gemma 4 keeps trust + oracle on merit; inspectors run Qwen3.6-35B-A3B. Fleet reality: demo profiles run on a single 8× MI300X droplet (1×/8× are the only shapes sold).

## 1. Concept & positioning

**One-liner:** *"Describe an internal process. Get it running inside your walls — built, verified, and yours to run forever."*

A platform for **regulated enterprises** that turns a plain-language description of an internal process into a **running, verified, sovereign process automation**. The unit of sale is not an app or code — it is the **process, handled**: KYC done, reports filed, claims adjudicated, document bases processed. Customer data never leaves customer-controlled AMD hardware; external frontier models only ever see sanitized specifications, and **Sovereign Mode** removes external calls entirely.

**The lifecycle replaces the pipeline as the headline.** Three phases:

1. **Build** (once per process) — frontier-planned, locally completed and certified, fleet-coded, adversarially QA'd (§4).
2. **Operate** (forever) — the certified process runs on new data on local hardware, metered per run, with zero frontier calls (§5).
3. **Refine** (on demand) — a change request re-opens planning under a triage model; the process re-certifies as a new version (§6).

The workflow is a **versioned asset**. Per task, the customer chooses: run it on new data, or re-instantiate the recipe (same certified design, new environment/connectors — e.g. per-subsidiary rollout).

**The economic wedge:** frontier intelligence is a **capital expense, not a marginal cost**. It is paid once, at build time, on sanitized specs only. Every subsequent run is local and cheap. Chat-based and cloud-agent competitors pay frontier tokens *and* surrender data on every run. This is the deck's money slide.

**What changed from v1:** nothing structural was lost. "Software factory" becomes internal vocabulary; the code/repo is the audit-grade evidence behind the delivered process, not the deliverable itself.

**Why a single frontier chat cannot substitute** (unchanged from v1): jobs are too large for one context, the data is private and cannot leave the boundary, and delivery requires a build–test–fix loop validated against real systems and connectors.

## 2. Adaptive delivery modes

The planner designs the **work topology for the task**, not just software. At intake the job is classified and the planner (frontier; local in Sovereign Mode) selects and designs one of three modes:

- **Build mode** — the v1 factory: the topology is a software plan (modules, typed interfaces, tests) → built, certified, deployed, registered.
- **Process mode** — no app needs to exist. The topology is a *processing plan over a corpus* — documents, records, people, or a large codebase. The planner defines:
  - the **unit of work** (one contract, one person's records, one source file);
  - the **extraction/judgment schema per unit** — the data points the customer's queries require;
  - the **model allocation** per step (which local seat handles OCR vs. extraction vs. judgment vs. aggregation).
  The elastic MI300X fleet fans out — units across workers — and results aggregate into the deliverable: a dataset, dashboard, or report.
- **Semi-automated mode** — either topology with human-review steps designed in (queues, approvals): *AI does the pass, people adjudicate the flags.*

**The lifecycle is mode-agnostic.** A processing topology is also a saved, versioned, re-runnable workflow: feed it next month's corpus, refine the schema at the planning step, re-certify.

**Model bill-of-materials (BoM):** every plan includes the model seats and fleet size the task needs (e.g. "Gemma OCR seat ×N, GLM analyst, oracle sampling at 5%"). The orchestrator provisions the fleet from the BoM — elastic GPU allocation **justified by the plan itself**. This is the "full-on adaptive system" claim made concrete, and it upgrades the AMD story from decorative to load-bearing.

Note: a pure process-mode job skips code generation entirely (stages 4–5) — the cheapest possible live demonstration of the platform, and the most relatable ("here are 10,000 contracts; six fields and the anomalies by morning").

## 3. Build phase — pipeline architecture

| # | Stage | Runs on | Model class |
|---|---|---|---|
| 0 | Intake, mode classification & data boundary | Self-hosted MI300X (vLLM/ROCm) | Local trust model (currently Gemma 4; seat is model-agnostic) |
| 1 | Planning (topology + model BoM) | External API, or Fireworks in Sovereign Mode | Frontier (Claude Fable-class default; open frontier in Sovereign Mode) |
| 2 | Plan completion & certification | Self-hosted MI300X | Strong local analyst (GLM 5.2-class) |
| 3 | Quote | — (deterministic + planner output) | — |
| 4 | Parallel code generation *(build mode only)* | Elastic 1–5× MI300X (vLLM/ROCm) | Multiple open coder models (Qwen-Coder/DeepSeek-class; IDs TBD) |
| 5 | Consolidation *(build mode only)* | Fireworks (AMD-hosted) | Large open model |
| 4′/5′ | Corpus fan-out & aggregation *(process mode)* | Elastic 1–5× MI300X | Local seats per the plan's model BoM |
| 6 | Adversarial QA | Self-hosted MI300X + deployed process | Inspector agents + Numeric Oracle |
| 7 | Delivery → operations registry | Platform infra | — |

### Stage 0 — Intake, mode classification & data boundary
- Clarification dialogue with the customer; produces a structured spec + acceptance criteria + **delivery-mode classification** (build / process / semi-automated, surfaced as an in-app choice with a recommended default).
- PII masking and schema abstraction: raw records in, sanitized abstractions out. The **only stage that touches raw customer data**.
- Document OCR/extraction for document-driven jobs happens here, locally.

### Stage 1 — Planning (dual, with Sovereign Mode)
- Default planner: Claude Fable-class external model (permitted by track rules; sees only sanitized specs — never raw data).
- **Sovereign Mode:** toggle swaps the planner for a Fireworks-hosted open frontier model — entire pipeline on AMD-hosted infrastructure, zero external calls. Product feature and demo insurance.
- Output: work topology for the selected mode (module decomposition + typed interfaces + task DAG, or corpus topology + unit schema), data schemas, algorithm pseudocode, **model BoM**, initial estimate.

### Stage 2 — Plan completion & certification (revised from v1's "verification loop")
GLM runs the same structured checks as v1 (interface compatibility, data-model completeness, error-handling coverage, consistency of auth/state patterns) — but findings are **triaged into two buckets**:

- **Local amendments** — exact values, underspecified fields, ambiguous interface details, missing error cases with obvious handling. GLM patches these **directly into the plan**. Each patch is logged as a signed amendment (e.g. *"§3.2 payout rounding unspecified → amended: banker's rounding, per spec §1.4"*).
- **Frontier consults** — wrong decomposition, missing module, flawed algorithm; anything GLM judges structural or hard. Sanitized findings go back to the planner for a **constrained re-plan** of the affected region only. Max 2–3 iterations.

Output: a **certified plan** = frontier draft + amendment log + consult history + integration test specs. The amendment log renders in the UI — the local model visibly *finishes* the frontier's work inside the boundary.

**Guardrail:** GLM's amendments are themselves covered by the integration tests it emits — a bad local patch is caught by the same QA gate as bad code.

**Authority story in one line:** *frontier authors, local model finishes and certifies, frontier is on-call for the hard parts.*

### Stage 3 — Quote
- Itemized upfront estimate: planning, projected token usage by tier, projected GPU time — per the model BoM.
- Delivery reconciles against **metered actuals**. Quote is a range; the invoice is exact.

### Stage 4 — Parallel code generation (build mode)
- Elastic fleet of 1–5× MI300X droplets (192 GB HBM each) running vLLM on ROCm, hosting multiple open coder models concurrently.
- Workers build modules in parallel against the certified typed interfaces and test specs. Fleet size follows the BoM; per-GPU usage feeds the invoice.

### Stage 5 — Consolidation (build mode)
- A larger open model (Fireworks, AMD-hosted) merges modules into a coherent codebase.
- Gate: stage-2 integration test specs must pass. Objective signal, not review-by-vibes.

### Stages 4′/5′ — Corpus fan-out & aggregation (process mode)
- The fleet fans out over the corpus, one unit of work per worker slot, applying the plan's per-unit schema with the allocated model seats.
- Aggregation assembles unit results into the deliverable (dataset/dashboard/report). The oracle samples unit outputs as the QA gate.

### Stage 6 — Adversarial QA
- Inspector agents probe the **deployed** process: API calls, auth/tenant-isolation probes, edge-case walks — against acceptance criteria, connectors, and masked/synthetic data.
- **Numeric Oracle** (§7.1): independent computation of expected outputs for quantitative business rules; assert `process output == oracle output`.
- Defects are filed as structured tickets routed back to the fleet. Loop until green; irreducible disagreements are **flagged for human review**, never auto-resolved.

### Stage 7 — Delivery → operations registry
- The process enters the **operations registry** (§5) rather than ending at "here's your URL."
- Package: live process + repo + generated documentation + QA report + final metered invoice.

## 4. Operate phase — runtime & registry

**Operations registry:** the customer's catalog of running automations. Each entry is a **process package**:

- Certified plan (frontier draft + amendments + consult history)
- Built codebase + deployment config (build mode) or topology definition (process mode)
- Integration test specs + Numeric Oracle test vectors
- Connector bindings (which internal systems it reads/writes)
- Run history + metering ledger + version history

**Running a process:** feed it work — a batch (this quarter's filing, 500 claims, 10,000 contracts) or a stream (today's KYC applications). Execution is entirely local: deterministic work in the built code; judgment-shaped steps (OCR, extraction, risk-narrative reads) on local model seats. **Zero frontier calls per run.** The meter records GPU-seconds and local tokens per run — the per-run cost line trends flat and small, making "yours to run forever" visible.

**Continuous assurance (the honest "runs continuously"):** a thin slice of QA stays alive in operation — the oracle spot-checks a sample of live outputs (every Nth payout recalculated independently); inspector agents run periodic probes. Discrepancies never auto-fix: they file **warranty tickets** into the process's queue, which feeds the Refine phase. Language rule for deck and demo: *operating with a warranty*, not unattended magic.

**Re-instantiation:** from any package, "instantiate copy" re-runs the build pipeline from the certified plan — new connectors, new environment, same verified design, **no frontier planning cost**.

**Hackathon scope:** the registry + run view stays modest — a table of processes with versions, run history, per-run cost, warranty tickets, and `run batch` / `instantiate copy` / `request refinement` actions. KYC and Reg-Report demos exercise it naturally.

## 5. Refine phase & versioning

**Entry points:** a customer change request ("add adverse-media checks in Spanish"), a warranty ticket from operation, or a schema change in a process-mode job ("we now also need clause expiry dates").

**Triage first, frontier maybe:** GLM assesses the delta against the certified plan.
- Small/mechanical (new field, threshold change, added schema data point) → GLM amends locally; affected modules or topology steps rebuild; re-certify.
- Structural (new subsystem, changed decomposition, new algorithm) → **scoped frontier consult**: the planner sees only the sanitized certified plan + the delta request — never accumulated data — and re-plans only the affected region of the DAG.

**Version semantics:** every refinement produces v(n+1) of the process package with a human-readable diff: what changed in the plan, which modules rebuilt, which tests were added, what re-certification found. **Old versions stay runnable** (regulated customers need "run Q3 filing under the rules as of Q3").

**Cost:** refinement is quoted as a mini-build — mostly local GPU time; frontier tokens itemized only if a consult fires. The invoice shows why a refinement cost ~2% of the original build.

**Demo:** one rehearsed refinement beat in the KYC demo — change request arrives live, GLM triages on screen, v2 deploys, the diff view shows the amendment. Likely the single most "this is a real product" moment available to us. Pre-recorded fallback required.

## 6. Gemma: justified roles only

**Honest position (unchanged from v1):** the trust layer (intake, PII masking, OCR, doc generation) is a *local-model* requirement, not a *Gemma* requirement — Qwen/Llama-class local models could fill it equally well. Gemma currently occupies the seat; we do not present this alone as a "best use of Gemma" claim.

Two roles are Gemma-specific, based on the team's benchmark deep-dive (figures must be **re-validated on our workload during build week**):

### 6.1 Numeric Oracle
- **Seat requirements (all three simultaneously):** locally hosted (test vectors derive from real data and must stay inside the boundary); cheap enough to run per-rule at volume; competition-grade quantitative reasoning.
- **Benchmark basis:** Gemma 4 31B — AIME 89.2%, vs. Qwen 3.5 27B ≈ 49% and DeepSeek V4 42.5%. No other locally hostable model meets all three at once.
- **Function:** for each numeric business rule, independently compute expected outputs for test vectors **without seeing the generated code**. QA asserts process output equals oracle output — dual-implementation testing where the second implementation is a reasoning model.
- **Expanded in v2:** the oracle also runs **operate-phase spot-checks** on sampled live outputs (§4), feeding warranty tickets.
- **Limits:** the oracle is not infallible; oracle-vs-process disagreements are flagged for review, never auto-trusted. Produces the "N adjudicated correctly, M flagged for human review" delivery stat.

### 6.2 Agentic inspector swarm
- **Seat requirements:** always-on post-deploy probing means many concurrent agent loops; cost scales with active parameters.
- **Benchmark basis:** Gemma 4 26B MoE activates ≈3.8B parameters per forward pass; Gemma 4 31B scores 86.4% on τ2-bench. Alternatives activate ≥17B for comparable capability.
- **Function:** drive the deployed process agentically (API/browser tool use), probe auth and isolation, walk edge cases, file structured defect tickets. Inspectors do **not** write code; coder models implement fixes.
- **Expanded in v2:** periodic operate-phase probes (§4).

### 6.3 Validation gate and fallback
Before demos are locked: replicate both claims on our workload (oracle accuracy on demo rule sets vs. a Qwen baseline; inspector task-completion rate). If Gemma underperforms, swap the seat and drop the Gemma-prize pursuit. All seats are model-agnostic by design.

### 6.4 Edge (optional, cut-first)
Gemma E4B on-device (≈1.5 GB RAM, offline, native audio): one deck slide on run-time sovereignty; optionally one demo beat (KYC voice intake). No build dependency; first cut under time pressure.

## 7. Demo surface: UI, gallery, judge sandbox

### 7.1 UI — two connected views matching the lifecycle
- **Build view** (v1's factory floor): live task DAG, parallel worker panels streaming work, per-GPU ROCm telemetry, cost accrual meter vs. quote, QA defect board — plus new: the **amendment log** (GLM local patches vs. frontier consults rendered as a diff on the plan) and the **model BoM panel** (what the plan provisioned and why).
- **Operations view** (new, modest): the process registry per §4.

Landing page of the live demo URL = the platform itself, live. *(Exact visual design deferred to a separate session.)*

### 7.2 Gallery — five demos, cut order preserved
Each demo is a seed kit (synthetic data, mock connectors, validators) plus a rehearsed run — no canned outputs (track rule).

**Build priority / cut order:** KYC (hero) → Sovereign Surveillance (finale) → Regulatory Report Factory → process-mode demo (cuts before any locked demo, but see §7.3 — it doubles as the judge sandbox) → Claims Engine (**pre-decided cut**).

1. **KYC/AML Customer Onboarding (hero).** Documents → OCR → sanctions screening (public OFAC/EU lists) → PEP → adverse media → risk scoring → case file + audit trail. **v2 end-state:** the process lands in the registry and runs a live batch; then the **refinement beat** (§5) ships v2 on stage. Spotlights every layer, including the amendment log during certification.
2. **Trading Compliance Surveillance, Sovereign Mode (finale).** Spoofing/wash-trade detection over synthetic blotters with planted sequences; case management; regulator-ready reports. Sovereign Mode toggled **live**, network monitor proving zero external calls. Presentation ends here. Deterministic seeds; rehearse.
3. **Regulatory Report Factory.** Quarterly filing pipeline against a real public regulatory schema; validation wall goes from partial failures to **143/143 green** after the defect loop. **v2 addition:** the natural **re-run demo** — "Q2 ran in April; watch Q3 run now on new data, zero frontier calls, per-run cost on screen."
4. **Process-mode demo / judge sandbox seed.** ~200 synthetic contracts → planner designs topology + model BoM → fleet fans out live, one unit per worker → dashboard fills in → oracle spot-checks → saved as a re-runnable workflow.
5. **Insurance Claims Engine (pre-decided cut).** 500 synthetic claims → **487 adjudicated correctly, 13 flagged for human review**. Its flagged-for-review stat grafts onto KYC risk scoring if cut.

### 7.3 Judge sandbox (centerpiece of judge-run mode)
The deployed site offers **three synthetic companies** — a bank, a clinic, a law firm — each with browsable mock internal data (accounts and transactions; patient records; contracts). Judges pick a company, then either run **suggested prompts** ("flag dormant accounts with unusual reactivation patterns," "extract renewal dates and auto-renew clauses across all contracts") or **write their own** against that data — prompts alone are useless without data to run on; the mock data is what makes judge-run real. Every sandbox run is a genuine process-mode job: planner → topology → fan-out → live dashboard. Guards: per-run budget cap, job queue, pre-warmed fleet.

**Convergence:** the sandbox *is* process mode — demo 4 and judge-run mode are **one work item**, not two.

## 8. Economics

- **Build:** itemized quote (per the model BoM) → metered invoice (real tokens, real GPU-seconds). Quote is a range; invoice is exact.
- **Operate:** per-run metering — local GPU-seconds + local tokens. The trend line is the product claim.
- **Refine:** mini-quotes; frontier tokens itemized only when a consult fires.
- **Money slide:** *frontier intelligence is a capital expense, not a marginal cost.* Competitors pay frontier tokens and surrender data on every run; our customers pay once, at plan time, on sanitized specs.

## 9. Judging alignment

| Criterion | Where we score |
|---|---|
| Creativity & originality | Triage authority model (local model finishes & certifies frontier plans; visible amendment log); adaptive topology planner + model BoM; lifecycle-as-asset (versioned, re-runnable, refinable); Numeric Oracle dual-implementation QA; data-boundary architecture; Sovereign Mode |
| Product/market potential | Process-as-deliverable + recurring runs = recurring revenue; amortization wedge ("frontier as capex") retained by non-technical judges; regulated-enterprise wedge ("we operate where external AI is banned"); itemized quote→invoice |
| Completeness | Working end-to-end lifecycle; registry with live runs; **judge sandbox makes the platform judge-exercisable, not just watchable**; QA reports |
| Use of AMD platforms | Stages 0, 2, 4/4′, 6 + all operate-phase runs self-hosted on MI300X/ROCm/vLLM; stages 1 (Sovereign) and 5 on Fireworks (AMD-hosted); **GPU allocation justified by the plan's model BoM**; GPU time as an invoice line item |

**AMD gate evidence (mandatory, auto-pre-screened from repo + PDF deck + live URL — video not processed):**
- README: AMD infrastructure architecture + diagram.
- Code paths: vLLM/ROCm configs, Fireworks client, fleet orchestration.
- Live ROCm telemetry in the Build view.
- Deck slide: where each stage runs.

**Gemma prize ("Best AMD-Hosted Gemma Project", $2,000):** pursued via §6 roles; go/no-go at the §6.3 validation gate.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Judge sandbox fails live | Budget cap + queue + pre-warm; gallery of completed runs as the always-working surface |
| Refinement beat fails on stage | Rehearse with deterministic change request; pre-recorded fallback |
| "Runs forever/continuously" over-claims | Language rule: *operating with a warranty*; show oracle spot-check tickets on screen |
| Certification-loop latency at the front of the demo | Stream amendments/findings as produced; measure loop latency early in build week |
| GPU credits (~$100 AMD Cloud + Fireworks credits) | Elastic fleet sized per BoM; Fireworks-backed paths for the always-on URL; droplets scheduled around judging window |
| Five demo surfaces in four days | Sandbox = demo 4 = one work item; seed kits are content, not architecture; pre-decided cut (Claims); hero rehearsed first |
| Gemma benchmark claims don't reproduce | §6.3 validation gate; all seats model-agnostic; swap and continue |
| Generated processes fail QA repeatedly | Certified interfaces + test specs narrow the target; defect loop bounded, then flagged-for-human list |
| 30s response-time rule | UI streams progress continuously so no request appears hung |

## 11. Compliance checklist (track rules)

- [ ] Public GitHub repo, MIT-compliant, README with setup + usage.
- [ ] Slide deck as **PDF**.
- [ ] Demo video showing the real system.
- [ ] Live URL reachable through judging.
- [ ] All output in English; no hardcoded/canned answers.
- [ ] Any shipped container built `linux/amd64`.
- [ ] AMD usage legible in repo + deck + live URL within 30 seconds of skimming.

## 12. Open decisions

1. **Product name** (blocker for repo/deck/URL branding). "Factory" root doubly excluded (§ header). Candidates to be brainstormed separately.
2. Exact coder-fleet model IDs (choose during build against MI300X capacity).
3. Verifier deployment config: GLM 5.2-class size/quantization vs. dedicated GPU in the elastic plan.
4. GPU count vs. credit budget: measured after first end-to-end run.
5. §6.3 Gemma validation results → Gemma-prize go/no-go.
6. Whether Demo 5 (Claims) ships or is cut.
7. Edge/E4B beat in KYC demo: only if everything lands early.
8. Judge sandbox dataset scope: how deep each synthetic company's data goes (enough rows to make fan-out visible; small enough to seed in a day).
9. Exact UI design for Build view + Operations view (separate design session, per team).
