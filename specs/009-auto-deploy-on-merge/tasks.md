# Tasks: Automatic Deploy on Merge

**Input**: Design documents from `specs/009-auto-deploy-on-merge/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/build-configs.md, quickstart.md

**Tests**: no automated suite. Verification uses real PRs and merges (quickstart V1–V7).

**Ground rules**:
- **No new repositories** (research R0). Use the existing GitHub repo `curiouslearning/CL-Language-Publishing-Automation`, the existing Artifact Registry repo `ftm` and the existing Cloud Run service `ftm-language-generator`.
- Tasks marked **(cloud)** run `gcloud` against `ftm-language-generator` and need an Owner. **(github)** tasks need a `curiouslearning` org owner. **(user)** tasks need the user's explicit go-ahead (commits, pushes, PRs, merges).

**Phase order note**: US2 (PR check) comes before US1 here, because the rollout PR should get its check **before** it's merged, and that merge is US1's first automatic deploy.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 (cloud) Confirm the starting state:
  - `gcloud artifacts repositories describe ftm --location=us-central1 --project=ftm-language-generator` exists (reused, R0);
  - `gcloud run services describe ftm-language-generator --region=us-central1 --project=ftm-language-generator` exists;
  - `gcloud builds connections list --region=us-central1 --project=ftm-language-generator` and `gcloud builds triggers list --region=us-central1 --project=ftm-language-generator` are empty;
  - `git remote get-url origin` is `https://github.com/curiouslearning/CL-Language-Publishing-Automation.git`.
- [X] T002 Secret check before anything is committed (constitution V): `git status --porcelain --ignored` shows `client_secret*.json`, `credentials.json`, `token.json`, `.env`, `lang/`, `.ai_cache/` only as **ignored** (`!!`), never as untracked or staged. `git grep -nE "AIza|BEGIN PRIVATE KEY"` returns nothing.

---

## Phase 2: Foundational (blocks all stories)

- [X] T003 (cloud) Create the deploy identity `ftm-deployer` with the research R4 roles only:
  - `gcloud iam service-accounts create ftm-deployer --display-name="FTM deploy (Cloud Build)"`;
  - project roles `roles/run.admin`, `roles/logging.logWriter`, `roles/cloudbuild.builds.viewer`;
  - `roles/iam.serviceAccountUser` **on `ftm-generator-run` only** (`gcloud iam service-accounts add-iam-policy-binding ftm-generator-run@…`);
  - `roles/artifactregistry.writer` **on repo `ftm` only** (`gcloud artifacts repositories add-iam-policy-binding ftm --location=us-central1 …`).

  No Secret Manager role.
- [X] T004 [P] (cloud) Create the PR identity `ftm-pr-builder` with **only** `roles/logging.logWriter` on the project.
- [X] T005 [P] In `cloudbuild.yaml`, per contracts/build-configs.md:
  - add top-level `serviceAccount: projects/${PROJECT_ID}/serviceAccounts/ftm-deployer@${PROJECT_ID}.iam.gserviceaccount.com`;
  - convert the `deploy` step to `entrypoint: bash` with `args: ["-c", <script>]`. The script:
    - (a) gets `BUILT=$(date -d "$(gcloud builds describe $BUILD_ID --region=us-central1 --format='value(createTime)')" +%s)`;
    - (b) gets `LIVE=$(gcloud run services describe ${_SERVICE} --region=${_REGION} --format='value(spec.template.metadata.labels.ftm-build-time)' 2>/dev/null || true)`;
    - (c) if `LIVE` is non-empty and `LIVE > BUILT`, prints `⏭️ Skipping deploy: a newer build ($LIVE) is already live` and exits 0;
    - (d) otherwise runs the existing `gcloud run deploy` with **every current flag unchanged**, plus `--update-labels=ftm-build-time=$BUILT,commit-sha=${SHORT_SHA}`.
  - Escape `$` as `$$` for bash variables, so Cloud Build doesn't substitute them.
  - Keep the build and push steps and all substitutions as they are.
  - Update the header comment: the file is run automatically on merge to `main` (spec 009) and by manual `gcloud builds submit`.
- [X] T006 [P] Create `cloudbuild-pr.yaml` at the repo root, per contracts/build-configs.md:
  - `serviceAccount: projects/${PROJECT_ID}/serviceAccounts/ftm-pr-builder@${PROJECT_ID}.iam.gserviceaccount.com`;
  - `options: {logging: CLOUD_LOGGING_ONLY}`;
  - one step `gcr.io/cloud-builders/docker` with args `["build", "-t", "ftm-pr-check:${SHORT_SHA}", "."]`;
  - no `images:`, no push, no deploy;
  - a header comment explaining it's the PR check (spec 009).
