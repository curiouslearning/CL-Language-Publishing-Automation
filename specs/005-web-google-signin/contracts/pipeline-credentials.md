# Contract: Credentials for the Pipeline Scripts

Every Google client in `generate_language.py`, `fetch_lang_sheet.py`, `fetch_drive_audios.py` and `run_unity_check.py` is built from `google_auth.load_credentials()`.

## Inputs (environment)

| Variable | Set by | Format |
|---|---|---|
| `FTM_GOOGLE_CREDENTIALS` | `app.py`, for the pipeline subprocess only | JSON authorized-user info: `{"token", "refresh_token", "token_uri", "client_id", "client_secret", "scopes", "expiry"}` (the same shape as `Credentials.to_json()`) |
| `FTM_HOSTED` | container image (`ENV FTM_HOSTED=1`) | `1` means a hosted server |

## Resolution order

1. **`FTM_GOOGLE_CREDENTIALS` set:**
   - Build credentials from it.
   - If expired, refresh in memory.
   - Never write it to disk.
   - Malformed, or the refresh fails → `❌ Authentication failed: the Google sign-in for this run is invalid or expired.` and exit 1.
2. **Else `FTM_HOSTED=1`:** `❌ Authentication failed: no Google sign-in was provided for this run.` and exit 1. No `token.json`, no desktop flow.
3. **Else (developer command line):** unchanged.
   - `token.json` if valid.
   - Else the `InstalledAppFlow.run_local_server` sign-in using `credentials.json`, saved to `token.json`.

All of these exit before Step 0 (`verify_language_on_drive`), so nothing is created or deleted (constitution I).

## Scopes

*Changed during implementation (2026-10-09): two sets, not one.* Refreshing a token with more scopes than it was granted fails with `invalid_scope`, so a single wider set would break every existing `token.json`.

- **Web sign-in** (`google_auth.WEB_SCOPES`): `openid`, `https://www.googleapis.com/auth/userinfo.email`, `https://www.googleapis.com/auth/drive`, `https://www.googleapis.com/auth/spreadsheets.readonly`. `FTM_GOOGLE_CREDENTIALS` carries the scopes actually granted, and the scripts use exactly those.
- **Command line** (`google_auth.CLI_SCOPES`): `https://www.googleapis.com/auth/drive`, `https://www.googleapis.com/auth/spreadsheets.readonly`, which is what `token.json` has always been granted. Existing `token.json` files keep working.

## Output (stdout, unchanged public contract)

- `🔐 Authenticating with Google...`
- `✅ Authenticated as <email>`: email from Drive `about.user.emailAddress`, re-checked against `@curiouslearning.org`.
- On a domain mismatch: today's `❌ Only Curious Learning (curiouslearning.org) accounts can generate languages. Signed in as <email>.` + `❌ Nothing was created or deleted.`, exit 1. `token.json` is deleted only in command-line mode.

## Not passed

`ai_language_check.py` never receives `FTM_GOOGLE_CREDENTIALS`. It doesn't call Google Drive.
