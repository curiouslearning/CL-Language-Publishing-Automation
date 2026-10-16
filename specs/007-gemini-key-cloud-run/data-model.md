# Data Model: Gemini Key for the Hosted Generator

No application data changes. The "entities" are cloud resources.

| Entity | Identifier | Attributes | Rules |
|---|---|---|---|
| Gemini API | `generativelanguage.googleapis.com` in `ftm-language-generator` | enabled | Must be enabled before the key works |
| Production API key | display name `FTM generator (Cloud Run)` | API target restriction: `generativelanguage.googleapis.com` only | Created in the project, never the developer's personal key. The value is never written to disk |
| Gemini key secret | `ftm-gemini-api-key` | replication automatic; versions 1..n | Holds exactly the key string (no newline). Rotation adds a version; older versions are disabled, then destroyed |
| Secret IAM binding | on `ftm-gemini-api-key` | `roles/secretmanager.secretAccessor` → `serviceAccount:ftm-generator-run@ftm-language-generator.iam.gserviceaccount.com` | The only non-admin reader |
| Cloud Run env var | `GEMINI_API_KEY` | value source `ftm-gemini-api-key:latest` | Resolved at instance start. Never set as a literal |
| Local developer key | `GEMINI_API_KEY` in `language_automation/.env` | personal AI Studio key | Local only; excluded from the upload and the image |

## Key lifecycle

```text
created (restricted) ──> stored as secret version N ──> attached (deploy) ──> in use
        rotation: new key ──> version N+1 ──> redeploy ──> disable version N ──> delete old key
```

## Key lookup order (unchanged, in `ai_providers.load_config`)

1. Real environment variable `GEMINI_API_KEY` (Cloud Run: from the secret)
2. `language_automation/.env` (local)
3. Missing → AI check "not configured" (hosted: the reason names the secret)
