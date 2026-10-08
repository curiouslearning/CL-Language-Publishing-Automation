# Contract: How the Pipeline Gets Google Access

The new module `language_automation/google_auth.py` is the **only** place that builds Google
credentials. `fetch_lang_sheet.get_services()` and `fetch_drive_audios.get_drive_service()`
delegate to it.

## Inputs (environment variables, set by `app.py` on the subprocess only)

| Variable | Values | Meaning |
|---|---|---|
| `FTM_AUTH_MODE` | `web` or unset | `web` means the run was started from the hosted page. |
| `FTM_GOOGLE_ACCESS_TOKEN` | Google OAuth access token | The signed-in user's token. Required when `FTM_AUTH_MODE=web`. |

## Behavior

| `FTM_AUTH_MODE` | Token set? | Result |
|---|---|---|
| `web` | yes | The credentials are built from that token only. `token.json` and `credentials.json` are never read or written. |
| `web` | no | Prints `❌ Not signed in: no Google access token was provided.` and exits 1. This happens before `verify_language_on_drive`, so nothing is touched. |
| unset | (ignored) | Today's command-line behavior: `token.json`, or the browser OAuth flow with `credentials.json`. Unchanged. |

If a Google call returns 401 or 403 in `web` mode, the pipeline prints
`❌ Google access was refused for this account.` and exits 1. Because Stage B checked the token
first, this should only happen if the user's Drive permissions are missing, and the pre-check then
fails before any wipe.

## Server secrets (`language_automation/.streamlit/secrets.toml`, gitignored, not committed)

```toml
[auth]
redirect_uri  = "https://<host>/oauth2callback"
cookie_secret = "<random 32+ bytes>"
expose_tokens = "access"

[auth.google]
client_id     = "<web client id>"
client_secret = "<web client secret>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
client_kwargs = { scope = "openid email profile https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/spreadsheets.readonly", hd = "curiouslearning.org", prompt = "select_account" }
```