- [X] T007 Validate both YAML files parse (`python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ('cloudbuild.yaml','cloudbuild-pr.yaml')]"`). Then run one manual deploy with `gcloud builds submit --config cloudbuild.yaml --project=ftm-language-generator` (only while nobody is generating), which proves:
  - `ftm-deployer` has enough permission (no secret role needed, R4; if refused, grant `roles/secretmanager.viewer` on the two secrets and note it in research R4);
  - the guard works (first run: no label yet → deploys and sets `ftm-build-time`).
- [X] T008 (cloud + github) Create the connection: `gcloud builds connections create github ftm-github --region=us-central1 --project=ftm-language-generator`. Open the printed link, authorize, and have a **`curiouslearning` org owner install "Google Cloud Build" on the org with access to only `CL-Language-Publishing-Automation`**. Then `gcloud builds connections describe ftm-github --region=us-central1 --project=ftm-language-generator --format="value(installationState.stage)"` must say `COMPLETE`.
- [X] T009 (cloud) Link the **existing** repo (this creates no repository, R0): `gcloud builds repositories create cl-language-publishing-automation --connection=ftm-github --remote-uri=https://github.com/curiouslearning/CL-Language-Publishing-Automation.git --region=us-central1 --project=ftm-language-generator`.
- [X] T010 (user) With the user's go-ahead:
  - create branch `009-auto-deploy-on-merge` from `main`;
  - commit the currently untracked/modified work: `Dockerfile`, `.dockerignore`, `.gcloudignore`, `cloudbuild.yaml`, `cloudbuild-pr.yaml`, the specs 007–009 folders, `language_automation/` changes (`ai_providers.py`, `app.py`, `package_store.py`, `.env.example`, `check_access.py`), `README.md`, `CLAUDE.md`, `requirements.txt`, `.specify/memory/constitution.md` and the spec 003 edits;
  - re-run T002 on the staged set first;
  - push and open a PR into `main`. Commit message and PR body end with the attribution lines.

**Checkpoint**: identities, configs, connection and link exist, and the rollout PR is open (not merged).

---

## Phase 3: User Story 2 - Pull requests are checked before merging (P1)

**Goal**: every PR into `main` gets a build-only check on GitHub. No deploy, no secrets.

**Independent Test**: quickstart V2.

- [X] T011 [US2] (cloud) Create the PR trigger:

  ```bash
  gcloud builds triggers create github --name=ftm-pr-check --region=us-central1 --project=ftm-language-generator \
    --repository=projects/ftm-language-generator/locations/us-central1/connections/ftm-github/repositories/cl-language-publishing-automation \
    --pull-request-pattern='^main$' --build-config=cloudbuild-pr.yaml \
    --comment-control=COMMENTS_ENABLED_FOR_EXTERNAL_CONTRIBUTORS_ONLY --include-logs-with-status \
    --service-account=projects/ftm-language-generator/serviceAccounts/ftm-pr-builder@ftm-language-generator.iam.gserviceaccount.com
  ```

  **No ignored files** on this trigger (research R2).
- [X] T012 [US2] Trigger the check on the open rollout PR: push an empty commit after the user's go-ahead, or comment `/gcbrun`. Confirm:
  - the PR shows `ftm-pr-check` → success with a "Details" log link;
  - the log has only the docker build;
  - `gcloud run services describe ftm-language-generator --region=us-central1 --project=ftm-language-generator --format="value(status.latestReadyRevisionName)"` is unchanged.
- [ ] T013 [US2] Negative check (quickstart V2): with the user's go-ahead, push a commit to the PR adding `nonexistent-package-xyz==1.0` to `requirements.txt`. The check fails. Revert it, and the check passes again.

---

## Phase 4: User Story 1 - Merging a PR deploys it (P1) 🎯 MVP

**Goal**: any code change merged to `main` deploys to the existing Cloud Run service automatically.

**Independent Test**: quickstart V3 (merge → live), V4 (docs-only → no deploy), V5 (newest wins).

- [X] T014 [US1] (cloud) Create the deploy trigger:

  ```bash
  gcloud builds triggers create github --name=ftm-deploy-main --region=us-central1 --project=ftm-language-generator \
    --repository=projects/ftm-language-generator/locations/us-central1/connections/ftm-github/repositories/cl-language-publishing-automation \
    --branch-pattern='^main$' --build-config=cloudbuild.yaml --include-logs-with-status \
    --ignored-files='**/*.md,specs/**,.specify/**,.claude/**,.github/**' \
    --service-account=projects/ftm-language-generator/serviceAccounts/ftm-deployer@ftm-language-generator.iam.gserviceaccount.com
  ```

- [X] T015 [US1] (user) Merge the rollout PR, once the user confirms nobody is generating a language. Confirm (quickstart V3):
  - `ftm-deploy-main` starts within 1 minute and shows on the merge commit;
  - it succeeds within ~10 minutes;
  - the new revision carries `commit-sha=<merge short SHA>`;
  - the page returns HTTP 200.
- [ ] T016 [US1] Quickstart V5, newest wins: run `gcloud builds triggers run ftm-deploy-main --branch=main --region=us-central1 --project=ftm-language-generator` twice in quick succession. The later-created build is the live one (`ftm-build-time` label). If the earlier build finishes last, its log shows `⏭️ Skipping deploy`.

