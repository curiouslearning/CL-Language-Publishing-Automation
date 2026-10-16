# Tasks: Gemini Key for the Hosted Generator

**Input**: Design documents from `specs/007-gemini-key-cloud-run/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/deploy-and-key.md, quickstart.md

**Tests**: no automated tests (constitution: no test suite). Verification is manual, per [quickstart.md](quickstart.md).

**Organization**: tasks are grouped by user story.

- Tasks marked **(cloud)** run `gcloud` against `ftm-language-generator`. They need an Owner-level account, and a POSIX shell (Git Bash) for the pipes.
- Never print, echo, paste into a file, or commit the key value.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 = AI check works hosted, US2 = key kept secret, US3 = documented setup/rotation

---

## Phase 1: Setup

- [X] T001 (cloud) Confirm prerequisites before any change:
  - `gcloud config get-value account` is an Owner on `ftm-language-generator`;
  - `gcloud iam service-accounts describe ftm-generator-run@ftm-language-generator.iam.gserviceaccount.com --project=ftm-language-generator` succeeds;
  - `gcloud secrets describe ftm-oauth-web-client --project=ftm-language-generator` succeeds (spec 005 setup done, README "Deploy to Cloud Run").

  Stop and report if any is missing.

---

## Phase 2: Foundational (blocks US1 and US2)

**Purpose**: the cloud resources from [data-model.md](data-model.md) must exist before the deploy can attach the key.

- [X] T002 (cloud) Enable the APIs (research R4): `gcloud services enable generativelanguage.googleapis.com apikeys.googleapis.com secretmanager.googleapis.com --project=ftm-language-generator`.
- [X] T003 (cloud) Create the production key, restricted to "`generativelanguage.googleapis.com` only" (research R3):

  ```bash
  gcloud services api-keys create --display-name="FTM generator (Cloud Run)" --api-target=service=generativelanguage.googleapis.com --project=ftm-language-generator
  ```

  Then confirm the restriction with `gcloud services api-keys list --project=ftm-language-generator --format="table(name,displayName,restrictions.apiTargets)"`. Record only the key's resource **name** (not its string) for T004.
- [X] T004 (cloud) Store the key as secret `ftm-gemini-api-key` without exposing it. It must hold "exactly the key string (no newline)":

  ```bash
  gcloud services api-keys get-key-string <KEY_NAME> --project=ftm-language-generator --format="value(keyString)" | tr -d '\r\n' | gcloud secrets create ftm-gemini-api-key --data-file=- --replication-policy=automatic --project=ftm-language-generator
  ```

  Verify that `gcloud secrets versions list ftm-gemini-api-key --project=ftm-language-generator` shows version 1 enabled.
- [X] T005 (cloud) Grant read access to the runtime SA only (research R5):

  ```bash
  gcloud secrets add-iam-policy-binding ftm-gemini-api-key --member=serviceAccount:ftm-generator-run@ftm-language-generator.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --project=ftm-language-generator
  ```

  Do **not** grant the Cloud Build SA.

**Checkpoint**: quickstart V1 passes.

---

## Phase 3: User Story 1 - AI check works on the hosted page (P1) 🎯 MVP

**Goal**: a signed-in user on the Cloud Run page gets a real AI review.

**Independent Test**: quickstart V2 + V3.

- [X] T006 [US1] In `cloudbuild.yaml`, deploy step:
  - change the `--set-secrets` line to `--set-secrets=/secrets/client_secret_web.json=ftm-oauth-web-client:latest,GEMINI_API_KEY=ftm-gemini-api-key:latest` ([contracts/deploy-and-key.md](contracts/deploy-and-key.md));
  - replace the comment "No AI key is attached yet: ... shows "not configured"" with one saying the Gemini key comes from secret `ftm-gemini-api-key` as env var `GEMINI_API_KEY` (resolved at instance start; rotate = new version + redeploy);
  - keep the key out of `--set-env-vars`.
- [X] T007 [P] [US1] In `language_automation/ai_providers.py` `load_config()`:
  - strip each API key: `cfg[name]["api_key"] = (os.environ.get(env) or env_file.get(env, "")).strip()`, so an all-whitespace key counts as missing (research R6);
  - when `os.environ.get("FTM_HOSTED") == "1"` and the chosen provider's key is missing, return the reason `no API key configured for <provider>: the Cloud Run service has no <ENV_KEY> secret attached (README "Deploy to Cloud Run")`;
  - otherwise keep the existing `.env` reason text unchanged.
- [X] T008 [P] [US1] In `language_automation/app.py` (the AI check caption, about line 790), append "See `.env.example`." to `Not configured: <reason>.` only when `os.environ.get("FTM_HOSTED") != "1"`. Leave all other AI section output unchanged.
- [X] T009 [US1] (cloud) Deploy with `gcloud builds submit --config cloudbuild.yaml --project=ftm-language-generator` (depends on T002–T008). Then confirm with `gcloud run services describe ftm-language-generator --region=us-central1 --project=ftm-language-generator` that `GEMINI_API_KEY` is sourced from secret `ftm-gemini-api-key` (quickstart V2).
- [ ] T010 [US1] Manual verification, quickstart V3:
  - on the hosted page, with the AI check and "Show tokens used" on, generate a real language (e.g. `Hindi`);
  - confirm the pipeline summary, the AI review with model + non-zero tokens, and "Download AI log";
  - also confirm that with the AI check off, nothing is sent.

**Checkpoint**: MVP: the hosted AI check works.

---

## Phase 4: User Story 2 - The key is kept secret and owned by the project (P1)

**Goal**: the key exists only in Secret Manager, restricted, readable only by the runtime SA.

**Independent Test**: quickstart V4 (and the IAM part of V1).

- [X] T011 [US2] Verify there's no exposure:
  - `git grep -n "AIza"` returns nothing;
  - `.dockerignore` still excludes `language_automation/.env` and `language_automation/.env.*`;
  - `.gcloudignore` still contains `#!include:.gitignore`;
  - `.gitignore` still excludes `.env`.

  Change nothing unless something regressed (FR-011).
