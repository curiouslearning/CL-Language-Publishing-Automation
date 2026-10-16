# Feature Specification: Automatic Deploy on Merge

**Feature Branch**: `009-auto-deploy-on-merge`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "Automatic deploy on merge: whenever a PR is merged into main on GitHub (curiouslearning/CL-Language-Publishing-Automation), the generator is built and deployed to Cloud Run (ftm-language-generator, us-central1) automatically using a Cloud Build GitHub trigger that runs the existing cloudbuild.yaml. Pull requests into main get an automatic build-only check (image builds, nothing deployed) whose result shows on the PR. No keys stored in GitHub. Decisions already made by the user: Cloud Build trigger (not GitHub Actions), and yes to a build-only PR check."

## Context

Today the hosted generator is deployed by hand: someone runs the deploy command from their own machine, and it uploads whatever is in their working folder, committed or not. So what's live can drift from what's on GitHub, and only people with the tools set up can deploy.

This feature makes GitHub's `main` branch the single source of what's live:
- merging a pull request deploys it;
- every pull request is checked before merging, so a broken build is caught first.

Decisions already made by the user:
- deploys are run by Google Cloud itself, watching the repository (no deploy keys stored in GitHub);
- pull requests get a build-only check.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Merging a PR deploys it (Priority: P1)

A developer opens a pull request against `main`, it gets reviewed and merged. Without anyone running a command, the hosted generator is rebuilt from the merged code and the new version goes live. On GitHub, the merge commit shows a status (in progress → success or failure) that links to the build's log.

**Why this priority**: it's the user's request. It removes manual deploys and keeps the live page in step with `main`.

**Independent Test**: merge a small, visible change (e.g. a caption text) into `main`. Within 10 minutes, the hosted page shows the change, and the commit on GitHub shows a green deploy status.

**Acceptance Scenarios**:

1. **Given** a PR is merged into `main`, **When** the merge lands, **Then** a build and deploy start automatically within 1 minute, and the new version is serving within 10 minutes.
2. **Given** the deploy is running or finished, **When** someone looks at the merge commit on GitHub, **Then** they see its status (pending / success / failure) with a link to the log.
3. **Given** a direct push to `main` (not via a PR), **When** it lands, **Then** it's deployed the same way, because `main` is what's live.
4. **Given** a merge that only changes documentation or specs (README, CLAUDE.md, `specs/`, `.specify/`), **When** it lands, **Then** no deploy happens, so nobody's run is interrupted for a docs change.

---

### User Story 2 - Pull requests are checked before merging (Priority: P1)

When a PR targeting `main` is opened or updated, the generator's image is built from the PR's code as a check. Nothing is deployed, and the check never has access to the production secrets. The result appears on the PR as a pass/fail check with a link to the log.

**Why this priority**: with automatic deploys, a merge that doesn't build would fail in production. The check catches it before merging.

**Independent Test**: open a PR that breaks the build (e.g. a misspelled package in `requirements.txt`). The PR shows a failed check and the live page is unchanged. Fix it: the check turns green.

**Acceptance Scenarios**:

1. **Given** a PR into `main` is opened or gets new commits, **When** the check runs, **Then** the PR shows a check that passes only if the image builds.
2. **Given** a PR check, **When** it runs, **Then** nothing is deployed and the live service is untouched.
3. **Given** a PR check, **When** it runs, **Then** it can't read the production secrets (Gemini key, OAuth client).
4. **Given** a PR that only changes docs or specs, **When** it's opened, **Then** no build check is needed (skipped or trivially passing).

---

### User Story 3 - A failed deploy is safe and visible (Priority: P2)

If an automatic build or deploy fails, the previously deployed version keeps serving, the failure is visible on GitHub and in the build history, and a maintainer can roll back or redeploy with documented steps.

**Why this priority**: automatic deploys must not take the page down.

**Independent Test**: merge a change that builds but fails to start (or temporarily break the deploy permission). The page keeps working on the previous version, and the commit shows a failed status.

**Acceptance Scenarios**:

1. **Given** an automatic deploy fails at any stage, **When** users open the page, **Then** they get the previous version.
2. **Given** a failed or bad deploy, **When** a maintainer follows the README, **Then** they can redeploy a commit or switch traffic back to the previous version within 5 minutes.

---

### Edge Cases