**Checkpoint**: MVP: merges deploy automatically.

---

## Phase 5: User Story 3 - A failed deploy is safe and visible (P2)

**Goal**: failures keep the old version serving; rollback in under 5 minutes.

**Independent Test**: quickstart V6.

- [ ] T017 [US3] Verify safety: in the Cloud Build history, a failed build (e.g. T013's failed PR check, or a deliberately failing `gcloud builds triggers run` on a test branch pattern) never changes `latestReadyRevisionName`. Then rehearse rollback:
  1. `gcloud run services update-traffic ftm-language-generator --to-revisions=<previous revision>=100 --region=us-central1 --project=ftm-language-generator`;
  2. confirm the page is served by the previous revision;
  3. restore with `--to-latest`.

  Time it: under 5 minutes.

---

## Phase 6: Polish & Cross-Cutting (lands as a docs-only PR, which also proves FR-002)

- [ ] T018 [P] Update `README.md` "Deploy to Cloud Run":
  - **How deploys happen now:** merge to `main` → automatic, docs-only merges skipped. Where to see status: the GitHub commit/PR checks and Cloud Build history.
  - **One-time automatic-deploy setup:** the T003/T004/T008/T009/T011/T014 commands, stating that no new repositories are created.
  - **Manual deploy:** still `gcloud builds submit` (now as `ftm-deployer`), with a warning that it uploads local, possibly uncommitted files and that the next merge replaces it.
  - **Redeploy:** `gcloud builds triggers run ftm-deploy-main --branch=main`.
  - **Rollback:** the `update-traffic` command, plus how to clear the `ftm-build-time` label to force an older commit.
  - **Notes:** "Merge code changes when nobody is generating a language". Recommend a repo admin require the `ftm-pr-check` check in branch protection for `main`.
- [ ] T019 [P] Update `CLAUDE.md`:
  - **Hosting section:** automatic deploys (triggers `ftm-deploy-main` / `ftm-pr-check`, connection `ftm-github`), identities `ftm-deployer` / `ftm-pr-builder` and their limits, the newest-wins guard (`ftm-build-time` label), the docs-only skip, and no new repositories;
  - **Spec list:** add `009-auto-deploy-on-merge`.
- [ ] T020 (user) With the user's go-ahead, commit T018–T019 on a branch, open a PR and merge it. This is a docs-only change, so quickstart V4 applies: the PR still gets `ftm-pr-check`, but **no** `ftm-deploy-main` build runs after the merge, and the live revision is unchanged.
- [ ] T021 (cloud) Remove the now-unneeded broad grants to the Compute default SA from the spec 005 setup (research R4):
  - `gcloud projects remove-iam-policy-binding ftm-language-generator --member=serviceAccount:838897084130-compute@developer.gserviceaccount.com --role=roles/run.admin`;
  - `gcloud iam service-accounts remove-iam-policy-binding ftm-generator-run@ftm-language-generator.iam.gserviceaccount.com --member=serviceAccount:838897084130-compute@developer.gserviceaccount.com --role=roles/iam.serviceAccountUser --project=ftm-language-generator`.

  Leave its default Editor role alone (project-wide policy, out of scope). Update the README's one-time setup block to match.
- [ ] T022 Quickstart V7: no credentials in GitHub (repo Settings → Secrets is empty for this; `git grep` clean on `main`). Then set Status "Implemented" in `specs/009-auto-deploy-on-merge/spec.md` and tick tasks here.

---

## Dependencies & Execution Order

- T001 → T002 → {T003, T004, T005, T006} → T007 (needs T003 + T005) → T008 → T009 → T010.
- **US2**: T011 (needs T004, T006, T009) → T012 (needs T010's PR) → T013.
- **US1**: T014 (needs T003, T005, T009) → T015 (merge; ideally after T012/T013 are green) → T016.
- **US3**: T017 after T015.
- **Polish**: T018 ∥ T019 → T020 (docs-only PR). T021 after T015 + T016 have proven `ftm-deployer`. T022 last.

### Parallel opportunities

- T004 ∥ T005 ∥ T006 (different resources/files) once T003 has started.
- T018 ∥ T019 (different docs).

### Parallel example: Foundational

```text
T004 create ftm-pr-builder (cloud)
T005 edit cloudbuild.yaml
T006 create cloudbuild-pr.yaml
```

## Implementation Strategy

1. Phases 1–2: identities, configs (proven by one manual deploy), connection, link, rollout PR.
2. US2: the PR check runs on the rollout PR itself.
3. **MVP = US1**: create the deploy trigger, merge the rollout PR, and that's the first automatic deploy.
4. US3: rehearse safety and rollback.
5. Polish via a docs-only PR, which doubles as the "docs don't deploy" test. Then tighten IAM.
6. Every merge (T015, T020) waits for the user's confirmation that nobody is generating a language.
