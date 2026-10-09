# Research: Per-Person Web Google Sign-In for the Generator

All Technical Context unknowns are resolved below. Each entry gives the decision, the rationale and the alternatives considered.

> **Scope change (2026-10-09)**: hosting is out of scope. R8 (Cloud Run) and R10 (zip download) are kept only as notes for the separate hosting work. R11's "https" rule applies only once `FTM_HOSTED=1` is set by that work.

## R1. Which OAuth flow replaces `run_local_server`

- **Decision**: the OAuth 2.0 **web server flow** with a **Web application** OAuth client.
  - `google_auth_oauthlib.flow.Flow.from_client_config(..., redirect_uri=FTM_PUBLIC_URL)`, with PKCE (`code_verifier`).
  - Authorization-URL parameters:
    - `access_type=offline` and `prompt="select_account consent"`, so a refresh token is always returned and the account chooser always shows (FR-007);
    - `include_granted_scopes=false`;
    - `hd=curiouslearning.org` as a hint only;
    - a random `state`.
- **Rationale**:
  - `run_local_server` redirects to `localhost` on the *server*, so it can never complete for a remote browser.
  - The web flow redirects to the app's public URL.
  - `Flow` is already installed with `google-auth-oauthlib`.
- **Alternatives**:
  - `st.login`: needs Authlib, puts login state in a cookie that outlives the tab, and was removed at the user's request (spec 002).
  - Device-code flow: Drive scopes aren't allowed on it.
  - IAP + service account (option A): rejected by the user.

## R2. Where the sign-in completes, and how the waiting session learns about it

- **Decision**: the sign-in opens in a **new tab** (`st.link_button`). Google redirects that tab to the app URL with `?code&state`. On load, `app.py` checks `st.query_params` and runs **callback mode** only; the generator form isn't drawn. Callback mode:
  1. Looks up `state` in a process-wide **pending store** (`st.cache_resource` dict guarded by a lock).
  2. Exchanges the code with the stored `code_verifier`.
  3. Verifies the ID token (R3).
  4. Writes the outcome into the pending entry.
  5. Clears the query params.
  6. Shows "Signed in as <email>. Return to the generator tab", or the refusal.

  The originating session is already polling inside `run_pipeline`'s sign-in stage (same 0.2 s loop, same 3-minute timeout, same tab-closed check). It **pops** the entry, so it can be used once only.
- **Rationale**:
  - Redirecting the generator tab itself would drop its Streamlit session: the typed language, the queue and the history.
  - A new tab keeps today's "open the sign-in page" experience.
  - Popups opened from a rerun are blocked by browsers, so the user must click the button.
- **Alternatives**: same-tab redirect with the language kept in the URL. Rejected: the history is lost, and the language name ends up in browser history.

## R3. Admission rule (curiouslearning.org only)

- **Decision**: after the token exchange:
  - `google.oauth2.id_token.verify_oauth2_token(creds.id_token, Request(), client_id)` checks the signature, `iss`, `aud` and `exp`.
  - Admit only when `email_verified is True` **and** `hd == "curiouslearning.org"` **and** `email.lower().endswith("@curiouslearning.org")`.
  - Anything else → `refused`.
  - The pipeline's existing `authenticate()` still re-checks Drive's `about.user.emailAddress` (defence in depth).
- **Rationale**:
  - `hd` is set only for accounts managed by that Workspace organization. That defeats look-alike addresses and Gmail accounts using a `curiouslearning.org` alias.
  - Signature verification stops forged tokens.
  - The `hd=` parameter in the URL is only a UI hint, which is why the check happens afterwards (FR-005).
- **Alternatives**: the email suffix alone, as today. It's weaker: a consumer account can register a third-party address, though not with `hd`.

## R4. Binding a sign-in to the session and browser that started it (FR-003)

