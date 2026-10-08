# Research: Google Sign-In Restricted to Curious Learning Accounts

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-10-05

Findings come from reading the installed Streamlit 1.64.0 source (`streamlit/auth_util.py` and
`streamlit/web/server/starlette/starlette_auth_routes.py`), plus the existing pipeline code.

---

## R1. How users sign in

- **Decision**: Use Streamlit's built-in login (`st.login("google")`, `st.user`, `st.logout()`),
  configured as Google OIDC in `.streamlit/secrets.toml`.
- **Rationale**: It is already part of the installed Streamlit. It handles the redirect, the
  callback, PKCE and a signed session cookie, so no OAuth code has to be hand-written. Two config
  options make per-user Drive access possible:
  - `client_kwargs.scope` lets the sign-in request Drive and Sheets permissions in addition to
    `openid email profile`.
  - `expose_tokens = "access"` makes the user's Google access token available to the app as
    `st.user.tokens["access"]`.
- **Cost**: it requires **Authlib**, which isn't installed today (`ModuleNotFoundError`). That is
  the only new dependency. It's justified in plan.md → Complexity Tracking.
- **Alternatives considered**:
  - *Hand-written OAuth web flow with `google-auth-oauthlib.Flow`* (no new dependency). Streamlit
    can't set cookies, so the sign-in would be lost on every page reload, and code meant for
    desktop use would need reworking for a web server. Rejected: more security-sensitive code to
    maintain.
  - *Identity-Aware Proxy or another reverse proxy doing the login.* It can restrict the domain,
    but it can't hand the app a per-user Drive token (spec FR-009). The app would still need its
    own login.

## R2. Enforcing curiouslearning.org (FR-002, FR-003)

- **Decision**: After sign-in, admit the user only if all three hold:
  1. `st.user["hd"] == "curiouslearning.org"`. `hd` is the hosted-domain claim Google puts in the
     ID token for Google Workspace accounts.
  2. `st.user["email_verified"]` is true.
  3. The email ends with `@curiouslearning.org`, as a consistency check.

  `client_kwargs.hd = "curiouslearning.org"` also tells Google to suggest Curious Learning
  accounts. That is only a hint and is not relied on.
- **Rationale**: Google documents `hd` as the claim to check for Workspace domain membership.
  Checking the email text alone would accept look-alike addresses. Google's "unverified app"
  screen can be clicked through, so it isn't a control either.
- **Defense in depth (admin action)**: set the OAuth consent screen's User type to
  **Internal**. Google will then refuse non-Curious Learning accounts before they reach the app,
  and the "unverified app" warning goes away for staff. The app check stays in place even so.
- **Alternatives considered**: an allowlist of email addresses. Rejected because the spec wants
  the whole domain.

## R3. Running the pipeline with the user's own Drive access (FR-009)

- **Decision**:
  - The UI passes the user's access token to the `generate_language.py` subprocess through the
    environment variable `FTM_GOOGLE_ACCESS_TOKEN`, together with `FTM_AUTH_MODE=web`.
  - A new helper, `language_automation/google_auth.py`, builds Google credentials. If the token
    variable is set, it uses that token. If `FTM_AUTH_MODE=web` is set but there's no token, it
    fails without touching anything. Otherwise (command-line use) it keeps today's
    `token.json` flow.
  - The two current copies of the sign-in code (`fetch_lang_sheet.get_services` and
    `fetch_drive_audios.get_drive_service`) both call this helper.
- **Rationale**:
  - The environment is visible only to the child process. It isn't on the command line, where
    `ps` would show it, and it isn't written to disk.
  - The command line stays unchanged, as the spec requires.
  - It's one small module, and no other pipeline code needs to know where the token came from.
- **Scopes requested at sign-in**: `openid email profile`,
  `https://www.googleapis.com/auth/drive` and
  `https://www.googleapis.com/auth/spreadsheets.readonly`. These are the same scopes the
  pipeline uses today, so behavior doesn't change. Full `drive` is still needed for the
  Excel-to-Sheet copy. Narrowing it is follow-up work from security finding #3. With an
  **Internal** consent screen, no Google verification is required for these scopes.
- **Alternatives considered**: writing a per-user `token.json`. Rejected because tokens would sit
  on the server's disk (constitution V), and one user's file could be picked up for another
  user's run.

## R4. Token lifetime (no refresh token)

- **Finding**: Streamlit stores only `id_token` and `access_token` in its cookie (see
  `starlette_auth_routes.py`, where `tokens = {k: token[k] for k in ["id_token", "access_token"]}`).
  There is no refresh token. Google access tokens last about 3600 seconds. Streamlit's own login
  cookie lasts 30 days.
