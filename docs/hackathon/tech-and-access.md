# Technology & access

Everything runs **fully in the cloud**. The stack: **AMD Developer Cloud (GPUs) · ROCm · Fireworks AI API · any open-source AI frameworks.**

## 🖥️ GPU access — start here

> **Hackathon GPU portal: https://notebooks.amd.com/hackathon**
> *(From the Discord kickoff announcement — this is the link to get GPU access.)*

- **AMD Developer Cloud** — on-demand AMD GPUs for training, fine-tuning, benchmarking, and deploying AI workloads.
- New ADP sign-ups get **$100 in AMD Developer Cloud credits**.
- Docs: [AMD Developer Cloud overview](https://www.amd.com/en/developer/resources/cloud-access/amd-developer-cloud.html) · [Getting started guide](https://www.amd.com/en/developer/resources/technical-articles/2025/how-to-get-started-on-the-amd-developer-cloud-.html)

## ⚡ Fireworks AI API

Fast, scalable API access to **AMD-hardware-hosted models** for inference, fine-tuning, and building pipelines.
- **$50 Fireworks AI API credits** for every participant (hackathon credit); another **$50** for new ADP sign-ups.
- Exact model IDs published on launch day. For **Track 1** the harness injects `FIREWORKS_API_KEY`, `FIREWORKS_BASE_URL`, `ALLOWED_MODELS`.
- Platform: https://fireworks.ai/ · Docs: https://docs.fireworks.ai/

## 🔧 ROCm

AMD's open-source GPU computing platform for AI/ML and high-performance workloads.
- Run **PyTorch / TensorFlow** on AMD GPUs; port CUDA workloads to AMD hardware.
- Docs: https://rocm.docs.amd.com/en/latest/ · Install: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/ · GitHub: https://github.com/ROCm/ROCm

## 🎓 Learning resources
- AMD AI Academy — courses, technical resources, tutorials, docs.
- Full training catalog: https://www.amd.com/en/developer/browse-by-resource-type/training.html
- lablab primer: [From Zero to AI Builder with AMD](https://lablab.ai/ai-articles/from-zero-to-ai-builder-amd-developer-program)
- DeepLearning.AI (1-month Pro for new sign-ups): https://www.deeplearning.ai/

---

## 🤝 Technology partners

### Gemma (Google DeepMind) — worth $2,000 to us
Family of lightweight, open-weight models (same research as Gemini). **Apache 2.0.**
- **Access:** through **Fireworks AI** + **AMD Developer Cloud**. Usage draws from hackathon or new-member Fireworks credits — **no separate sign-up**.
- **Track 3 prize:** **Best AMD-Hosted Gemma Project — $2,000.** If Gemma fits our product, using it meaningfully is a second, independent shot at prize money.
- How to use: call a Gemma model via the Fireworks API, run the app on AMD Developer Cloud, check track model restrictions.
- Docs: https://ai.google.dev/gemma/docs · Model: https://deepmind.google/models/gemma/

> **Note:** for **Track 1** Gemma variants appear in the allowed-models list (`gemma-4-31b-it`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it-nvfp4`). For **Track 3** there's no model restriction — use any Gemma model via Fireworks.

### Native.Builder (NativelyAI)
AI-native environment for building software, workflows, and agents fast — use **Fireworks AI credits inside Builder** to go from concept to prototype quickly.
- Site: https://www.nativelyai.com/ · Start: https://beta.nativelyai.com/
- Docs: https://docs-builder.nativelyai.com/ · Getting started: https://docs-builder.nativelyai.com/introduction/getting-started

---

## 💳 Getting credits — quick recap
1. **Register on lablab.ai** and enroll in the hackathon.
2. **Sign up for the AMD AI Developer Program (ADP)** — required for credits + approval.
3. **Hackathon credits** ($50 Fireworks, all participants): day one if registered by **Jul 2**, else **from Jul 7**.
4. **New-member credits** ($100 AMD Cloud + $50 Fireworks + DeepLearning.AI Pro): separate **2–3 business-day** manual approval, independent timeline.
5. Get GPU access at **https://notebooks.amd.com/hackathon**.

*(Full credit timing in [overview.md](overview.md).)*