- **Decision**: three guards. When Generate starts a sign-in, the session creates:
  - `state` (32 random bytes, URL-safe), the key into the pending store;
  - a `browser_nonce`, set as cookie `ftm_signin=<nonce>; Path=/; SameSite=Lax; Max-Age=600` (plus `Secure` on https). It is set by a fixed `st.html(..., unsafe_allow_javascript=True)` script in the same render that shows the button. The page already uses that mechanism for focus.

  The callback rejects the attempt unless all of these hold:
  - the `state` exists, is still pending, and is less than 3 minutes old;
  - `st.context.cookies["ftm_signin"]` equals the stored nonce;
  - the originating `session_id` is still active.

  A rejected callback marks the entry `failed` with "sign-in must be completed in the same browser".
- **Rationale**: the copied-link edge case in the spec. A link pasted into another browser lacks the cookie. A reused link finds no pending entry.
- **Verification in implementation (T001, 2026-10-09): cookie guard feasible.** From the installed Streamlit 1.64.0 source: `st.context.cookies` returns "cookies sent in the initial request", i.e. the session's websocket handshake (`runtime/context.py`); and `st.html` content "is **not** iframed" (`elements/html.py`), so a script run with `unsafe_allow_javascript=True` writes `document.cookie` for the app's own origin. The callback tab is a new page load and a new session, so its handshake carries a `Path=/` cookie set earlier by the generator tab in the same browser. Browser-level confirmation is quickstart V8.
- **Alternatives**: a signed server cookie. Not possible from Streamlit script code.

## R5. Where a person's sign-in lives (FR-008/FR-009)

- **Decision**: keep `credentials.to_json()`-equivalent authorized-user info in `st.session_state["google_signin"] = {email, info, at}`. It is never written to disk.
  - It dies with the session: tab closed or reloaded (a new session) or a restart.
  - Each pipeline subprocess gets it as the env var `FTM_GOOGLE_CREDENTIALS` (JSON).
  - The AI-check subprocess env does **not** include it.
- **Rationale**: per-person, not shareable across sessions, and nothing survives a restart (SC-006). On Cloud Run the container is single-tenant, so a child's env is visible only to the same process tree.
- **Alternatives**:
  - A per-run temp token file: it lands on disk, even if briefly.
  - Passing only an access token: it expires after 1 h, breaking long runs (edge case). The refresh token plus client id/secret let `google-auth` refresh by itself.

## R6. Scripts' credential loading (`google_auth.py`)

- **Decision**: `load_credentials(scopes)` works as follows:
  1. If `FTM_GOOGLE_CREDENTIALS` is set → `Credentials.from_authorized_user_info(json, scopes)`, refreshing if needed. Invalid JSON or a failed refresh → raise, with no fallback.
  2. Else if `FTM_HOSTED=1` → raise "no Google sign-in for this run" (fail closed, FR-011).
  3. Else → today's behaviour: `token.json`, else `InstalledAppFlow.run_local_server`, then save to `token.json` (CLI, FR-014).

  `fetch_lang_sheet.get_services`, `fetch_drive_audios.get_drive_service` and `run_unity_check.get_sheets_service` all call it. One scope set for every client: `openid`, `userinfo.email`, `drive`, `spreadsheets.readonly`.
- **Rationale**:
  - A single loader removes three copies of the desktop flow.
  - One scope set avoids the CLI's current behaviour of building Drive clients with a narrower scope than the token holds.
- **`FTM_HOSTED`**: this feature only defines the switch. Setting it on a server belongs to the separate hosting work.
- **Alternatives**: separate code paths per script. More places for the server to fall back to `token.json` by accident.

## R7. Web client configuration and redirect URI

- **Decision**: in Curious Learning's Google Cloud project:
  - an OAuth client of type **Web application**;
  - consent screen user type **Internal**;
  - authorized redirect URIs `https://<cloud-run-url>/` and `http://localhost:8501/`.

  The app reads:
  - `FTM_OAUTH_CLIENT_FILE` (default `client_secret_web.json` in `language_automation/`, already gitignored by `client_secret*.json`);
  - `FTM_PUBLIC_URL` (default `http://localhost:8501/`).

  Missing or unreadable → setup error, and no run (FR-011). For `http://localhost` only, the app sets `OAUTHLIB_INSECURE_TRANSPORT=1`. It always sets `OAUTHLIB_RELAX_TOKEN_SCOPE=1`, because Google returns scopes in a different order.
