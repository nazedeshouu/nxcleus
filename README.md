# AMD Developer Hackathon: ACT II — 🦄 Unicorn Track

Working repository for our entry to the **AMD Developer Hackathon: ACT II** (Track 3, Unicorn / Open Innovation).
All reference material has been gathered from the [official event page](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-ii/) and the participant guide, and organized below.

> **Our track:** 🦄 **Track 3 — Unicorn (Open Innovation).** Build an original AI product on AMD compute. No benchmarks — judged on creativity, product/market potential, completeness, and use of AMD platforms. **AMD compute usage is mandatory or the project is disqualified.**

---

## ⏱️ The essentials

| | |
|---|---|
| **Event** | AMD Developer Hackathon: ACT II (online, on lablab.ai) |
| **Kick-off** | Mon **Jul 6, 2026 · 9:00 PM** Kazakhstan Time (UTC+5) |
| **Submission deadline** | **Jul 11, 2026 · 9:00 PM** Kazakhstan Time (UTC+5) |
| **Build window** | ~5 days |
| **Our track prize** | 🥇 $2,500 · 🥈 $1,500 · 🥉 $1,000 (+ $2,000 Gemma bonus) |
| **Stack** | AMD Developer Cloud (GPUs) · ROCm · Fireworks AI API · any open-source models/frameworks |
| **Deliverables** | Public GitHub repo · Demo video · Slide deck (PDF) · Live demo URL (recommended) |

## 🚦 Immediate action items
1. **Register** on lablab.ai and sign up for the **AMD AI Developer Program (ADP)** — required for credits and approval.
   - ⚠️ Day-one credits required registration by **July 2**. Registering now still works, but hackathon compute/credits allocate **from July 7 onward**.
2. Join the **[AMD Discord](https://discord.gg/mVUBbE5KjN)** (infra/hardware help) and **[lablab Discord](https://discord.gg/lablabai)** (teammates, Q&A).
3. Lock the idea → see [`project/IDEA.md`](project/IDEA.md).
4. Spin up an **AMD Developer Cloud** GPU instance early and prove ROCm works for the chosen stack.

---

## 📚 Documentation index

Everything about the hackathon lives in [`docs/hackathon/`](docs/hackathon/):

| Doc | What's in it |
|---|---|
| [overview.md](docs/hackathon/overview.md) | Dates, prize pool, credits, how to register |
| [**unicorn-track.md**](docs/hackathon/unicorn-track.md) | ★ Our track — full task, deliverables, judging, rules, strategy |
| [other-tracks.md](docs/hackathon/other-tracks.md) | Track 1 & 2 specs (context / fallback) |
| [rules-and-submission.md](docs/hackathon/rules-and-submission.md) | General rules, what to submit, image/arch requirements |
| [tech-and-access.md](docs/hackathon/tech-and-access.md) | AMD Cloud, ROCm, Fireworks AI, Gemma, Native.Builder + how to get credits |
| [resources.md](docs/hackathon/resources.md) | Every official link in one place |
| [schedule-and-people.md](docs/hackathon/schedule-and-people.md) | Event agenda + speakers / mentors / judges |

Source artifacts (original PDF + raw scrape) are in [`resources/`](resources/).

**Engineering spec map** (logic / AI / backend architecture) lives in [`docs/specs/`](docs/specs/00-INDEX.md) — locked stack: Python + FastAPI control plane on an always-on VM, elastic MI300X fleet for all inference, custom event-sourced orchestrator.

## 🗂️ Repo layout
```
.
├── README.md                     ← you are here
├── docs/hackathon/               ← cleaned, structured event reference
├── resources/
│   ├── participant-guide.md      ← official task spec, readable Markdown
│   ├── participant-guide.pdf     ← original 8-page PDF (primary source)
│   └── lablab-listing-raw.md     ← verbatim scrape of the event page
└── project/
    ├── IDEA.md                   ← lock the concept here (fill me in)
    ├── SUBMISSION-CHECKLIST.md   ← everything needed to submit, tracked
    └── design/                   ← brand, deck, demo assets
```

## 📌 Project status
- [x] Repository initialized & event fully documented
- [ ] Idea locked (`project/IDEA.md`)
- [ ] ADP registration + credits confirmed
- [ ] AMD Developer Cloud instance running
- [ ] MVP built
- [ ] Demo video + slide deck
- [ ] Submitted on lablab.ai

*More project-specific details incoming — this README will grow into the public submission README (setup + usage instructions required).*
