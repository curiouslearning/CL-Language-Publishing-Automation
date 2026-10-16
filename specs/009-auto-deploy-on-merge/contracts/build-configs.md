# Contract: Build configurations and triggers

## `cloudbuild.yaml` (deploy: trigger `ftm-deploy-main` and manual `gcloud builds submit`)

Changes to today's file:

| Item | Value |
|---|---|
| top-level `serviceAccount` | `projects/${PROJECT_ID}/serviceAccounts/ftm-deployer@${PROJECT_ID}.iam.gserviceaccount.com` |
| build / push steps | unchanged (`:${BUILD_ID}` and `:latest` tags) |
| deploy step | `entrypoint: bash`, running the guard and then the existing `gcloud run deploy` with all current flags, plus `--update-labels=ftm-build-time=<epoch>,commit-sha=${SHORT_SHA}` |
| guard output | `⏭️ Skipping deploy: a newer build (<t>) is already live` and exit 0, when the service label is greater than this build's createTime |

Every existing flag stays the same: region, runtime SA, `--allow-unauthenticated`, 1 instance, `--cpu`, `--memory`, `--timeout`, `--session-affinity`, env vars, and secrets including `GEMINI_API_KEY`.

## `cloudbuild-pr.yaml` (new; trigger `ftm-pr-check`)

| Item | Value |
|---|---|
| `serviceAccount` | `projects/${PROJECT_ID}/serviceAccounts/ftm-pr-builder@${PROJECT_ID}.iam.gserviceaccount.com` |
| steps | one: `gcr.io/cloud-builders/docker build -t ftm-pr-check:${SHORT_SHA} .` |
| images / artifacts | none (nothing pushed) |
| options | `logging: CLOUD_LOGGING_ONLY` |

Outcome: SUCCESS = the image builds (Dockerfile valid, `pip install -r requirements.txt` succeeds, the code is copied). No deploy, no secrets.

## GitHub-visible behaviour

| Event | GitHub shows |
|---|---|
| PR opened / updated (org member) | check `ftm-pr-check` pending → success / failure, "Details" links to the log |
| PR from an outside contributor | no build until a maintainer comments `/gcbrun` |
| push to `main` touching code | check `ftm-deploy-main` on the commit: pending → success / failure |
| push to `main` touching only ignored files | no check for `ftm-deploy-main` |
