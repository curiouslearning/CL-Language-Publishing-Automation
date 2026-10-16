# Quickstart / Validation: Automatic Deploy on Merge

Settings: [contracts/build-configs.md](contracts/build-configs.md), resources: [data-model.md](data-model.md).

**Prerequisites**:
- An Owner on `ftm-language-generator`.
- A `curiouslearning` GitHub org owner available to approve the Cloud Build GitHub App.
- The deploy files and specs 007–009 work on a branch with an open PR (research R6).

## V1. Setup in place

```bash
P=ftm-language-generator
gcloud builds connections describe ftm-github --region=us-central1 --project=$P --format="value(installationState.stage)"   # COMPLETE
gcloud builds triggers list --region=us-central1 --project=$P --format="table(name,serviceAccount)"                    # ftm-deploy-main, ftm-pr-check
gcloud projects get-iam-policy $P --flatten="bindings[].members" --filter="bindings.members:ftm-pr-builder" --format="value(bindings.role)"  # logging.logWriter only
```

The GitHub repo → Settings → Integrations → GitHub Apps lists "Google Cloud Build" with access to this repository only.

## V2. PR check (US2)

- The rollout PR shows check `ftm-pr-check` running, then green. Its log shows the docker build. There's no deploy step, and the live revision (`gcloud run services describe … --format="value(status.latestReadyRevisionName)"`) is unchanged.
- Push a commit to that PR with a bad requirement line, e.g. `nonexistent-package-xyz==1.0`: the check turns red. Revert it: green again.

## V3. Merge deploys (US1)

1. Merge the PR. Within 1 minute, the merge commit shows `ftm-deploy-main` pending, and within ~10 minutes success.
2. A new revision is live, labeled `commit-sha=<merge short SHA>`.
3. The page returns HTTP 200.

## V4. Docs-only merge (FR-002)

Merge a PR that only edits `README.md`: no `ftm-deploy-main` build runs, and the revision is unchanged.

## V5. Newest wins (FR-008)

Merge two small code PRs back to back. Both builds run, and the one created later is live. If the older one finishes last, its log shows `⏭️ Skipping deploy`.

## V6. Failure is safe (US3)

Run `gcloud builds triggers run ftm-deploy-main --branch=main` after temporarily changing `_RUN_SA` in a branch, or simulate by using a PR-only test. Simplest: confirm that a red PR check never deploys (V2), and that a failed deploy build leaves the previous revision serving (`latestReadyRevisionName` unchanged, page 200).

Rollback drill: `gcloud run services update-traffic ftm-language-generator --to-revisions=<previous>=100 --region=us-central1 --project=$P` takes under 5 minutes, and the page serves the previous revision.

## V7. No credentials in GitHub (SC-003)

The repo's Settings → Secrets and variables → Actions lists nothing for this, and `git grep -nE "AIza|BEGIN PRIVATE KEY|client_secret"` on `main` returns no secrets.