- [X] T012 [US2] (cloud) Verify access and restriction:
  - `gcloud secrets get-iam-policy ftm-gemini-api-key --project=ftm-language-generator` lists only `ftm-generator-run` as `secretAccessor`;
  - from a throwaway shell, a call to another Google API with the key is refused (`API_KEY_SERVICE_BLOCKED`), per quickstart V4. Don't save the key or its output.
- [X] T013 [P] [US2] Update the `language_automation/.env.example` header comment: these keys are for **local** runs only; on Cloud Run, `GEMINI_API_KEY` comes from Secret Manager secret `ftm-gemini-api-key`, and no key goes in the image.

---

## Phase 5: User Story 3 - One documented setup and deploy (P2)

**Goal**: a maintainer can do setup, deploy and rotation from the README alone.

**Independent Test**: a maintainer who didn't build this follows the README only (quickstart V6 for rotation).

- [X] T014 [US3] In `README.md`, "Deploy to Cloud Run", one-time setup block:
  - add the T002–T005 commands, under a `# Gemini API key for the AI check (spec 007)` heading;
  - change the runtime SA comment to "it can only read the two secrets", which now really are two: OAuth client + Gemini key;
  - add a note that the key is billed at paid-tier rates because the project has billing, and an optional budget alert (research R7).
- [X] T015 [US3] In `README.md`, add a "Rotate the Gemini key" subsection:
  - create a new restricted key (T003 command);
  - `... get-key-string ... | tr -d '\r\n' | gcloud secrets versions add ftm-gemini-api-key --data-file=-`;
  - redeploy, or `gcloud run services update ftm-language-generator --region=us-central1 --update-secrets=GEMINI_API_KEY=ftm-gemini-api-key:latest --project=ftm-language-generator`;
  - then `gcloud secrets versions disable <old> ...` and `gcloud services api-keys delete <old key name> ...`.
- [X] T016 [US3] In `README.md`:
  - replace "The Cloud Run deploy doesn't attach any AI key until the provider is decided." (setup step 4) and the "No AI key is attached until the provider is decided." sentence in "Secrets" with: the hosted page uses Gemini with the project's key from Secret Manager (`ftm-gemini-api-key`); local runs use your own key in `.env`;
  - update the `specs/` row in the layout table to "(001–007)".
- [X] T017 [P] [US3] Run quickstart V6 (rotation) once, or at least dry-read it against the README text, and fix any mismatch in `README.md`.

---

## Phase 6: Polish & Cross-Cutting

- [X] T018 [P] Update `CLAUDE.md`:
  - **spec list**: add `007-gemini-key-cloud-run`: Gemini key for the hosted page (Secret Manager → `GEMINI_API_KEY`);
  - **Hosting**: replace "no AI key is attached until the provider, Gemini or Claude, is decided" with the `ftm-gemini-api-key` secret attached as env var `GEMINI_API_KEY`, readable only by `ftm-generator-run`;
  - **local testing paragraph**: replace "The project's Gemini key isn't used anywhere" with "the project's restricted key is used only by Cloud Run";
  - **AI check Config / `.env`**: note keys are whitespace-stripped and the hosted "not configured" reason names the secret.
- [X] T019 [P] Update the `Dockerfile` header comment so it matches: the web OAuth client is mounted as a file, and the Gemini key is set as env var `GEMINI_API_KEY`, both from Secret Manager at run time.
- [X] T020 Run quickstart V5 locally:
  - with `FTM_HOSTED=1` and no `GEMINI_API_KEY`, the caption shows the hosted reason without `.env.example`;
  - `python ai_language_check.py Hindi` reports `unavailable`;
  - with `FTM_HOSTED` unset and the personal key in `language_automation/.env`, the AI check works as before.
- [ ] T021 Mark the spec Status "Implemented" in `specs/007-gemini-key-cloud-run/spec.md` and tick the tasks completed here.

---

## Dependencies & Execution Order

- **T001** → **T002 → T003 → T004 → T005** (sequential: each needs the previous resource).
- **T006, T007, T008** need no cloud resources and can start any time (T007, T008 [P]; T006 touches only `cloudbuild.yaml`).
- **T009 (deploy)** needs T002–T008. Deploying before T005 fails (research R5).
- **T010** needs T009. **US2** verification (T011–T012) needs T004–T005 (T012 also needs T009 for the service view). **US3** docs (T014–T016) can be written in parallel with US1 code, but are validated after T009.
- **Polish** last, except T018/T019, which can be written any time.

### Parallel opportunities

- T007 ∥ T008 ∥ T013 ∥ T018 ∥ T019 (different files).
- Docs (T014–T016, same file `README.md`, so sequential among themselves) ∥ code (T006–T008).

### Parallel example: User Story 1

```text
T007 ai_providers.py: strip keys + hosted reason
T008 app.py: hosted caption
(T006 cloudbuild.yaml alongside: different file)
```

## Implementation Strategy

1. **MVP** = Phases 1–3: cloud resources + deploy wiring + hosted verification. The AI check works on Cloud Run.
2. Then US2: confirm secrecy and restriction (mostly verification, no new resources).
3. Then US3 + Polish: README/CLAUDE.md so the next maintainer can repeat and rotate.
4. Don't deploy while someone is running a language (README note): the new revision replaces the running one.