- **Decision**:
  - In the "Authenticating…" stage of every submission, check the token with Google's tokeninfo
    endpoint (`https://oauth2.googleapis.com/tokeninfo`, called with the existing `requests`
    dependency). Proceed only if all of these hold:
    - `aud` is our client ID;
    - `email` is the signed-in user;
    - the scopes include Drive;
    - `expires_in` is at least `MIN_TOKEN_SECONDS`, default 1800, tunable after timing real runs
      (R8).
  - Otherwise show "Your Google sign-in has expired, please sign in again". Nothing is created.
  - Separately, treat any login older than 8 hours (the ID token's `iat` claim) as signed out.
    This is spec FR-006.
- **Rationale**: a token that expires mid-run would fail *after* `lang/<Language>/` is wiped,
  which goes against constitution I in spirit. Checking up front keeps every failure before the
  wipe.
- **Consequence (spec amendment A3)**: people have to sign in again roughly once an hour before
  starting a run. Because they're already signed in to Google in the browser, that's one click on
  the account chooser.
- **Alternatives considered**:
  - *Offline access with a refresh token*. Streamlit discards refresh tokens, and storing them
    server-side would need our own OAuth flow (R1, rejected).
  - *Retrying after a 401 mid-run*. Not possible without a refresh token.

## R5. Where sign-in happens in the flow (spec amendments A1, A2)

- **Findings**:
  - `st.login` is a full-page redirect. Google returns to `/oauth2callback`, which then redirects
    to the app's base URL, so a new Streamlit session starts. A language name typed before
    sign-in is lost.
  - On a cancelled *or* failed sign-in, Streamlit redirects to the base URL without passing on
    any error, so the app can't tell the two apart.
- **Decision (revised per user, A1)**:
  1. **The language form is shown first.** On Generate, if the visitor isn't signed in, save a
     **pending request** (`{languages, created}`) in a server-side store, `st.cache_resource`,
     keyed by the browser's `_streamlit_xsrf` cookie (read with `st.context.cookies`). Then call
     `st.login("google")` straight away, which takes the user to Google's login page. No steps are
     drawn.
  2. **After returning**, run "Authenticating…" (domain R2, then token R4), take the pending
     request for this browser, and on ✅ start the steps for those languages automatically.
  3. **Abandoned login** (tab closed, cancelled, never finished): nothing has started, so nothing
     is running or holding the lock. The pending request expires after 10 minutes. If the
     visitor comes back without being signed in, it's discarded and they see "Sign-in was
     cancelled or didn't complete".
  4. **Tab closed during a run**: the run loop checks `Runtime.is_active_session()` every 0.2 s.
     When the tab has closed, it kills the subprocess and releases the lock (FR-001b).
- **Why the cookie works**: `_streamlit_xsrf` is set by the Streamlit server on page load
  (`starlette_routes.py`). It's a browser-session cookie, so it survives the same-tab round trip
  to Google, while `st.session_state` does not. **Verify in implementation**. If it does change
  across the redirect, use a short random ID in the `redirect_uri` state instead, or fall back to
  pre-filling the form.
- **Rationale**: this is exactly the flow the user asked for ("enter a language → take the user to
  the login page"), and no automation step appears before sign-in.

## R5b. Abandoned sign-ins must never block the generator (bug, fixed 2026-10-05)

- **Finding**: in the current app, a run that needs a Google sign-in calls
  `InstalledAppFlow.run_local_server()`, which waits forever. Closing the browser tab doesn't stop
  the Streamlit script, so the subprocess and the one-run lock were held indefinitely and nobody
  could add a language. (Reported by the user.)
- **Fix (already in `app.py`)**:
  - The run loop cancels when the starting tab's session is no longer active
    (`Runtime.instance().is_active_session()`), or when the pipeline has waited more than
    `SIGNIN_TIMEOUT_SECONDS = 180` for a sign-in.
  - On cancel, it kills the subprocess, records the run as `cancelled` ("Nothing was created or
    deleted" if it stopped before the wipe step), stops any remaining comma-separated languages,
    and releases the lock.
- **Verified**:
  - The Streamlit test harness showed the sign-in timeout cancels the run, kills the process and
    frees the lock.
  - In headless Edge, closing the tab during a sign-in wait killed the process, and a new tab
    could start a run immediately with no busy warning.
- **In the new design (R3)** the web flow never calls `run_local_server`. This guard stays as a
  safety net for any run.

## R6. Hosting at a shared URL

- **Decision**: a single small **Linux VM** (Google Compute Engine, `e2-small`) in Curious
  Learning's Google Cloud project:
  - Streamlit runs as a `systemd` service on localhost:8501.
  - **Caddy** sits in front. It provides automatic HTTPS and passes WebSocket traffic through.
  - The VM has a persistent disk for `lang/` and `logs/`.
  - DNS: e.g. `ftm-generator.curiouslearning.org`. The exact name is up to Curious Learning IT.
- **Rationale**:
  - One always-on instance keeps the one-run-at-a-time lock correct.
  - Packages survive restarts.
  - Long runs aren't cut off by request timeouts.
  - `ffmpeg` installs from apt.
  - The cost is around USD 7–15 a month.
- **Alternatives considered**:
  - *Cloud Run*: the disk is temporary, so packages are lost, and there may be several
    instances, which breaks the lock unless max instances is set to 1. Long WebSocket sessions
    are also limited. A reasonable later option once packages are delivered elsewhere.
  - *This Windows PC plus a tunnel*: depends on one laptop being on, and adds a third-party
    tunnel.
  - *Streamlit Community Cloud*: Curious Learning's Drive data would go through third-party
    hosting, and the disk is temporary.
- **Ownership**: the VM, DNS and OAuth client are created by the Curious Learning GCP or Workspace
  admin. The repo ships only deployment files and instructions (`deploy/`).

## R7. Consequences of hosting on Linux

- **Path casing (constitution: technical constraints)**:
  - Today the folder is `lang/<AsTyped>/`, `fetch_lang_sheet` writes `lang/<lower>/ftm_<lower>.json`,
    and the checks read `lang/<AsTyped>/ftm_<AsTyped>.json`. This works only on Windows.
  - **Decision**: one helper, `lang_paths(lang)`, that every module uses. The folder is
    `lang/<lang.lower()>/` and the JSON is `ftm_<lang.lower()>.json`, which matches the lowercase
    URL path the game uses.
  - On Windows nothing visible changes.
- **Getting the package off the server (spec amendment A4)**: the content team can't see the
  server's disk.
  - **Decision**: after a run that completes (with or without errors), offer **"Download language
    package (.zip)"**, built with the standard library's `zipfile`, so no new dependency.
  - **Open question for the user**: is a zip download the right handoff, or should packages be
    uploaded somewhere, such as a Drive folder or the game CDN? A zip is the minimal default.
- **Hosting hardening** (from the 2026-10-05 security review, now more important because many
  people can submit):
  - *#1 Drive file names*: clean them before using them as paths in
    `download_convert_to_mp3` (reuse `INVALID_NAME_CHARS` and take only the base name).
  - *#4 Language names*: allow only letters, digits, spaces, `-` and `_` before any Drive lookup
    or folder operation.
  - *#5 Sheet URL fetch*: `fetch_unity_json` uses `requests.get(url, timeout=…)` and allows only
    `https://`.

## R8. Performance and limits

- **Run duration**: unknown. It must fit inside the token window (R4). **Measure** a large
  language (e.g. Hausa, about 165 files) in implementation, then set `MIN_TOKEN_SECONDS` to that
  run time plus a margin.
- **Concurrency**: one run at a time across all users (existing lock). Sign-in itself works for
  any number of users at once.

## R9. Records (FR-010, FR-011)

- **Decision**: the app appends JSON lines to `language_automation/logs/access.jsonl`, using only
  the standard library. That file is gitignored and stays on the server's persistent disk. The
  events are:
  - `signin_ok`;
  - `signin_refused` (email and `hd`);
  - `run_started` and `run_finished` (email, language, outcome).

  Each run's downloadable log also starts with `👤 Started by: <email>`. The app adds that line
  itself, so the pipeline's log lines are unchanged.
- **Never logged**: access tokens and ID tokens.

## Admin dependencies (outside the repo)

| # | Action | Owner |
|---|---|---|
| D1 | Create an OAuth client of type **Web application** in the Curious Learning GCP project, with redirect URI `https://<host>/oauth2callback` (plus `http://localhost:8501/oauth2callback` for local testing). The existing `credentials.json` is a *desktop* client and can't be used for this. | Curious Learning GCP project admin |
| D2 | Set the OAuth consent screen User type to **Internal**. | Workspace admin |
| D3 | Create the VM, open ports 80 and 443, and add a DNS record for the host name. | GCP / IT admin |
| D4 | Confirm each content team member's account can read the language sheets folder and the audio root folder. | Drive owners |
