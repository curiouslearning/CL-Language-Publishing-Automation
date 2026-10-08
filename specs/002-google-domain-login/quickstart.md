# Quickstart & Validation: Google Sign-In Restricted to Curious Learning Accounts

**Plan**: [plan.md](plan.md) · **Stages**: [contracts/auth-states.md](contracts/auth-states.md) ·
**Pipeline**: [contracts/pipeline-auth.md](contracts/pipeline-auth.md)

## Prerequisites

1. **Admin dependency D1** (see [research.md](research.md#admin-dependencies-outside-the-repo)):
   an OAuth client of type *Web application* with redirect URI
   `http://localhost:8501/oauth2callback` for local testing.
2. Install the dependencies from the repo's new `requirements.txt` (adds `Authlib`), and make sure
   `ffmpeg` is on PATH.
3. Create `language_automation/.streamlit/secrets.toml` as shown in the pipeline contract, with
   `redirect_uri = "http://localhost:8501/oauth2callback"`.
4. Have two test accounts ready: **A**, a `curiouslearning.org` account with Drive access, and
   **B**, any other account (e.g. `@sutara.org` or Gmail).

## Run locally

```bash
cd language_automation
python -m streamlit run app.py
```

## Validation scenarios

Before each refusal scenario, snapshot the language folders so you can show nothing changed:

```powershell
Get-ChildItem -Recurse lang | Get-FileHash | Out-File $env:TEMP\before.txt
# … run the scenario …
Get-ChildItem -Recurse lang | Get-FileHash | Out-File $env:TEMP\after.txt
Compare-Object (gc $env:TEMP\before.txt) (gc $env:TEMP\after.txt)   # expect no output
```

| # | Scenario | Steps | Expected |
|---|---|---|---|
| V1 | Not signed in | Private window: type `Hausa`, press Generate. | Taken straight to Google's login page. No steps were drawn. |
| V2 | Allowed account (US1) | Continue V1 by signing in as **A**. | Back on the generator: "Authenticating…", then ✅ "Signed in as A", then Steps 1–7 for **Hausa** with no retyping, and the run completes. The log's first line is `👤 Started by: A`. The zip download is offered. |
| V2b | Login tab closed | Private window: type `Hausa`, Generate, then **close the tab** on Google's login page. Open the generator in a new tab and generate `Hindi` as **A**. | The `Hindi` run starts right away with no busy warning. Nothing was created for Hausa. |
| V2c | Generator tab closed mid-run | Start a run as **A**, then close the tab during Step 5. Open a new tab and start another language. | The first run is recorded as cancelled ("lang/hausa may be incomplete…"). The new run starts right away. |
| V3 | Refused account (US2) | Private window. Sign in as **B**, clicking through Google's "unverified app" warning if it's shown. | ❌ `refused` message and **Use a different account**. No form. The folder snapshot is unchanged, and no `_converted` sheet copy appears on Drive. `logs/access.jsonl` has a `signin_refused` line for B. |
| V4 | Cancelled sign-in | Click Sign in, then close or cancel the Google page. | `cancelled` message plus the button. The snapshot is unchanged. |
| V5 | Expired token | Sign in as **A**, wait until the token has less than `MIN_TOKEN_SECONDS` left (or set it to 3599 temporarily), then press Generate. | ❌ `expired` + **Sign in again**. No steps shown. The snapshot is unchanged. |
| V6 | Allowed account without Drive access | Use a `curiouslearning.org` account that can't see the language folders. | Sign-in is ✅. The run stops at Step 1 with "not found on Google Drive". The snapshot is unchanged. |
| V7 | Busy | While V2 is running, submit from a second browser as another allowed account. | The existing "another language is being generated" message. Nothing is created for the second user. |
| V8 | Sign out | Press **Sign out**, then Generate again. | Same as V1: straight to Google's login page. |
| V9 | Command line unchanged | `python generate_language.py Hausa` with `FTM_AUTH_MODE` unset. | It behaves exactly as before, using `token.json`. |
| V10 | Web mode without a token | `$env:FTM_AUTH_MODE='web'; python generate_language.py Hausa` | `❌ Not signed in…`, exit code 1, snapshot unchanged. |
| V11 | Invalid language name | Submit `..\..` or `Hausa/x`. | Rejected before any Drive call. Snapshot unchanged. |
| V12 | Linux casing | On the VM, generate `Hausa`. | `lang/hausa/ftm_hausa.json` exists. The unused and missing audio checks run, and their results match a Windows run. |
| V13 | Run timing (R8) | Time V2 for the largest language. | Record it. Set `MIN_TOKEN_SECONDS` to that time plus a margin. |

## Deploy (shared URL)

Follow `deploy/README.md`, which implementation will create:
1. Set up the VM and install `python3`, `ffmpeg` and Caddy.
2. Copy the repo there and install the requirements.
3. Create `secrets.toml` with `redirect_uri = "https://<host>/oauth2callback"`.
4. Enable the `systemd` service.
5. Point the Caddyfile at the host.
6. Repeat V1–V8 and V12 against the shared URL.
