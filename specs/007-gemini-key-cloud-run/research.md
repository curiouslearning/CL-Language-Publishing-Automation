# Research: Gemini Key for the Hosted Generator

## R1. How the key reaches the AI check on Cloud Run

- **Decision**: expose the secret as an **environment variable** `GEMINI_API_KEY` with `--set-secrets=GEMINI_API_KEY=ftm-gemini-api-key:latest`, next to the existing file mount for the OAuth client.
- **Rationale**:
  - `ai_providers.load_config()` already reads `os.environ["GEMINI_API_KEY"]` before `.env`.
  - `app.py` builds both subprocess environments from `dict(os.environ, ...)` (pipeline and AI check), so the variable reaches `ai_language_check.py` unchanged.
  - Zero change to key lookup (FR-005).
- **Alternatives**:
  - A file mount (`/secrets/gemini_api_key`) plus a new `GEMINI_API_KEY_FILE` variable. That needs new lookup code for no gain.
  - Mounting a whole `.env` as a secret. That mixes formats and could shadow local behaviour.

## R2. `:latest` and rotation

- **Decision**: reference `:latest`. Rotate by adding a new secret version, then redeploying (`gcloud builds submit ...`) or running `gcloud run services update ftm-language-generator --region=us-central1 --update-secrets=GEMINI_API_KEY=ftm-gemini-api-key:latest`. Then disable the old version and delete the old API key.
- **Rationale**: for env-var secrets, Cloud Run resolves the version when an instance starts. A new revision (or a new instance) picks up the newest version. The repo doesn't change (FR-007, SC-005).
- **Alternatives**: pinning a version number. That's safer against a bad new version, but every rotation would need a repo edit, which the spec rules out.

## R3. Creating and restricting the key without exposing it

- **Decision**:
  1. `gcloud services api-keys create --display-name="FTM generator (Cloud Run)" --api-target=service=generativelanguage.googleapis.com`
  2. Read the key's resource name: `gcloud services api-keys list --filter=displayName=...`
  3. `gcloud services api-keys get-key-string <name> --format="value(keyString)" | tr -d '\r\n' | gcloud secrets create ftm-gemini-api-key --data-file=- --replication-policy=automatic`
- **Rationale**:
  - The API target restriction means the key works only against the Gemini API (US2 scenario 2).
  - Piping keeps the value out of files, terminal scrollback and shell history (principle V).
  - `tr -d` removes the newline that `value(...)` output appends.
- **Alternatives**:
  - Creating the key in the AI Studio UI and pasting it. That's acceptable as a fallback, documented as one line, but paste-into-terminal risks history.
  - Using the developer's personal key. That's rejected by the spec assumption: usage must belong to the project.

## R4. APIs to enable

- **Decision**: `gcloud services enable generativelanguage.googleapis.com apikeys.googleapis.com secretmanager.googleapis.com --project=ftm-language-generator`. Secret Manager is probably already on (the OAuth secret exists); enabling it again is harmless.
- **Rationale**: the Gemini API must be on for the key to work (FR-001). The API Keys API is needed for `gcloud services api-keys`.

## R5. Who can read the secret

- **Decision**: a secret-level binding of `roles/secretmanager.secretAccessor` for `ftm-generator-run@ftm-language-generator.iam.gserviceaccount.com` only. The Cloud Build SA gets nothing new: Cloud Run checks access with the **runtime** SA when the revision starts.
- **Rationale**: least privilege (FR-004, SC-003). This mirrors the existing `ftm-oauth-web-client` binding.
- **Failure mode**: if the secret is missing or the binding is absent, `gcloud run deploy` fails, because the revision can't become ready. Cloud Build marks the build failed and the previous revision keeps serving. This covers the "fail clearly" edge case without code.

## R6. Trailing whitespace and the hosted "not configured" message

- **Decision**:
  - `load_config()` strips each API key (`.strip()`), so a secret saved with a newline or spaces still works. An all-whitespace key counts as missing.
  - When `FTM_HOSTED=1` and the Gemini key is missing, the reason reads `no API key configured for gemini: the Cloud Run service has no GEMINI_API_KEY secret attached (README "Deploy to Cloud Run")`, not the `.env` hint.
  - `app.py` drops "See `.env.example`." from the caption when hosted.
- **Rationale**: an HTTP header with `\n` is rejected by the client library, and the error would look like a bad key. A hosted user can't act on a `.env` hint.
- **Alternatives**: none worth keeping; both are one-line changes.

## R7. Billing tier

- **Decision**: accept the paid tier. A key in a project with billing enabled is billed at Gemini paid rates. `config.json` keeps `gemini-3.1-flash-lite` with its flash-lite/flash fallbacks.
- **Rationale**: about 1.5 K input tokens per language is negligible. Spec 006's token display makes usage visible. An optional budget alert on the project is documented, but isn't required.
- **Alternatives**: a separate billing-free project for the key. That adds another project to manage, and its free-tier rate limits are a worse experience for the team.

## R8. Provider selection on the hosted page

- **Decision**: no change. `config.json` already sets `"provider": "gemini"`, and it's baked into the image. No `ANTHROPIC_API_KEY` secret is attached, and switching to Claude stays out of scope.
