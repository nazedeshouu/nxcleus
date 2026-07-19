# Local hardening review and handoff

Date: 2026-07-18

## Isolation and scope

- The original repository at `C:\Users\Alibek\Work\amd-hackathon` was not modified by this work.
- All hardening work lives in the isolated clone at `C:\Users\Alibek\Work\amd-hackathon-security-local`, branch `codex/security-hardening`.
- The hardening series starts after `621ccb5`; backend/integration work ends at `4c18e22`, and the reviewed frontend slice is `900b9fa`.
- CI, environment guidance, README corrections, and this handoff live in the final local hardening commit. This review-only PR publishes only this document; the hardening code remains local, and nothing was merged or deployed.

This review distinguishes a deterministic mock demonstration from a verified production execution. It does not treat a fallback, missing output, missing test runner, or synthetic corpus as production evidence.

## Review of the junior overview

| Junior claim | Assessment | Current state |
|---|---|---|
| An arbitrary prompt becomes the canned KYC process in mock mode | Confirmed, with context | The mock client is fixture-driven and remains suitable for a scripted offline demonstration, not proof of general prompt handling. General behavior requires configured live/auto backends and separate validation. |
| Generated `process.py` and runtime entrypoint contracts disagree; generated indentation can be invalid | Confirmed at the reviewed base | Fixed in `54b4584`: generated execution now has an explicit worker contract and fails closed on load/compile/entrypoint errors. |
| Staging hides a broken entrypoint behind an accepted/review fallback | Confirmed at the reviewed base | Fixed in `54b4584`: broken generated execution cannot become a verified successful run. |
| Code execution can report green when Docker/tests did not actually run | Confirmed at the reviewed base | Fixed in `320b326`: unavailable execution is unverified, the generated package surface is validated, launch failures remain failures, and stage gates reject missing evidence unless an explicit mock-only demo override is enabled. |
| `no_actual` can become a visual match and QA can deliver without real output | Confirmed at the reviewed base | Backend delivery evidence is fail-closed in `5c0c4b5`; frontend event/status truth is preserved in `f854ed7`. Commit `900b9fa` adds a direct `no_actual` regression test. |
| QA emits `fix_applied` without persisting and retesting the repair | Confirmed at the reviewed base | Fixed in `5c0c4b5`: repair state, changed files, retest evidence, and terminal ticket state are now distinguished. |
| Missing corpora silently create realistic-looking synthetic units | Confirmed at the reviewed base | Fixed in `9b8ad11`: real corpus evidence is required by default. Synthetic units require mock mode, a server escape hatch, and an explicit per-job/per-run request, and remain badged unverified demo output. |
| Global Sovereign Mode did not reliably govern new jobs/runs | Confirmed at the reviewed base | `a4784b5` applies the default to new jobs and `e8834ee` persists the captured policy through processes/runs. Existing jobs retain their captured policy. |
| YAML registry loading can fall back because Windows uses the wrong encoding | Confirmed | Fixed in `58ba286` with explicit UTF-8 reads. |
| A clean clone lacks a dependable demo bootstrap | Confirmed | `fe8a552` makes seed generation and the mock golden path evidence-backed and fail-fast. |
| Custom datasets, database drivers, and advertised integrations disagree | Confirmed in part | `4c18e22` aligns custom-dataset API contracts, connection behavior, production database dependencies, fleet integration, and adds integration contract tests. External services still need environment-specific smoke tests. |
| “Live” only meant backend reachability | Confirmed | `f854ed7` separates runtime verification/model truth in the UI; the final slice documents that health is not model mode. |
| Sandbox concurrency was effectively fixed at one worker | Correct for the reviewed implementation/default | `369b825` implements a bounded worker set based on `SANDBOX_MAX_CONCURRENT`. The safe default remains `1`; higher capacity still needs deployment-level load validation. |
| CSV uploads are read fully into memory | Confirmed, unresolved | Explicitly outside this hardening slice; see open items below. |

## Fixed commit map

| Commit | Scope |
|---|---|
| `d5b404d` | Contains untrusted file paths inside trusted workspace/data roots and adds path regression coverage. |
| `54b4584` | Makes generated-process loading/execution fail closed and reconciles generator/runtime contracts. |
| `320b326` | Makes generated-code compile/test/integration gates evidence-based and fail closed. |
| `5c0c4b5` | Makes QA repair, oracle evidence, tickets, and delivery gates reflect actual persisted/retested results. |
| `9b8ad11` | Requires corpus/runtime evidence and explicitly gates/badges synthetic demo runs. |
| `58ba286` | Reads YAML registries as UTF-8. |
| `f854ed7` | Preserves failed/unverified/no-actual truth through API adapters, state folds, and UI. |
| `a4784b5` | Applies the Sovereign default when creating new jobs. |
| `e8834ee` | Persists Sovereign enforcement into registered processes and later runs. |
| `fe8a552` | Makes clean-clone seed/bootstrap and the offline golden path reproducible and fail-fast. |
| `369b825` | Makes engine/sandbox async lifecycle and configured concurrency safe. |
| `ebfd779` | Makes process registration retry-safe. |
| `f25c710` | Fails interrupted runs when replay cannot honestly resume them. |
| `4c18e22` | Aligns advertised connection, custom dataset, Docker dependency, fleet, and integration contracts. |
| `900b9fa` | Makes local open-demo presenter access truthful, adds frontend truth regressions, and route-splits the application. |

