# Implementation Plan: Automatic Deploy on Merge

**Branch**: `009-auto-deploy-on-merge` (spec folder; rollout goes through a PR into `main`) | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-auto-deploy-on-merge/spec.md`

## Summary

**No new repositories** (user decision): the source is this existing GitHub repo, images go to the existing Artifact Registry repo `ftm`, and every code change merged to `main` deploys to the existing Cloud Run service `ftm-language-generator`. The only new things are the GitHub link, two triggers and two service accounts.

Connect the GitHub repo to Cloud Build with a 2nd-gen connection: the Google Cloud Build GitHub App, approved once by a `curiouslearning` org owner. Create two triggers in `us-central1`:
- **`ftm-deploy-main`**: on push to `main`, unless only docs/specs changed, runs `cloudbuild.yaml` as a new least-privilege SA `ftm-deployer`. A small guard in the deploy step skips deploying when a newer build is already live.
- **`ftm-pr-check`**: on PRs into `main`, runs a new build-only `cloudbuild-pr.yaml` as `ftm-pr-builder`. It has no push, no deploy and no secrets. Outside contributors need a `/gcbrun` comment.

GitHub shows both as checks. Nothing is stored in GitHub.

Rollout: commit the currently local deploy files + specs 007–009 on a branch → PR → set up the connection, SAs and triggers → merge, which is the first automatic deploy.

## Technical Context

**Language/Version**: YAML (Cloud Build configs), bash in the deploy step (cloud-sdk image); no Python changes

**Primary Dependencies**: Cloud Build 2nd-gen GitHub connection and triggers, Artifact Registry, Cloud Run, IAM; gcloud SDK 588 locally

**Storage**: none (the GitHub token lives in a Secret Manager secret that Cloud Build creates)

**Testing**: manual, quickstart V1–V7 (real PRs and merges)

**Target Platform**: GitHub `curiouslearning/CL-Language-Publishing-Automation` → Cloud Build `us-central1` → Cloud Run `ftm-language-generator`

**Project Type**: CI/CD configuration for the existing web service

**Performance Goals**: deploy starts < 1 min after merge; live < 10 min (today's build takes ~4 min)

**Constraints**: no credentials in GitHub; PR builds have no secret or deploy access; the newest commit wins; a failed deploy keeps the old revision; docs-only merges don't deploy

**Scale/Scope**: 2 triggers, 2 SAs, 1 connection, 1 new config file, edits to `cloudbuild.yaml`, README, CLAUDE.md, and committing the untracked deploy files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I–IV (pipeline behaviour, matching, audio, log contract) | ✅ N/A | No pipeline or app code changes |
| V. No secrets in the repository | ✅ | Nothing in GitHub secrets; the token is in Secret Manager; PR builds can't read secrets. `git status` is checked before the rollout commit (no `client_secret*`, `token.json`, `.env`, `lang/`). |
| Tech: no new dependency | ✅ | No Python deps; cloud services only |
| Workflow: CLAUDE.md updated | ✅ | Hosting section: automatic deploys, triggers, SAs, rollback |
| Workflow: manual verification | ✅ | quickstart V2–V6 with real PRs/merges |

**Post-design re-check**: passes. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/009-auto-deploy-on-merge/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/build-configs.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
cloudbuild.yaml         # serviceAccount ftm-deployer; deploy step → bash guard + labels (R3, R5)
cloudbuild-pr.yaml      # NEW: build-only PR check as ftm-pr-builder
Dockerfile, .dockerignore, .gcloudignore   # committed for the first time (R6), content unchanged
README.md               # "Deploy to Cloud Run": automatic deploys, one-time trigger setup, status, rollback, manual deploy
CLAUDE.md               # Hosting: triggers, SAs, newest-wins guard, docs-only skip
```

**Structure Decision**: config files at the repo root next to the existing `cloudbuild.yaml`. Cloud resources are created with documented `gcloud` commands, which are recorded in the README so they can be reproduced.

## Complexity Tracking

None.
