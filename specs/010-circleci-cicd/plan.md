# Implementation Plan: CI/CD on CircleCI

**Branch**: `010-circleci-cicd` | **Date**: 2026-10-16 | **Spec**: [spec.md](spec.md)

## Summary

`.circleci/config.yml` has two jobs:
- **`build-check`** runs on every branch except `main`: `docker build` with remote Docker, and no Google access.
- **`deploy`** runs only on `main`, with context `ftm-language-generator-gcp`:
  1. a docs-only check, which stops the job if nothing else changed;
  2. sign in to Google Cloud with CircleCI's OIDC token through a workload identity pool, impersonating `ftm-deployer`;
  3. `gcloud builds submit --config cloudbuild.yaml --region=us-central1 --substitutions=_COMMIT_SHA=<sha7>`.

`cloudbuild.yaml` is unchanged apart from taking the commit SHA from `_COMMIT_SHA`. Then the spec 009 Cloud Build trigger setup is removed.

## Research / decisions

- **R1, CircleCI starts Cloud Build (not a pure-CircleCI build):** this reuses the proven deploy: the image push to `ftm`, the guard, the identical flags, and builds running inside the project. The alternative was building and pushing in CircleCI, then running `gcloud run deploy`. That would mean rewriting the guard, and pushing ~700 MB images from outside Google. Rejected.
- **R2, keyless sign-in:** a workload identity pool `circleci` with an OIDC provider `circleci-oidc`.
  - Issuer `https://oidc.circleci.com/org/<org id>`, audience `<org id>`.
  - Attribute mapping: `google.subject=assertion.sub` (the V1 token's sub, `org/…/project/…/user/…`, fits the 127-byte limit; the V2 token's longer sub doesn't), and `attribute.project_id=assertion['oidc.circleci.com/project-id']`.
  - Condition `attribute.project_id == '<project id>'`. `roles/iam.workloadIdentityUser` on `ftm-deployer` for that project's principalSet.
  - The job writes `$CIRCLE_OIDC_TOKEN` to a file and a credential config JSON (nothing in it is secret), then runs `gcloud auth login --cred-file`.
  - CircleCI only injects the token into jobs that use a **context**, hence `ftm-language-generator-gcp`. It's empty and can be restricted to the project.
  - The alternative, a service-account JSON key in a context, was rejected as a long-lived secret (constitution V).
- **R3, `ftm-deployer` now also *starts* builds:**
  - add `cloudbuild.builds.editor` (which replaces `builds.viewer`), `serviceusage.serviceUsageConsumer`, `iam.serviceAccountUser` on itself (the build runs as itself), and `storage.admin` on bucket `ftm-language-generator_cloudbuild` only (source upload; replaces `objectViewer`);
  - enable APIs `iamcredentials` and `sts`;
  - still no Secret Manager access.
- **R3a, implementation finding (2026-10-16):** the first CircleCI deploy failed with "forbidden from accessing the bucket [ftm-language-generator_cloudbuild]". With the *default* staging bucket, `gcloud builds submit` first checks bucket ownership by listing the project's buckets, which `ftm-deployer` (bucket-level access only) can't do. The job now passes `--gcs-source-staging-dir=gs://ftm-language-generator_cloudbuild/source`, which skips that check. This was reproduced and verified by impersonating `ftm-deployer`: the default bucket fails, the explicit dir succeeds. No broader storage permission is needed.
- **R4, docs-only skip:** `git diff --name-only HEAD^1 HEAD`. If every file matches `*.md`, `specs/`, `.specify/`, `.claude/` or `.github/`, the job halts with `circleci-agent step halt`, which counts as success. This is simpler than dynamic config with the path-filtering orb.
- **R5, ordering:**
  1. set up the CircleCI project and OIDC;
  2. open a rollout PR: `build-check` proves CircleCI runs;
  3. delete the Cloud Build deploy trigger, then merge, so CircleCI's `deploy` is the only one;
  4. clean up the rest.
- **R6, cleanup (FR-006):**
  - delete triggers `ftm-deploy-main` and `ftm-pr-check`;
  - delete the repository link and connection `ftm-github`;
  - the user uninstalls the "Google Cloud Build" GitHub App from `curiouslearning`;
  - delete SA `ftm-pr-builder` and its `logging.logWriter` binding;
  - remove the Cloud Build service agent's `secretmanager.admin` (only needed to create the connection);
  - remove the Compute default SA's `run.admin` and `actAs` on `ftm-generator-run` (only used for spec 005/007 manual deploys; manual deploys now run as `ftm-deployer`);
  - delete `cloudbuild-pr.yaml`.

## Constitution Check

| Principle | Status |
|---|---|
| I–IV pipeline behaviour | ✅ N/A: no app changes |
| V No secrets | ✅ No key in CircleCI or GitHub; the OIDC credential config contains no secret; the PR job has no access |
| Workflow: CLAUDE.md updated | ✅ |
| Manual verification | ✅ tasks T008–T010 |

## Project Structure

```text
.circleci/config.yml     # NEW
cloudbuild.yaml          # _COMMIT_SHA substitution; comments
cloudbuild-pr.yaml       # DELETED
README.md, CLAUDE.md     # CircleCI setup, one-time GCP setup, rollback
specs/009-…/spec.md      # Status: superseded
```

## Revision 2026-10-16: aligned with FeedTheMonsterJS, and clearer logs

- **Layout copied from `CuriousReader/FeedTheMonsterJS/.circleci/config.yml`:**
  - reusable `commands:` (`gcloud-login`, `build-and-deploy`, with parameters);
  - a `test` job on every branch;
  - `build-and-deploy-prod` on `main` with `requires: [test]` and `context:` as a list;
  - workflow `cloud-run-deploy-workflow`.

  There's only one environment here, so there are no dev/test deploy jobs.
- **Differences kept on purpose:**
  - no stored keys (OIDC instead of `aws-context` keys);
  - no orbs (the sign-in is plain `gcloud`; the deploy image is `google/cloud-sdk:slim` because it needs `gcloud`);
  - the test job is Python: `pip install`, `compileall`, `docker build`.
- **Logs:**
  - a failure ends with a ❌ line saying what failed (missing context, refused sign-in, build not started, failed Cloud Build step and its reason);
  - the deploy prints the full Cloud Build log (`ftm-deployer` gets `roles/logging.viewer`) and a console link.
  - **Trimmed (user request):** no parameters, artifacts, progress lines or result file. The test job doesn't run `pip install` separately, because `docker build` installs `requirements.txt` anyway.
