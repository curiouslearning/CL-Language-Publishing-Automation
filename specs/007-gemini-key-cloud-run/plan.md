# Implementation Plan: Gemini Key for the Hosted Generator

**Branch**: `007-gemini-key-cloud-run` (spec folder; work stays on `main`) | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-gemini-key-cloud-run/spec.md`

## Summary

Make the AI language check work on the Cloud Run page with a Gemini key owned by `ftm-language-generator`.

- **Cloud setup (one-time, documented in the README):** enable the Gemini API (`generativelanguage.googleapis.com`), plus the API Keys and Secret Manager APIs. Create an API key restricted to the Gemini API, and pipe its value straight into a new Secret Manager secret `ftm-gemini-api-key`, without echoing it or saving it to a file. Grant only `ftm-generator-run` `roles/secretmanager.secretAccessor` on that secret.
- **Deploy:** `cloudbuild.yaml` adds `GEMINI_API_KEY=ftm-gemini-api-key:latest` to `--set-secrets` as an **environment variable**. `ai_providers.load_config()` already reads `GEMINI_API_KEY` from the environment before `.env`, and `app.py` passes `os.environ` to both subprocesses. So the key reaches the AI check with no change to how keys are found.
- **Small code changes (`ai_providers.py`, `app.py`):** strip whitespace from keys, so a trailing newline in a secret value can't break requests. When `FTM_HOSTED=1`, the "not configured" reason names the secret, not `.env`.
- **Docs:** README (setup, deploy, rotate, Secrets), CLAUDE.md (Hosting + AI check config), and comments in `cloudbuild.yaml`/`Dockerfile`. They no longer say "no AI key attached / provider undecided".

## Technical Context

**Language/Version**: Python 3.13 (container image `python:3.13-slim`); local dev Python 3

**Primary Dependencies**: existing only (`google-genai`, `streamlit`, Google API clients). Adds no new Python dependency. Cloud tooling: `gcloud` (Cloud Build, Cloud Run, Secret Manager, API Keys)

**Storage**: Secret Manager secret `ftm-gemini-api-key` (versioned). No other storage changes.

**Testing**: no automated suite (constitution). Manual verification per [quickstart.md](quickstart.md)

**Target Platform**: Cloud Run, `ftm-language-generator`, `us-central1`, service `ftm-language-generator`, runtime SA `ftm-generator-run`

**Project Type**: Streamlit web page + CLI scripts, deployed as one container

**Performance Goals**: unchanged. One Gemini request per language (about 1.5 K input tokens)

**Constraints**: the key never appears in the repo, image, upload or service config (FR-003, SC-002). Only the runtime SA can read the secret (FR-004). The AI check stays advisory (FR-008).

**Scale/Scope**: 1 secret, 1 API key, 1 deploy-file line, 2 small code edits, docs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Verify before touching disk | ✅ N/A | Pipeline order unchanged |
| II. Exact language matching | ✅ N/A | Untouched |
| III. JSON is source of truth for audio | ✅ N/A | Untouched |
| IV. Stable log contract | ✅ | No log prefix changes; the AI check keeps its `🤖`/`⚠` lines |
| V. No secrets in the repository | ✅ | Key exists only in Secret Manager. It's piped from the key-string command into the secret, so it never lands in a file or shell history. `.dockerignore`/`.gcloudignore` unchanged |
| Tech constraints: no new dependency | ✅ | None added |
| Workflow: CLAUDE.md updated with behaviour | ✅ | Planned (Hosting, AI config, Secrets) |
| Workflow: manual verification task | ✅ | quickstart V1–V6, incl. a real language run on the hosted page |

**Post-design re-check**: still passes. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/007-gemini-key-cloud-run/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── deploy-and-key.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
cloudbuild.yaml                      # + GEMINI_API_KEY secret env var; comments updated
Dockerfile                           # comment only (already mentions the Gemini key)
README.md                            # Deploy to Cloud Run: enable API, key, secret, IAM, rotate; Secrets section
CLAUDE.md                            # Hosting + AI check config: Gemini is the hosted provider
language_automation/
├── ai_providers.py                  # strip keys; hosted "not configured" reason names the secret
├── app.py                           # caption: no ".env.example" hint when hosted
└── .env.example                     # comment: local only; Cloud Run uses the secret
```

**Structure Decision**: existing single-folder layout. No new modules.

## Complexity Tracking

None.
