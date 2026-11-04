# Contract: HTTP API (`language_automation/server.py`)

All JSON. Errors: `{"detail": "<message safe to show>"}`.

## `GET /api/config`

```json
{
  "hosted": true,
  "signin": {"client_id": "….apps.googleusercontent.com", "hd": "curiouslearning.org"},
  "signin_error": null,
  "ai": {"provider": "gemini", "model": "gemini-2.5-flash", "reason": null},
  "busy": false
}
```
`signin` is null and `signin_error` set ("client_secret_web.json is missing", …) when sign-in isn't set up: the page disables Generate.

## `POST /api/existing`

Body `{"langs": ["Hausa"]}` → `{"existing": {"Hausa": 165}}`. Local only: counts mp3s when `lang/<lang>/` has its JSON and audios. Hosted: always `{}` (the page uses its own runs).

## `POST /api/runs`

Headers: `Authorization: Bearer <Google access token>`. Body `{"lang": "Hausa", "ai_check": true}`.

Refusals before anything starts (no stream):
- `400` invalid language name;
- `503` sign-in not set up;
- `409` another run in progress (`"Another language is being generated right now. Please try again when it finishes."`).

Otherwise `200`, `Content-Type: application/x-ndjson`, one JSON object per line:

| Event | Fields | Meaning |
|-------|--------|---------|
| `auth` | `status`: `ok` \| `refused` \| `failed`, `email?`, `reason?` | server token check. Not `ok` → `end` follows; nothing was created or deleted. |
| `line` | `text` | one pipeline stdout line (log contract) |
| `pipeline_end` | `returncode` | |
| `ai_start` | | AI check started (only if `ai_check`, authenticated, return code 0 or warnings, JSON exists) |
| `ai_line` | `text` | AI check output line (not the report) |
| `ai_report` | `report` | parsed `🤖 AI report:` JSON |
| `ping` | | keep-alive every 10 s without output |
| `end` | `package_id?`, `mp3_count?` | last event |

If the connection closes before `end`, the server kills the pipeline/AI check and releases the lock.

## `GET /api/packages/{package_id}`

`200 application/zip` (`<lang>/ftm_<lang>.json`, `<lang>/audios/…`, `<lang>/images/`), `Content-Disposition: attachment`. `410` with a reason when replaced, being regenerated or gone. Hosted: the folder is deleted after the zip is built (one fetch).

## Static

Every other `GET` serves `web/dist/` (`index.html` for unknown paths). If `web/dist` doesn't exist, `/` explains how to build it.