The final local hardening commit (`77de495`) also adds project setup guidance, `.env.example`, a least-privilege GitHub Actions CI workflow, and claim corrections in the root README. Those companion changes are not part of this review-only PR.

## Verification evidence

- Backend full suite from the final backend commit: `405 passed, 9 skipped`.
- Ruff, including the node agent: clean.
- Frontend unit tests: `11 passed` across 2 files on Vitest `4.1.10` in the Node environment.
- Frontend lint: no errors; two existing Fast Refresh warnings remain in `src/components/shell/breadcrumbs.tsx`.
- Frontend production build: successful on Node 24-compatible dependencies.
- Route splitting reduced the initial JS entry chunk from `707.67 kB` (`198.13 kB` gzip) to `263.41 kB` (`83.87 kB` gzip); the largest lazy route chunk is `104.42 kB` (`28.45 kB` gzip).
- The CI workflow parses successfully as YAML, and `git diff --check` reports no whitespace errors.
- Docker was unavailable locally, so neither Docker image was built here. CI builds both the production image and `Dockerfile.codeexec` before the golden path and full pytest run.

## Explicitly unresolved or skipped

1. **Public reads, CORS, and broader authentication/security posture:** intentionally not changed per the user's request. `ADMIN_TOKEN` protects presenter/admin writes when configured; it is not a complete shared-deployment authentication design. Review public data exposure, origins, rate limiting, session identity, and deployment access controls before production use.
2. **CSV whole-memory ingestion:** large CSV uploads can still consume backend memory. Add streaming parsing, row/byte limits, backpressure, and cancellation in a separate change.
3. **Codebase Git/local-path trust:** repository cloning and local-path ingestion need a dedicated threat model covering SSRF, credentials, symlinks, repository size, hooks/config, and tenant isolation. This slice did not redesign ingestion.
4. **Stage 7 event delivery is at-least-once:** registration is retry-safe, but consumers must still tolerate duplicate delivery/events and use stable idempotency keys.
5. **Docker builds were unavailable locally:** CI is the first environment that builds both images and exercises Docker isolation. A successful CI run is required before adoption.
6. **No frontend browser E2E suite:** unit/lint/build checks do not validate real navigation, token entry, SSE reconnect behavior, or presenter flows in a browser.
7. **Invite/sign-up is not implemented in this repository:** the repository contains Presenter mode using `ADMIN_TOKEN`, not an invite-code account system. An invite prompt on a hosted page belongs to an external deployment/access layer and must be diagnosed there. For a local demo, leave `ADMIN_TOKEN` empty; for a shared demo, set it and enter the same value in Presenter mode.
8. **No remote deployment was performed:** no hosted environment, DNS, secrets, database, or external provider was changed or smoke-tested.
9. **Mock generality remains limited:** a deterministic fixture-backed KYC demo is not evidence that arbitrary requests produce relevant processes. Demonstrate arbitrary requests only with an explicitly configured model backend and captured output/test evidence.

## Teammate adoption without a merge

Review the isolated work directly first:

```bash
git -C C:/Users/Alibek/Work/amd-hackathon-security-local status --short
git -C C:/Users/Alibek/Work/amd-hackathon-security-local log --oneline 621ccb5..codex/security-hardening
git -C C:/Users/Alibek/Work/amd-hackathon-security-local show --stat 900b9fa
git -C C:/Users/Alibek/Work/amd-hackathon-security-local show --stat codex/security-hardening
```

`git status --short` should be empty after the handoff commit; that is the simplest proof that the isolated review tree contains no forgotten local diff.

The teammate can fetch the local branch into their own clone and cherry-pick the committed hardening series without merging the branch:

```bash
git fetch C:/Users/Alibek/Work/amd-hackathon-security-local codex/security-hardening
git cherry-pick d5b404d^..HEAD
```

Run CI before accepting the result; no remote deploy is part of this handoff. The teammate may also cherry-pick a smaller contiguous prefix or individual atomic commits after reviewing the commit map.
