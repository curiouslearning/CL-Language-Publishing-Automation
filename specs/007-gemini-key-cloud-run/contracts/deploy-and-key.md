# Contract: Deploy settings and the Gemini key

## Cloud Run service `ftm-language-generator` (set by `cloudbuild.yaml`)

| Setting | Value | Change |
|---|---|---|
| `--set-secrets` | `/secrets/client_secret_web.json=ftm-oauth-web-client:latest,GEMINI_API_KEY=ftm-gemini-api-key:latest` | **added** `GEMINI_API_KEY` |
| `--set-env-vars` | `FTM_HOSTED=1,FTM_PUBLIC_URL=…,FTM_OAUTH_CLIENT_FILE=/secrets/client_secret_web.json` | unchanged. The key is **never** in `--set-env-vars` |
| `--service-account` | `ftm-generator-run@…` | unchanged |

Deploy precondition: secret `ftm-gemini-api-key` exists and `ftm-generator-run` can access it. If not, the deploy fails and the previous revision keeps serving.

## Environment seen by `ai_language_check.py`

| Variable | Hosted | Local |
|---|---|---|
| `GEMINI_API_KEY` | from the secret (whitespace stripped by `load_config`) | from the real env or `.env` |
| `FTM_HOSTED` | `1` | unset |

## AI check "not configured" reason (`load_config` second return value)

| Situation | Reason text |
|---|---|
| Local, no key | `no API key configured for gemini: add GEMINI_API_KEY=... to language_automation/.env` (unchanged) |
| Hosted (`FTM_HOSTED=1`), no key | `no API key configured for gemini: the Cloud Run service has no GEMINI_API_KEY secret attached (README "Deploy to Cloud Run")` |

`app.py` caption: `Not configured: <reason>.` followed by `See .env.example.` **only when not hosted**.

All other AI check output (`🤖 AI check:`, `⚠ AI check:`, `🤖 AI report:`) is unchanged.
