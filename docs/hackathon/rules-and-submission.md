# Rules & submission requirements

## General rules (all tracks)

- Your container must **start and be ready within 60 seconds**.
- **Response time per request** must be under **30 seconds**.
- **All responses must be in English.**
- **Do not hardcode or cache answers** to specific inputs — evaluation uses unseen variants.
- Container images must be **publicly pullable** at submission time.
- Submissions must be **original and MIT-compliant**.

## Image architecture requirement (Tracks 1 & 2; any container for Track 3)

- The judging VM runs **`linux/amd64`**. Your image **must include a `linux/amd64` manifest** or it fails to pull and scores zero.
- On Apple Silicon (M1/M2/M3), build with the platform flag:
  ```bash
  docker buildx build --platform linux/amd64 --tag your-image:latest --push .
  ```
- Standard `linux/amd64` builds (Intel/AMD or GitHub Actions) are fine as-is.
- **Image size ≤ 10 GB compressed** — larger images are rejected before pulling.
- **Rate limit: ≤ 10 submissions per hour per team** — test locally before repeated submits.

## What to submit (lablab.ai platform)

Submit through the lablab.ai platform **before the deadline**. Fields:

**📋 Basic information**
- Project Title
- Short Description
- Long Description
- Technology & Category tags

**📸 Cover image & presentation**
- Cover Image
- Video Presentation
- Slide Presentation

**💻 App hosting & code repository**
- Public GitHub Repository
- Demo Application Platform
- Application URL

**Requirements**
- Submitted through lablab.ai before the deadline.
- All submissions **containerized** (mandatory for Tracks 1 & 2; Track 3 needs no Docker image but a hosted/containerized live demo helps).
- GitHub repo **public**, with a **README** covering setup + usage.
- App **runnable** from the provided instructions.

## Per-track submission summary

| | Track 1 | Track 2 | Track 3 (ours) |
|---|---|---|---|
| Docker image | ✅ required | ✅ required | ❌ not required |
| GitHub repo (public) | ✅ | ✅ | ✅ required |
| Demo video | ✅ | ✅ | ✅ required |
| Slide deck (PDF) | ✅ | ✅ | ✅ required |
| Live demo / hosted URL | — | — | ⭐ recommended |
| Scoring | leaderboard (accuracy → tokens) | leaderboard (accuracy + style) | human judges |

## Track 3 pre-screen reminder
Automated pre-screening for Track 3 inspects the **GitHub repo, slide deck (PDF), and live demo/hosted URL** — it **does not process the demo video**, and it verifies **AMD compute usage** (mandatory, or disqualified). Details in [unicorn-track.md](unicorn-track.md).

## Fine print
Participation is voluntary. Prizes/opportunities depend on eligibility, availability, and third-party sponsors. Rules, prizes, and terms may change or be canceled at lablab.ai's discretion. **Prize distribution may take up to 90 days.**
Full terms: https://lablab.ai/terms-of-use · Hackathon guidelines: https://lablab.ai/ai-articles/hackathon-guidelines