- **Rationale**:
  - **Internal** limits the client to curiouslearning.org at Google's side.
  - It also avoids Google's verification of the restricted `drive` scope, which an External app would need.
- **Alternatives**: External + testing mode. Limited to 100 listed test users, with 7-day refresh tokens.

## R8. Hosting platform and settings (DEFERRED: out of scope)

> **Not implemented in this feature.** The user is handling hosting separately. This entry is kept
> as input for that work only.

- **Decision**: **Cloud Run**, deployed with `gcloud run deploy --source .`, using the repo `Dockerfile` and built by Cloud Build. Settings:
  - `--min-instances 0 --max-instances 1`
  - `--cpu 1 --memory 2Gi`
  - `--timeout 3600 --session-affinity`
  - `--allow-unauthenticated` (the app does its own sign-in)
  - request-based billing (default)
  - `--set-secrets` for the web client file and the AI keys
  - `--set-env-vars FTM_HOSTED=1,FTM_PUBLIC_URL=...,FTM_OAUTH_CLIENT_FILE=/secrets/client_secret_web.json`

  Streamlit command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true`.
- **Rationale**:
  - Scales to zero.
  - The websocket counts as an active request, so the CPU stays allocated during a run while the tab is open. The run is cancelled anyway when the tab closes.
  - Max 1 instance keeps the in-process lock valid.
  - The free tier (≈180k vCPU-s / 360k GiB-s a month) covers ≈50 page-open hours at 1 vCPU / 2 GiB.
- **Known limits (documented)**:
  - A websocket is cut at 60 min, and Streamlit reconnects.
  - During a deploy, an old and a new revision can overlap briefly. Don't deploy mid-run.
  - An org policy blocking `allUsers` would require IAP in front. Escalate to Curious Learning IT if `--allow-unauthenticated` is refused.
- **Alternatives**:
  - A Compute Engine VM: always billed.
  - Streamlit Community Cloud: third-party host for Drive tokens.
  - App Engine Flex: no scale to zero.

## R9. Dependencies

- **Decision**: no new packages.
  - `Flow`, `Credentials.from_authorized_user_info` and `id_token.verify_oauth2_token` come from the already pinned `google-auth-oauthlib` and `google-auth`.
  - `requests` provides the transport.
  - ffmpeg comes from `apt` in the image.
- **Rationale**: constitution, technical constraints.

## R10. Getting output off a temporary server (DEFERRED: out of scope)

> **Not implemented in this feature** (spec, Out of Scope). Kept as input for the hosting work.

- **Decision**: after a run whose state is `complete` or `warning`:
  - zip `lang/<lang>/` with `shutil.make_archive` into a temp dir outside `lang/`;
  - offer it through `st.download_button("Download language package (.zip)", on_click="ignore")`;
  - name it `<lang>_<timestamp>.zip`;
  - keep the path in the run result. The file is deleted when the session's history drops it, or on restart.
- **Rationale**: the team can't reach the container's filesystem. `on_click="ignore"` keeps the "no rerun mid-run" rule from spec 004.
- **Alternatives**: uploading to a Drive folder. That writes to Drive, which this tool never does today, so it's out of scope.

## R11. Fail-closed behaviour

- **Decision**: the app shows a top-of-page setup error and disables Generate when:
  - the web client config is missing or invalid; or
  - `FTM_HOSTED=1` and `FTM_PUBLIC_URL` isn't https.

  The pipeline in hosted mode refuses to run without `FTM_GOOGLE_CREDENTIALS` (R6).
- **Rationale**: FR-011 and the spec edge case "settings missing".

## R12. What stays the same for the command line

- **Decision**: `python generate_language.py X` on a developer machine, with no env vars set, uses the `token.json`/desktop flow and the same email-domain check (FR-014). `token.json` is still deleted on refusal.
- **Rationale**: developers keep their workflow. The hosted server can't reach that path, because `FTM_HOSTED=1`.
