# Research: Automatic Deploy on Merge

Checked against Google Cloud SDK 588 (`gcloud builds connections`, `gcloud builds triggers create github`) and the current project state: no connections, no triggers, and builds run as the Compute Engine default SA, which has `roles/editor`.

## R0. No new repositories (user decision, 2026-10-15)

- **Source**: the existing GitHub repo `curiouslearning/CL-Language-Publishing-Automation`. Nothing new is created on GitHub. `gcloud builds repositories create` below only **links** that existing repo to Cloud Build (a pointer resource in Google Cloud), and doesn't create a repository.
- **Images**: the existing Artifact Registry repository `ftm` (`us-central1-docker.pkg.dev/ftm-language-generator/ftm`, created in the spec 007 setup). No new registry. (Container Registry / `gcr.io` is deprecated; Artifact Registry is its replacement and is already in use.)
- **Target**: any code change merged to `main` builds from this repo and deploys to the existing Cloud Run service `ftm-language-generator`.

## R1. How Cloud Build connects to GitHub

- **Decision**: a **2nd-generation repository connection**:
  - `gcloud builds connections create github ftm-github --region=us-central1`;
  - `gcloud builds repositories create cl-language-publishing-automation --connection=ftm-github --remote-uri=https://github.com/curiouslearning/CL-Language-Publishing-Automation.git --region=us-central1`.
- **How it's authorized**: the create command prints a link. The person who opens it signs in to GitHub, authorizes Cloud Build, and **installs the "Google Cloud Build" GitHub App** on the `curiouslearning` organization, limited to this one repository. Installing an app on an org needs an **org owner**, or an owner's approval of a member's request.
- **Credentials**: Cloud Build stores the GitHub OAuth token in this project's Secret Manager, as a secret it creates. Nothing is stored in GitHub (FR-006).
- **Status on GitHub**: builds from a GitHub App connection report **check runs** on the commit / PR automatically, with a "Details" link to the build log (FR-003, FR-004).
- **Alternatives**:
  - 1st-gen GitHub App triggers: global, being superseded.
  - Mirroring the repo into Cloud Source Repositories: deprecated.
  - GitHub Actions with Workload Identity Federation: rejected by the user.

## R2. Triggers

- **Deploy trigger** `ftm-deploy-main`:
  - `--branch-pattern='^main$'`, `--build-config=cloudbuild.yaml`;
  - `--ignored-files` = `**/*.md`, `specs/**`, `.specify/**`, `.claude/**`, `.github/**` (FR-002). Cloud Build skips the build only when **every** changed file matches.
  - `--include-logs-with-status`, so the GitHub check links to the logs.
  - `--service-account` = `ftm-deployer` (R4).
- **PR trigger** `ftm-pr-check`:
  - `--pull-request-pattern='^main$'`, `--build-config=cloudbuild-pr.yaml`;
  - `--comment-control=COMMENTS_ENABLED_FOR_EXTERNAL_CONTRIBUTORS_ONLY`: org members' PRs build automatically, and outside contributors' PRs need a maintainer's `/gcbrun` comment (FR-005);
  - `--service-account` = `ftm-pr-builder` (R4).
  - **No ignored files**, so the check always reports. A docs-only PR then still gets a (quick, harmless) check, and branch protection can require the check without blocking docs PRs forever (spec US2-4 allows "trivially passing").
- **Region**: `us-central1`, the same as the connection, the service and Artifact Registry.

## R3. Build configurations

- **`cloudbuild.yaml`** (deploy; kept, also used for manual deploys):
  - add `serviceAccount: projects/$PROJECT_ID/serviceAccounts/ftm-deployer@$PROJECT_ID.iam.gserviceaccount.com`, so manual and automatic deploys run with the same least-privilege identity. `logging: CLOUD_LOGGING_ONLY` is already set, which a custom SA needs.
  - The deploy step gets the "newest wins" guard (R5).
  - A `commit-sha=${SHORT_SHA}` revision label (empty for manual deploys) makes it visible which commit is live.
- **`cloudbuild-pr.yaml`** (new, check only):
  - one step, `docker build -t ftm-pr-check:${SHORT_SHA} .`;
  - no push, no deploy, no secrets, and `serviceAccount: ftm-pr-builder`.

  A failed `pip install` or Dockerfile error fails the check.

