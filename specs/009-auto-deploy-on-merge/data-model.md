# Data Model: Automatic Deploy on Merge

No application data. Cloud resources in `ftm-language-generator` (region `us-central1` unless noted):

| Resource | Name | Key settings |
|---|---|---|
| GitHub connection (2nd gen) | `ftm-github` | Authorized through Cloud Build's GitHub App, installed on org `curiouslearning`, limited to one repository. The token is in a Secret Manager secret Cloud Build creates. |
| Link to the existing GitHub repo | `cl-language-publishing-automation` | a pointer to `https://github.com/curiouslearning/CL-Language-Publishing-Automation.git`; **no new repo is created** |
| Image registry (existing, reused) | Artifact Registry `ftm` | `us-central1-docker.pkg.dev/ftm-language-generator/ftm/ftm-language-generator`; no new registry |
| Cloud Run service (existing) | `ftm-language-generator` | receives every code merge to `main` |
| Service account | `ftm-deployer` | roles per research R4; no secret access |
| Service account | `ftm-pr-builder` | `roles/logging.logWriter` only |
| Trigger | `ftm-deploy-main` | push, `^main$`, `cloudbuild.yaml`, ignored files `**/*.md, specs/**, .specify/**, .claude/**, .github/**`, SA `ftm-deployer`, logs linked from GitHub |
| Trigger | `ftm-pr-check` | PR into `^main$`, `cloudbuild-pr.yaml`, comment control `COMMENTS_ENABLED_FOR_EXTERNAL_CONTRIBUTORS_ONLY`, SA `ftm-pr-builder`, no ignored files |
| Cloud Run revision labels | `ftm-build-time`, `commit-sha` | `ftm-build-time` = epoch seconds of the deploying build's createTime (R5 guard); `commit-sha` = short SHA (empty for manual deploys) |

## Deploy flow (per push to main)

```text
push to main ──(all files ignored?)── yes ──> no build
      │ no
      ▼
build image ─> push :BUILD_ID ─> guard: service ftm-build-time > mine? ── yes ──> skip (exit 0)
                                         │ no
                                         ▼
                                  gcloud run deploy (labels ftm-build-time, commit-sha)
any step fails ──> build FAILURE, GitHub check red, previous revision keeps serving
```
