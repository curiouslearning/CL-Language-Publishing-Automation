# AI-assisted Language Publishing Automation

Tooling for publishing new languages for Curious Learning's **Feed the Monster (FTM)** game. For one language, it pulls the content JSON and audio files from Google Drive into `language_automation/lang/<language>/`, cleans up unused audio, and reports missing audio. A Streamlit web page wraps the pipeline for the content team. An optional AI review checks the language content.

> For the full details (pipeline steps, the web page's behaviour, the AI check, gotchas), see [CLAUDE.md](CLAUDE.md). Feature specs are in [specs/](specs/) and project rules are in [.specify/memory/constitution.md](.specify/memory/constitution.md).

## Setup

1. Install Python dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Install **ffmpeg** and put it on your `PATH` (it converts non-mp3 audio to mp3).
3. Put the Google OAuth client files in `language_automation/`. Ask the team for them and **never commit them** (both are gitignored):
   - `client_secret_web.json`: the **Web application** client for the web page, from the Google Cloud project `ftm-language-generator`.
   - `credentials.json`: the **desktop** client, only needed for the command line.
4. Optional, only for the AI language check: copy `language_automation/.env.example` to `language_automation/.env` and add the key (`GEMINI_API_KEY` or `ANTHROPIC_API_KEY`). Choose the provider and model in `language_automation/config.json`. For local testing, use your own Gemini API key from Google AI Studio. The hosted page uses Gemini with the project's own key from Secret Manager (see "Deploy to Cloud Run").

## Usage

Run everything from inside `language_automation/`:

```bash
cd language_automation

python -m streamlit run app.py              # web page for the content team
python generate_language.py Hausa           # full pipeline from the command line
python ai_language_check.py Hausa           # optional AI review of a generated language
```

**Signing in:** only `@curiouslearning.org` accounts are accepted.
- **Web page:** the first Generate in a page visit shows a **Sign in with Google** button that opens Google in a new tab. Each run uses the access of the person who signed in. Nothing is saved to disk, so reloading the page asks again.
- **Command line:** the first run opens a browser to sign in, and the sign-in is cached in `token.json`. Delete that file to sign in again.

The individual steps (`fetch_lang_sheet.py`, `fetch_drive_audios.py`, `check_missing_audios.py`, `fetch_unity_json.py`) can be run on their own for debugging. See [CLAUDE.md](CLAUDE.md#running-the-pipeline).

## What a run does

1. Checks that both the language's sheet and its audio folder exist on Drive.
2. Reads the game-JSON URL from the language sheet and downloads `ftm_<language>.json`.
3. Downloads and converts the language's audio files.
4. Deletes audio the JSON doesn't use, and reports audio the JSON needs but that's missing. Look-alike spellings are flagged for the team to check and are never renamed.
5. On the web page, offers the package as a zip: **📦 Download language package (.zip)**. It contains `<language>/ftm_<language>.json`, `audios/` and `images/`.

**On the hosted page, download right away.** The package is kept on the server only until you close or reload the page. After that it's deleted, whether or not it was downloaded, and you'd generate the language again from Drive. Locally, the package also stays in `language_automation/lang/<language>/`.

## Repository layout

| Path | Contents |
| --- | --- |
| `language_automation/` | Pipeline scripts, Streamlit app (`app.py`), AI check, `config.json` |
| `Dockerfile`, `cloudbuild.yaml` | Container image and Cloud Run deploy for the web page |
| `.circleci/config.yml` | CI/CD: build check on every PR, deploy on every merge to `main` |
| `specs/` | Spec-kit feature specs (001–010) |
| `.specify/`, `.claude/skills/` | Spec-kit templates, scripts and commands |
| `CLAUDE.md` | Detailed developer and maintainer notes |

## Deploy to Cloud Run

The web page runs on Cloud Run in the `ftm-language-generator` project. `cloudbuild.yaml` builds the `Dockerfile` image, pushes it to Artifact Registry (repo `ftm`) and deploys it. It uses one instance, scales to zero, and has the page's own curiouslearning.org sign-in in front.

**How deploys happen (CircleCI, spec 010):** the same CircleCI setup as our other projects (`.circleci/config.yml`).
- **Every PR** (every branch except `main`) runs `build-check`: the Docker image is built, and nothing is pushed or deployed. The result shows as a check on the PR.
- **Every merge or push to `main`** runs `deploy`. CircleCI signs in to Google Cloud with its OIDC token (no key stored anywhere) as `ftm-deployer`, and runs `cloudbuild.yaml`.
  - A merge that only changes docs or specs (`*.md`, `specs/`, `.specify/`, `.claude/`, `.github/`) is skipped.
  - If two merges overlap, the newer build wins: an older one that finishes last doesn't deploy.
- **Status:** the check on the GitHub commit/PR, and the job log in CircleCI.
- **Merge code changes only when nobody is generating a language.** A deploy replaces the running server and cancels a run in progress.

**One-time setup** (a project Owner, from the repo root, in Git Bash; region `us-central1`, service `ftm-language-generator`):

```bash
P=ftm-language-generator
PN=838897084130   # project number

# Container repository
gcloud artifacts repositories create ftm --repository-format=docker --location=us-central1 --project=$P

# Runtime service account: it can only read the two secrets
gcloud iam service-accounts create ftm-generator-run --display-name="FTM generator (Cloud Run)" --project=$P
RUN_SA=ftm-generator-run@$P.iam.gserviceaccount.com

# Secret: the web OAuth client file
gcloud secrets create ftm-oauth-web-client --data-file=language_automation/client_secret_web.json --project=$P
gcloud secrets add-iam-policy-binding ftm-oauth-web-client --member=serviceAccount:$RUN_SA --role=roles/secretmanager.secretAccessor --project=$P

# Gemini API key for the AI check (spec 007): restricted to the Gemini API, piped straight into
# the secret so it never lands in a file or the terminal
gcloud services enable generativelanguage.googleapis.com apikeys.googleapis.com secretmanager.googleapis.com iamcredentials.googleapis.com sts.googleapis.com --project=$P
gcloud services api-keys create --display-name="FTM generator (Cloud Run)" --api-target=service=generativelanguage.googleapis.com --project=$P
KEY_NAME=$(gcloud services api-keys list --project=$P --filter='displayName="FTM generator (Cloud Run)"' --format="value(name)" --limit=1)
gcloud services api-keys get-key-string $KEY_NAME --format="value(keyString)" | tr -d '\r\n' | gcloud secrets create ftm-gemini-api-key --data-file=- --replication-policy=automatic --project=$P
gcloud secrets add-iam-policy-binding ftm-gemini-api-key --member=serviceAccount:$RUN_SA --role=roles/secretmanager.secretAccessor --project=$P

# Deploy identity: starts the Cloud Build, pushes to repo ftm, deploys as the runtime account. No secret access.
gcloud iam service-accounts create ftm-deployer --display-name="FTM deploy (Cloud Build)" --project=$P
DEP=ftm-deployer@$P.iam.gserviceaccount.com
for R in roles/run.admin roles/cloudbuild.builds.editor roles/logging.logWriter roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding $P --member=serviceAccount:$DEP --role=$R --condition=None
done
gcloud iam service-accounts add-iam-policy-binding $RUN_SA --member=serviceAccount:$DEP --role=roles/iam.serviceAccountUser --project=$P
gcloud iam service-accounts add-iam-policy-binding $DEP --member=serviceAccount:$DEP --role=roles/iam.serviceAccountUser --project=$P
gcloud artifacts repositories add-iam-policy-binding ftm --location=us-central1 --member=serviceAccount:$DEP --role=roles/artifactregistry.writer --project=$P
gcloud storage buckets add-iam-policy-binding gs://${P}_cloudbuild --member=serviceAccount:$DEP --role=roles/storage.admin

# CircleCI sign-in without a key (OIDC + workload identity federation). The IDs are in CircleCI:
# Organization Settings > Overview (organization ID) and Project Settings > Overview (project ID).
ORG_ID="<CircleCI organization ID>"; CCI_PROJECT="<CircleCI project ID>"
gcloud iam workload-identity-pools create circleci --location=global --display-name="CircleCI" --project=$P
gcloud iam workload-identity-pools providers create-oidc circleci-oidc --location=global --workload-identity-pool=circleci \
  --issuer-uri="https://oidc.circleci.com/org/$ORG_ID" --allowed-audiences="$ORG_ID" \
  --attribute-mapping="google.subject=assertion.sub,attribute.project_id=assertion['oidc.circleci.com/project-id']" \
  --attribute-condition="attribute.project_id=='$CCI_PROJECT'" --project=$P
gcloud iam service-accounts add-iam-policy-binding $DEP --role=roles/iam.workloadIdentityUser --project=$P \
  --member="principalSet://iam.googleapis.com/projects/$PN/locations/global/workloadIdentityPools/circleci/attribute.project_id/$CCI_PROJECT"
```

Then:
- In the Cloud Console (Google Auth Platform → Clients → the web client), add the Cloud Run address as an **authorized redirect URI**. Include the trailing slash: `https://ftm-language-generator-838897084130.us-central1.run.app/`
- In CircleCI (organization `curiouslearning`):
  - set up the project from `main`, using the repo's `.circleci/config.yml`;
  - create a context named **`ftm-language-generator-gcp`** (Organization Settings → Contexts). It holds nothing secret: CircleCI only issues the OIDC token to jobs that use a context.

Only `ftm-generator-run` can read the two secrets. Neither CircleCI nor `ftm-deployer` needs them: Cloud Run reads them as the runtime account when an instance starts. If a secret is missing or not readable, the deploy fails and the previous revision keeps serving.

The project has billing enabled, so Gemini usage from this key is billed at paid-tier rates. It's small: about 1.5 K input tokens per language (turn on "Show tokens used" to see it). Optionally, set a budget alert on the project in Billing → Budgets & alerts.

**Manual deploy** (emergencies only): `gcloud builds submit --config cloudbuild.yaml --region=us-central1 --project=ftm-language-generator`. It uploads your local files, committed or not, and the next merge to `main` replaces it. To redeploy `main` as it is, rerun the latest `deploy` job in CircleCI.

**Roll back:** `gcloud run services update-traffic ftm-language-generator --to-revisions=<previous revision>=100 --region=us-central1 --project=ftm-language-generator`. The revisions are listed under Cloud Run → the service → Revisions. The next deploy moves traffic to the new revision again.

- Secrets never go into the image or the upload. `.gcloudignore` and `.dockerignore` exclude them, and Cloud Run mounts them from Secret Manager.
- Changing the region or the service name changes the address. Pass `--substitutions=_REGION=...` and register the new redirect URI.

### Rotate the Gemini key

No file in the repository changes. In Git Bash:

```bash
P=ftm-language-generator
OLD_KEY=$(gcloud services api-keys list --project=$P --filter='displayName:"FTM generator (Cloud Run)"' --format="value(name)" --limit=1)
gcloud services api-keys create --display-name="FTM generator (Cloud Run) $(date +%F)" --api-target=service=generativelanguage.googleapis.com --project=$P
NEW_KEY=$(gcloud services api-keys list --project=$P --filter="displayName=\"FTM generator (Cloud Run) $(date +%F)\"" --format="value(name)" --limit=1)
gcloud services api-keys get-key-string $NEW_KEY --format="value(keyString)" | tr -d '\r\n' | gcloud secrets versions add ftm-gemini-api-key --data-file=- --project=$P
# Pick up the new version: redeploy (a new revision resolves :latest again), e.g. rerun the last CircleCI deploy job, or:
gcloud builds submit --config cloudbuild.yaml --region=us-central1 --project=$P
# After checking the AI check still works: retire the old version and the old key
gcloud secrets versions list ftm-gemini-api-key --project=$P
gcloud secrets versions disable <OLD_VERSION> --secret=ftm-gemini-api-key --project=$P
gcloud services api-keys delete $OLD_KEY --project=$P
```

## Secrets

`credentials.json`, `token.json`, `client_secret*.json`, `.env`, the AI cache and generated `lang/` data are gitignored. Keep it that way. Never hardcode credentials. On Cloud Run, both secrets come from Secret Manager: the web OAuth client (`ftm-oauth-web-client`, mounted as a file) and the Gemini key (`ftm-gemini-api-key`, as `GEMINI_API_KEY`). Local runs use your own key in `language_automation/.env`.