## R4. Identities (least privilege, FR-009)

| SA | Used by | Roles |
|---|---|---|
| `ftm-deployer` | deploy trigger + manual `gcloud builds submit` | `roles/run.admin` (project; needed because the deploy sets `--allow-unauthenticated`), `roles/iam.serviceAccountUser` **on `ftm-generator-run` only**, `roles/artifactregistry.writer` **on repo `ftm` only**, `roles/logging.logWriter`, `roles/cloudbuild.builds.viewer` (for the R5 guard) |
| `ftm-pr-builder` | PR trigger | `roles/logging.logWriter` only |

- **Implementation finding:** manual `gcloud builds submit` also needs `ftm-deployer` to read the uploaded source, so it has `roles/storage.objectViewer` **on bucket `gs://ftm-language-generator_cloudbuild` only**. Triggered builds fetch from GitHub and don't use it. The first manual deploy (revision 00003) confirmed that the deployer needs **no** Secret Manager role.
- Neither can read secret values: there's no `secretAccessor`. Cloud Run checks secret access as the **runtime** SA (`ftm-generator-run`) when the revision starts, so the deployer doesn't need it. To be confirmed by the first trigger run (quickstart V2); if the deploy is refused, grant `roles/secretmanager.viewer` (metadata only, not values) on the two secrets.
- People running manual deploys need `iam.serviceAccountUser` on `ftm-deployer` (Owners have it).
- The broad grants to the Compute default SA from the spec 005 setup (`run.admin`, `actAs ftm-generator-run`) are no longer needed. They're removed in the polish phase, after the trigger has been proven.

## R5. Overlapping deploys: the newest commit wins (FR-008)

- **Problem**: Cloud Build runs triggered builds concurrently. If merge B lands while A is still building, A could finish last and roll the service back to older code.
- **Decision**:
  - The deploy step (cloud-sdk image, `bash`) reads its own build's `createTime` (`gcloud builds describe $BUILD_ID --region=us-central1`) as epoch seconds.
  - It reads the service's current label `ftm-build-time` (`gcloud run services describe … --format='value(spec.template.metadata.labels.ftm-build-time)'`).
  - If the service already runs a build created **later**, it prints `⏭️ Skipping deploy: a newer build is already live` and exits 0.
  - Otherwise it deploys with `--update-labels=ftm-build-time=<epoch>,commit-sha=${SHORT_SHA}`.
- **Why createTime**: builds are created in push order, so a later merge always has a later create time.
- **Residual race**: two deploys could pass the check within the same seconds. The window is tiny and the next merge corrects it. Accepted.
- **Alternatives**:
  - Cloud Build has no queue/concurrency setting for triggers.
  - Approval gates (`--require-approval`) would defeat "merge = deploy".
  - Pinning the image by digest doesn't solve ordering.

## R6. Committing the deploy files (FR-011)

- `Dockerfile`, `cloudbuild.yaml`, `.dockerignore` and `.gcloudignore` are untracked today, and `main` on GitHub doesn't have them. They, the spec 007/008 code and docs, and this feature's files must reach `main` through a PR **before** the deploy trigger is created. Otherwise the first trigger run fails, because `cloudbuild.yaml` isn't found.
- Order: commit everything on a branch → open a PR → create the connection + PR trigger (that PR then gets its first check) → merge → create the deploy trigger → push a trivial change to prove it. Or create the deploy trigger before merging, so the merge itself is the first automatic deploy.
- `.gitignore` already excludes every secret file (constitution V). Check `git status` before committing: no `client_secret*`, `token.json`, `.env` or `lang/`.

## R7. Rollback and manual deploys

- **Rollback**: `gcloud run services update-traffic ftm-language-generator --to-revisions=<previous>=100 --region=us-central1`. The next merge then deploys again and moves traffic to the new revision, since `gcloud run deploy` defaults to sending all traffic to the latest.
- **Redeploy a commit by hand**: `gcloud builds triggers run ftm-deploy-main --branch=main --region=us-central1` (current tip), or `--sha=<commit>`. The R5 guard skips an *older* commit unless the label is cleared, which is documented for emergencies.
- **Manual `gcloud builds submit`** still works (now as `ftm-deployer`). README warns that it deploys local, possibly uncommitted, files, and the next merge replaces it.