- **Merge while someone is generating a language:** the new version replaces the running one, which interrupts and cancels the in-progress run, and that tab's packages go with the old version (spec 008). This is accepted. Docs-only merges don't deploy, and README tells maintainers to merge code changes when nobody is generating.
- **Two merges in quick succession:** the version that ends up live must be the later merge, never an older one finishing last.
- **First automatic deploy:** the deploy files (Dockerfile, deploy config, ignore files) aren't on GitHub yet. They must be merged to `main` before the first automatic deploy can work.
- **Pull requests from forks or outside contributors:** builds must not run automatically for people outside the organization, and never with access to secrets. A maintainer approves them explicitly.
- **Manual deploys still possible:** a maintainer can still deploy by hand in an emergency. README notes that a manual deploy of uncommitted work is overwritten by the next merge.
- **Secrets:** the automatic deploy uses the same Secret Manager references as today. Nothing secret is added to GitHub or to the build configuration.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every push to `main` on `curiouslearning/CL-Language-Publishing-Automation` (including merged PRs) MUST automatically build the generator from that commit and deploy it to the existing hosted service, with the same settings as today's manual deploy.
- **FR-002**: Pushes that change only documentation or spec files (`*.md` outside `language_automation/`, `specs/**`, `.specify/**`, `.claude/**`) MUST NOT trigger a deploy.
- **FR-003**: Each automatic deploy MUST report its status on the GitHub commit, with a link to its log.
- **FR-004**: Every PR into `main` (opened or updated) MUST run a build-only check from the PR's code and report pass/fail on the PR. The check MUST NOT deploy, and MUST NOT have access to production secrets or permission to change the live service.
- **FR-005**: PR checks for contributors outside the organization MUST require a maintainer's approval before running.
- **FR-006**: No deploy keys, service-account keys or other credentials MUST be stored in GitHub. Google Cloud's own connection to the repository is the only link.
- **FR-007**: A failed build or deploy MUST leave the previously deployed version serving.
- **FR-008**: When several deploys overlap, the most recent commit on `main` MUST end up live.
- **FR-009**: The automatic deploy MUST run under an identity with only the permissions it needs: build, push the image, deploy the service as the existing runtime account. It MUST NOT be able to read the secret values.
- **FR-010**: The README MUST document:
  - how deploys now happen;
  - where to see their status;
  - the one-time setup (connecting the repository, creating the triggers);
  - how to roll back or redeploy a commit by hand;
  - the "don't merge code while someone is generating" note.

  `CLAUDE.md`'s Hosting section MUST be updated to match.
- **FR-011**: The deploy files needed by the automatic build MUST be committed to `main` (they're currently local only).

### Key Entities

- **Deploy trigger**: watches `main`; builds and deploys every non-docs push.
- **PR check trigger**: watches PRs into `main`; builds only.
- **Repository connection**: Google Cloud's authorized link to the GitHub repository. It needs an organization admin's approval once.
- **Deploy identity**: the account the automatic deploy runs as, with least privilege.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of code merges to `main` reach the hosted page without anyone running a command, typically within 10 minutes of merging.
- **SC-002**: 100% of PRs into `main` show a build check result before they can be merged.
- **SC-003**: 0 credentials are stored in GitHub.
- **SC-004**: A failed automatic deploy causes 0 minutes of downtime: the previous version keeps serving.
- **SC-005**: 0 deploys are triggered by documentation-only merges.
- **SC-006**: A maintainer can roll back to the previous version in under 5 minutes using the README.

## Assumptions

- **No new repositories** (user decision, 2026-10-15): builds come from this existing GitHub repository and reuse the existing image registry and Cloud Run service. Any code change merged to `main` deploys.

- `main` is the only branch that deploys. There's one environment (the existing service); no separate staging.
- A GitHub organization admin for `curiouslearning` can approve Google Cloud's GitHub App for this repository. Until then, nothing can be triggered.
- Interrupting an in-progress run on deploy is acceptable (rare; the same as manual deploys today).
- Requiring the PR check before merging (branch protection) is recommended. Turning it on needs a repo admin and is done in GitHub settings, outside this repo.
- The existing manual deploy command keeps working for emergencies.
- The current uncommitted work (specs 007/008, deploy files) will be committed and merged to `main` as part of rolling this out.
