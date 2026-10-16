# Feature Specification: CI/CD on CircleCI

**Feature Branch**: `010-circleci-cicd`

**Created**: 2026-10-16

**Status**: Draft

**Input**: User description: "Switch the PR checks and deploy-on-merge from Google Cloud Build to CircleCI, like our other projects: add config.yml, set the project up on CircleCI, then remove the Google Cloud Build automation and the settings it no longer needs."

## Context

Spec 009 set up PR checks and deploy-on-merge with Google Cloud Build triggers, and it works. But Curious Learning's other repositories use CircleCI. The user decided (2026-10-16, shared with David) to use CircleCI here too, for consistency: one tool, one place to see checks, the same branch-protection habits.

This spec replaces the **trigger** side of spec 009. The deploy itself (`cloudbuild.yaml`, the `ftm-deployer` identity, the newest-wins guard, the secrets) is unchanged and reused.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Merging to main deploys, via CircleCI (Priority: P1)

A PR is merged into `main`. CircleCI runs a deploy job that builds and deploys the generator to the existing Cloud Run service. The merge commit on GitHub shows CircleCI's status with a link to the job.

**Independent Test**: merge a small code change. The CircleCI `build-and-deploy-prod` job succeeds, and the new Cloud Run revision carries that commit's short SHA.

**Acceptance Scenarios**:

1. **Given** a code change merged to `main`, **When** CircleCI runs, **Then** the change is live within ~10 minutes, and the commit shows a green CircleCI check.
2. **Given** a merge that changes only docs or specs (`*.md`, `specs/`, `.specify/`, `.claude/`, `.github/`), **When** CircleCI runs, **Then** the deploy job stops early and nothing is deployed.
3. **Given** two quick merges, **When** both deploy, **Then** the newer commit ends up live (the spec 009 guard).

### User Story 2 - PRs get a CircleCI build check (Priority: P1)

Every PR branch gets a CircleCI job that builds the Docker image, without pushing or deploying, and without any Google Cloud access. Its result shows on the PR.

**Independent Test**: open a PR. The CircleCI `test` shows on it, and the live revision is unchanged.

### User Story 3 - Google Cloud Build automation removed (Priority: P2)

Once CircleCI works, the Cloud Build GitHub triggers, the GitHub connection and app, and the permissions that only they needed are removed. Merges then deploy exactly once, and nothing unused keeps access.

**Independent Test**: after cleanup, a merge produces one CircleCI deploy and no Cloud Build trigger build. The removed identities and grants no longer appear in IAM.

### Edge Cases

- **Switch-over:** while both systems exist, a merge would deploy twice. That's harmless (same commit, newest wins), but the Cloud Build deploy trigger is removed before the CircleCI rollout PR is merged.
- **CircleCI can't sign in to Google Cloud** (setup incomplete): the deploy job fails, the previous revision keeps serving, and the failure shows on the commit.
- **Forked PRs / other CircleCI projects:** they can't get Google Cloud access. The PR job has none, and the Google side only trusts this one CircleCI project.
- **Manual deploy** stays possible for emergencies (README).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A CircleCI config in the repo MUST run a build-only check on every branch except `main`, and a deploy on every push to `main`.
- **FR-002**: The deploy MUST reuse the existing deploy (`cloudbuild.yaml`, same service, settings, secrets and newest-wins guard) and label the revision with the deployed commit.
- **FR-003**: The deploy MUST skip merges that change only docs or specs.
- **FR-004**: CircleCI MUST sign in to Google Cloud without any stored key (OIDC with workload identity federation), acting only as `ftm-deployer`, and only for this CircleCI project.
- **FR-005**: The PR check MUST have no Google Cloud access.
- **FR-006**: After CircleCI is proven, the Cloud Build triggers, the GitHub connection and its repository link, the Cloud Build GitHub App installation, the `ftm-pr-builder` identity, `cloudbuild-pr.yaml`, and grants that only served Cloud Build triggers or manual Compute-SA deploys MUST be removed.
- **FR-007**: README and CLAUDE.md MUST describe the CircleCI setup, the one-time Google Cloud setup and the rollback. Spec 009 is marked superseded.

## Success Criteria *(mandatory)*

- **SC-001**: 100% of code merges to `main` deploy through CircleCI with no manual step.
- **SC-002**: Every PR shows a CircleCI build check.
- **SC-003**: 0 keys stored in CircleCI or GitHub.
- **SC-004**: After cleanup, each merge deploys exactly once.
- **SC-005**: 0 Cloud Build triggers, connections or unused identities remain.

## Assumptions

- The CircleCI organization `curiouslearning` is already used by other projects, and the user can set up this project and create a context there.
- No new repositories (spec 009 R0 still applies): the existing GitHub repo, Artifact Registry repo `ftm` and Cloud Run service are reused.
- Cloud Build is still used as the build/deploy *engine*, started by CircleCI. Only its GitHub triggers are removed.
