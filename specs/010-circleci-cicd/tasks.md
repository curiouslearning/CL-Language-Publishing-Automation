# Tasks: CI/CD on CircleCI

**Input**: [spec.md](spec.md), [plan.md](plan.md). **(user)** = needs the user (CircleCI dashboard, GitHub, merges). **(cloud)** = `gcloud` on `ftm-language-generator`.

## Phase 1: Setup

- [X] T001 Add `.circleci/config.yml` with:
  - `build-check` (`cimg/base:current`, `setup_remote_docker`, `docker build`), filtered to `ignore: main`;
  - `deploy` (`google/cloud-sdk:slim`, `main` only, context `ftm-language-generator-gcp`): the docs-only halt, then the OIDC credential config with `gcloud auth login --cred-file`, then `gcloud builds submit --config cloudbuild.yaml --region=us-central1 --substitutions=_COMMIT_SHA=${CIRCLE_SHA1:0:7}`.
- [X] T002 In `cloudbuild.yaml`: add the substitution `_COMMIT_SHA: ''`, use `commit-sha=${_COMMIT_SHA}`, and update the header comments. Delete `cloudbuild-pr.yaml`.
- [X] T003 (cloud) `ftm-deployer` can start builds:
  - added `roles/cloudbuild.builds.editor` (and removed `builds.viewer`) and `roles/serviceusage.serviceUsageConsumer`;
  - added `iam.serviceAccountUser` on itself;
  - `storage.admin` on `gs://ftm-language-generator_cloudbuild` replaces `objectViewer`;
  - enabled `iamcredentials` and `sts`;
  - created workload identity pool `circleci`.

## Phase 2: Foundational (needs the CircleCI IDs)

- [ ] T004 (user) In CircleCI, get the **organization ID** (Organization Settings → Overview) and, after setting up the project (T006), its **project ID** (Project Settings → Overview).
- [ ] T005 (cloud) Create OIDC provider `circleci-oidc` in pool `circleci`:
  - issuer `https://oidc.circleci.com/org/<org id>`, audience `<org id>`;
  - mapping `google.subject=assertion.sub,attribute.project_id=assertion['oidc.circleci.com/project-id']`;
  - condition `attribute.project_id=='<project id>'`.

  Then bind `roles/iam.workloadIdentityUser` on `ftm-deployer` to `principalSet://iam.googleapis.com/projects/838897084130/locations/global/workloadIdentityPools/circleci/attribute.project_id/<project id>`.
- [ ] T006 (user) In CircleCI:
  - set up project `CL-Language-Publishing-Automation`: "Set Up Project" → use the existing `.circleci/config.yml` from branch `010-circleci-cicd`;
  - create the context `ftm-language-generator-gcp` (Organization Settings → Contexts), empty, optionally restricted to this project.

## Phase 3: User Story 2 - PR build check (P1)

- [ ] T007 (user) With the user's go-ahead: commit and push branch `010-circleci-cicd`, then open a PR. CircleCI `build-check` shows on the PR and passes. Cloud Build's `ftm-pr-check` also runs until T011.

## Phase 4: User Story 1 - Deploy on merge via CircleCI (P1)

- [ ] T008 (cloud) Delete the Cloud Build trigger `ftm-deploy-main` **before** merging, so the merge deploys once (through CircleCI).
- [ ] T009 (user) Merge the PR when nobody is generating. Confirm:
  - CircleCI `deploy` succeeds;
  - the new revision is labeled `commit-sha=<merge sha7>`;
  - the page returns 200.
- [ ] T010 A docs-only merge (e.g. T013's docs) halts at "Only docs/specs changed", and the revision is unchanged.

## Phase 5: User Story 3 - Remove the Cloud Build automation (P2)

- [ ] T011 (cloud) Delete:
  - trigger `ftm-pr-check`;
  - repository link `cl-language-publishing-automation` and connection `ftm-github`;
  - SA `ftm-pr-builder`, plus its project `logging.logWriter` binding.

  Remove:
  - the Cloud Build service agent's `roles/secretmanager.admin`;
  - the Compute default SA's `roles/run.admin` and its `iam.serviceAccountUser` on `ftm-generator-run`.
- [ ] T012 (user) GitHub → `curiouslearning` org Settings → GitHub Apps → **Google Cloud Build** → Uninstall, or remove this repo from it if other repos use it.
- [ ] T013 Mark spec 010 Implemented. In GitHub branch protection for `main`, switch the required check from `ftm-pr-check` to CircleCI's `build-check`, if one was set (needs a repo admin).
