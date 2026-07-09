# AMD Developer Hackathon: Participant Submission Guide

> Faithful Markdown transcription of the official 8-page PDF (`participant-guide.pdf`).
> Source: https://drive.google.com/file/d/1UGpOZiGGGBqQhGQxX7g19QAA-Dq9hPKk/view
> This document covers everything you need to build and submit a competitive entry. Exact
> evaluation inputs are intentionally omitted: your agent must be genuinely capable, not
> hardcoded to specific answers.

---

## Track 1: General-Purpose AI Agent

### What you are building

An AI agent that handles a wide variety of natural language tasks across multiple capability domains, using Fireworks AI models as efficiently as possible.

### Capability categories

Your agent will be evaluated across all eight categories. Build for all of them:

| # | Category | What it covers |
|---|---|---|
| 1 | Factual knowledge | Explaining concepts, definitions, and how things work |
| 2 | Mathematical reasoning | Multi-step arithmetic, percentages, word problems, projections |
| 3 | Sentiment classification | Labelling sentiment and justifying the classification |
| 4 | Text summarisation | Condensing passages to a specific format or length constraint |
| 5 | Named entity recognition | Extracting and labelling entities (person, org, location, date) |
| 6 | Code debugging | Identifying bugs in code snippets and providing corrected implementations |
| 7 | Logical / deductive reasoning | Constraint-based puzzles where all conditions must be satisfied |
| 8 | Code generation | Writing correct, well-structured functions from a spec |

### What to submit

A **Docker image** pushed to a public registry (e.g. GitHub Container Registry, Docker Hub).
Check out the Image Architecture requirement at the bottom of this document.

Your container must:

**1. Read tasks from `/input/tasks.json` on startup**

```json
[
  { "task_id": "t1", "prompt": "Summarise the following text in one sentence: ..." },
  { "task_id": "t2", "prompt": "..." }
]
```

**2. Write results to `/output/results.json` before exiting**

```json
[
  { "task_id": "t1", "answer": "..." },
  { "task_id": "t2", "answer": "..." }
]
```

### Environment variables

The harness injects these at runtime. Read them from the environment: do not hardcode values or bundle a `.env` file in your image.

```python
import os

api_key  = os.environ["FIREWORKS_API_KEY"]      # provided by harness — do not use your own
base_url = os.environ["FIREWORKS_BASE_URL"]     # route ALL Fireworks calls through this URL
models   = os.environ["ALLOWED_MODELS"].split(",")  # exact model IDs published on launch day
```

For local development you can use a `.env` file, but your submitted container must read these purely from the environment: the harness will inject the real values at evaluation time.

| Variable | Description |
|---|---|
| `FIREWORKS_API_KEY` | Provided by the harness — use this key, not your own |
| `FIREWORKS_BASE_URL` | Base URL for all Fireworks API calls — must be used to configure your client |
| `ALLOWED_MODELS` | Comma-separated list of permitted Fireworks AI model IDs, published on launch day |

> **Important:** All API calls must go through `FIREWORKS_BASE_URL`. Calls that bypass this URL will not be recorded and the submission will score zero tokens. Do not hardcode model IDs: read from `ALLOWED_MODELS` at runtime.

### Rules

- Exit code `0` on success, non-zero on failure
- Maximum runtime: **10 minutes**
- Only models in `ALLOWED_MODELS` are permitted, calls to other models invalidate the submission
- `/output/results.json` must be valid JSON, malformed output scores zero
- **Local models and tokens used locally count as zero** for the final score; all inference must go through Fireworks AI via `FIREWORKS_BASE_URL`
- Do not hardcode or cache answers; evaluation uses unseen prompt variants
- Image compressed size must not exceed 10GB — larger images are rejected before pulling
- Submissions are rate-limited to 10 per hour per team

### Scoring

1. **Accuracy gate:** LLM-Judge evaluates each answer against the expected intent. Submissions below the accuracy threshold are excluded from the leaderboard.
2. **Token efficiency:** submissions that pass the accuracy gate are ranked ascending by total tokens recorded by the judging proxy. Fewer tokens = higher rank.

---

## Track 2: Video Captioning Agent

### What you are building

An AI agent that watches a video clip and generates a caption in a requested style. Build your pipeline to handle a wide variety of video content: different scenes, settings, subjects, and visual styles.

