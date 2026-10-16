# Quickstart / Validation: Gemini Key for the Hosted Generator

**Prerequisites**:
- Owner (or equivalent) on `ftm-language-generator`.
- `gcloud` authenticated, with Git Bash or a POSIX shell for the pipes.
- The spec 005 one-time setup is already done (Artifact Registry repo, `ftm-generator-run`, `ftm-oauth-web-client`).

The exact commands live in README "Deploy to Cloud Run" (see [contracts/deploy-and-key.md](contracts/deploy-and-key.md) for the settings they produce). This guide only checks the result.

## V1. One-time setup done

```bash
P=ftm-language-generator
gcloud services list --enabled --project=$P | grep -E "generativelanguage|apikeys|secretmanager"   # 3 lines
gcloud services api-keys list --project=$P --format="table(displayName,restrictions.apiTargets)"     # key → generativelanguage only
gcloud secrets versions list ftm-gemini-api-key --project=$P                                          # ≥1 enabled version
gcloud secrets get-iam-policy ftm-gemini-api-key --project=$P                                         # only ftm-generator-run as secretAccessor
```

## V2. Deploy

`gcloud builds submit --config cloudbuild.yaml --project=ftm-language-generator` → build SUCCESS.

`gcloud run services describe ftm-language-generator --region=us-central1 --project=$P` shows `GEMINI_API_KEY` sourced from secret `ftm-gemini-api-key`. No key value is visible anywhere.

## V3. Hosted AI check works (US1, SC-001)

1. Open the service URL and turn on **🤖 AI language check**. The caption reads `Uses gemini (gemini-3.1-flash-lite).`, not "Not configured".
2. Turn on **Show tokens used**. Generate a real language (e.g. `Hindi`), sign in with curiouslearning.org.
3. Expected:
   - the pipeline completes as before (audio check summary present);
   - the AI section shows a review with model and non-zero input/output tokens;
   - "Download AI log" works.

## V4. Key is secret (US2, SC-002)

- `git grep -n "AIza"` → no matches.
- The image contains no `.env`.
- The service config shows only a secret reference.
- Restriction: calling another Google API with the key (e.g. `https://www.googleapis.com/drive/v3/about?key=<key>`, run from a throwaway shell) is refused with `API_KEY_SERVICE_BLOCKED`.

## V5. Failure stays advisory (FR-008, SC-006)

Locally, with `FTM_HOSTED=1` set and no `GEMINI_API_KEY`:
- the caption shows the hosted "no GEMINI_API_KEY secret attached" reason, without `.env.example`;
- a CLI `python ai_language_check.py Hindi` reports `unavailable` with that reason;
- the pipeline itself still completes when run without the AI check.

## V6. Rotation (US3, SC-005)

Create a new key, add it as a new secret version (README "Rotate the Gemini key"), and redeploy or update the service. Then re-run V3: it still works with no repo change. Disable the old version, then delete the old key.

## Local unchanged

With the personal key in `language_automation/.env` and `FTM_HOSTED` unset, `python ai_language_check.py Hindi` works as before.
