# 🦄 Track 3 — Unicorn (Open Innovation) — OUR TRACK

> **This is the track we're competing in.** Everything here is the source of truth for what to build and how we'll be judged.

## What we're building

> *"Your idea. AMD infrastructure. No benchmarks, no constraints — just build."*

An **original AI application that uses AMD compute resources**. There is **no fixed task**. Use any open-source models and frameworks alongside **AMD GPUs and/or Fireworks AI API** credits to build a **product- or startup-oriented** project.

Judges are looking for the most **innovative, technically impressive, and practically useful** projects. **Think startup pitch, not benchmark run.** Submissions are *not* scored on speed, token usage, or accuracy.

## ✅ Deliverables (what to submit)

| Item | Required? | Notes |
|---|---|---|
| **GitHub repository URL** | ✅ Yes | Public. Include a README with setup + usage instructions. |
| **Demo video** | ✅ Yes | Shows the product working. |
| **Slide deck** | ✅ Yes | **PDF.** The pitch. |
| **Live demo / hosted URL** | ⭐ Optional but strongly recommended | A working, reachable app. |

Submit through the **lablab.ai platform** before the deadline. On the platform the fields map to: Project Title, Short + Long Description, Technology/Category tags, **Cover Image**, **Video Presentation**, **Slide Presentation**, **Public GitHub Repository**, **Demo Application Platform**, **Application URL**.

> ⚠️ **What the automated pre-screen actually reads:** the **GitHub repository, the slide deck (PDF), and the live demo / hosted URL**. It **does NOT process the demo video**. → Make sure your AMD usage and the core story are legible in the **repo + deck + live URL**, not only in the video.

> ℹ️ **No Docker image is required for Track 3.** (Containerization is mandatory for Tracks 1 & 2, not for us — though a hosted/containerized live demo still helps.)

## 🧪 How we're judged

Track 3 is **evaluated by human judges** (Tracks 1 & 2 are leaderboard-ranked). Flow: **automated pre-screening** for AMD-resource usage + originality → **human judges** score.

### Judging criteria
| Criterion | What judges want |
|---|---|
| **Creativity & Originality** | Uniqueness of the solution — novel approaches, new behaviors. |
| **Product / Market Potential** | The startup/product vision — how compelling and viable in a real market. |
| **Completeness** | How fully realized and functional the submitted project is. |
| **Use of AMD Platforms** | How **meaningfully** AMD infrastructure is incorporated. |

### 🚨 The one hard gate
> **AMD compute usage is a REQUIREMENT. Projects that do not demonstrate it will be DISQUALIFIED.**

This is non-negotiable and it's auto-screened. Whatever we build **must** run real work on **AMD Developer Cloud GPUs (ROCm)** and/or **Fireworks AI API** (AMD-hardware-hosted models) — and we must make that usage **obvious and provable** in the repo, deck, and live demo.

## 📏 Rules that apply to us (from the general rules)

Track 3 skips the Docker/harness rules, but these still apply:
- **All responses / output in English.**
- **Do not hardcode or cache answers** to specific inputs — the product should genuinely work.
- If we *do* ship a container for the live demo, the judging VM is **`linux/amd64`** (build with `--platform linux/amd64` on Apple Silicon).
- Submission must be **original and MIT-compliant**.

See [rules-and-submission.md](rules-and-submission.md) for the complete rule set.

---

## 🎯 Strategy notes (how to win this track)

Mapping effort directly to the four criteria + the hard gate:

1. **Make AMD usage the spine, not a checkbox.** Pick an idea where AMD GPUs / Fireworks are *load-bearing* — e.g. real-time inference on MI-series GPUs, fine-tuning on ROCm, a latency- or throughput-heavy workload that only makes sense on real GPU compute. Show it: architecture diagram, the ROCm/Fireworks calls in code, a note in the README, a slide on "why AMD."
2. **Pitch a real product.** Name it, give it a crisp one-line value prop, a target user, and a "why now." Judges reward market potential — treat the deck like a seed pitch (problem → solution → demo → market → moat → ask).
3. **Ship something that actually runs.** Completeness beats ambition. A narrow, polished, *working* live demo URL scores higher than a broad half-built vision. Prioritize a working end-to-end path.
4. **Lead with originality.** Avoid the obvious "chatbot on docs" unless there's a genuine twist. New behavior / novel interaction / an unexpected use of GPU compute stands out.
5. **Stack the Gemma bonus ($2,000).** The **Best AMD-Hosted Gemma Project** prize is a second, independent shot at money. If Gemma (via Fireworks / AMD Cloud) fits the product, use it meaningfully — see [tech-and-access.md](tech-and-access.md).
6. **Optimize for the pre-screen.** Since it reads repo + PDF deck + live URL (not the video): put the AMD story, setup instructions, and a working link where the automated pass and a skimming judge will see them in 30 seconds.

### Pre-submission gut check
- [ ] Does a stranger reading only the **README + deck + live URL** understand what it is and see the AMD usage?
- [ ] Is AMD compute **provably** used (not just claimed)?
- [ ] Does the live demo work from a clean session?
- [ ] Is there a clear market/product story, not just a tech demo?
- [ ] Deck exported as **PDF**; video shows the real thing; repo is **public**.

*(Idea development happens in [`../../project/IDEA.md`](../../project/IDEA.md); submission tracking in [`../../project/SUBMISSION-CHECKLIST.md`](../../project/SUBMISSION-CHECKLIST.md).)*