### Styles your agent must support

| Style | Description |
|---|---|
| `formal` | Professional, objective, factual tone |
| `sarcastic` | Dry, ironic, lightly mocking |
| `humorous_tech` | Funny, with technology or programming references |
| `humorous_non_tech` | Funny, everyday humour with no technical jargon |

### What to submit

A **Docker image** pushed to a public registry.

Your container must:

**1. Read tasks from `/input/tasks.json` on startup**

```json
[
  {
    "task_id": "v1",
    "video_url": "https://storage.example.com/clips/clip1.mp4",
    "styles": ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"]
  }
]
```

**2. Write results to `/output/results.json` before exiting**

```json
[
  {
    "task_id": "v1",
    "captions": {
      "formal": "...",
      "sarcastic": "...",
      "humorous_tech": "...",
      "humorous_non_tech": "..."
    }
  }
]
```

No inference log is required for Track 2.

Check out the Image Architecture requirement at the bottom of this document.

### Environment variables

No API key or model restriction is injected. You may call any model, API, or framework: use your own credentials inside the container.

### Example clips

Use these to develop and test your agent. Evaluation uses a hidden set your agent has never seen, ensure your pipeline generalises beyond these examples.

| Clip | URL | Content |
|---|---|---|
| v1 | `https://storage.googleapis.com/amd-hackathon-clips/1860079-uhd_2560_1440_25fps.mp4` | Urban autumn boulevard with golden trees and city traffic |
| v2 | `https://storage.googleapis.com/amd-hackathon-clips/13825391-uhd_3840_2160_30fps.mp4` | Orange kitten among green foliage in a garden |
| v3 | `https://storage.googleapis.com/amd-hackathon-clips/3044693-uhd_3840_2160_24fps.mp4` | Office worker at a desktop computer in a modern open-plan office |

### Rules

- Exit code `0` on success, non-zero on failure
- Maximum runtime: **10 minutes**
- No model restriction: any model, framework, or API is permitted
- **Video clips in the hidden evaluation set are 30 seconds to 2 minutes in length**
- Output must include a caption for every requested style for every clip, missing styles score zero for that clip
- `/output/results.json` must be valid JSON, malformed output scores zero
- Image compressed size must not exceed 10GB — larger images are rejected before pulling
- Submissions are rate-limited to 10 per hour per team

### Scoring

Each caption is scored on two dimensions by an LLM-Judge:

1. **Caption accuracy** (0–1): how faithfully the caption reflects the video content
2. **Style match** (0–1): how well the caption matches the requested tone

Final score = weighted average across all clips and all four styles. Evaluation uses a hidden set of ~12 clips spanning varied content (nature, urban, animals, people, sports, food, weather, technology). Agents that only work on the three example clips above will score poorly.

---

## Track 3: Unicorn (Open Innovation)

### What you are building

An original AI application that uses AMD compute resources. There is no fixed task, we are looking for the most innovative, technically impressive, and practically useful projects.

### What to submit

| Item | Required |
|---|---|
| GitHub repository URL | Yes |
| Demo video | Yes |
| Slide deck | Yes |
| Live demo / hosted URL | Optional but recommended |

> **Note:** automated pre-screening only inspects the GitHub repository, slide deck (PDF), and live demo/hosted URL — it does not process the demo video.

No Docker image is required for Track 3.

### Judging

Submissions are pre-screened automatically for AMD resource usage and originality, then reviewed by human judges. **AMD compute usage is a requirement: projects that do not demonstrate it will be disqualified.**

---

## General rules (all tracks)

- Your container must start and be ready within **60 seconds**
- Response time per request must be under **30 seconds**
- All responses must be in **English**
- Do not hardcode or cache answers to specific inputs — evaluation uses unseen variants
- Container images must be publicly pullable at submission time

## Image architecture requirement

The judging VM runs `linux/amd64`. Your image must include a `linux/amd64` manifest or it will fail to pull and score zero.

If you build on Apple Silicon (M1/M2/M3), add `--platform linux/amd64` to your build command:

```shell
docker buildx build --platform linux/amd64 --tag your-image:latest --push .
```

Standard `linux/amd64` builds (e.g. built on Intel/AMD or GitHub Actions) are fine without any changes.
