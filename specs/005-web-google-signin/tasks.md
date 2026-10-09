---

description: "Task list for per-person web Google sign-in in the generator"
---

# Tasks: Per-Person Web Google Sign-In for the Generator

**Input**: Design documents from `specs/005-web-google-signin/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/web-signin.md, contracts/pipeline-credentials.md, quickstart.md

**Tests**: No automated test suite exists (constitution). Each phase ends with the manual quickstart scenarios it enables; the constitution's required real-language run is T029.

**Scope**: sign-in only. No hosting files (Dockerfile, Cloud Run, deploy docs, zip download) may be added by any task here; the user handles hosting separately (spec, Out of Scope).

**Organization**: Tasks are grouped by user story so each story can be implemented and checked on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on an unfinished task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Every path is relative to the repository root

## Path Conventions

All code lives in `language_automation/` (constitution). Scripts run with that folder as CWD. New modules: `language_automation/google_auth.py` (credential loader for the scripts) and `language_automation/web_signin.py` (web OAuth flow, used only by `app.py`).

---

## Phase 1: Setup

**Purpose**: Resolve the one open design question and secure the prerequisite the manual checks depend on.

- [X] T001 Spike (research R4): confirm whether `st.context.cookies` on the installed Streamlit 1.64.0 can read a cookie set by a fixed `st.html(..., unsafe_allow_javascript=True)` script in the same browser. Use a throwaway script in the scratchpad directory (not in the repo). Record the outcome in `specs/005-web-google-signin/research.md` under R4: either "cookie guard feasible" or "fallback: state + 3-minute expiry + single use", and in the fallback case add a one-line known limitation to the "Sign-in completes in a different browser" edge case in `specs/005-web-google-signin/spec.md`.
- [X] T002 [P] (Developer, with their `curiouslearning.org` account; see quickstart Prerequisites) Create a new Google Cloud project inside the curiouslearning.org organisation, enable the Drive and Sheets APIs, set the OAuth consent audience to **Internal**, create a **Web application** OAuth client with redirect URI `http://localhost:8501/`, download its JSON and save it as `language_automation/client_secret_web.json`. Confirm `git status` doesn't list it (`.gitignore` already matches `client_secret*.json`). This blocks only the manual checks (T016, T019, T024, T029), not the coding tasks.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: One credential loader for every script, and the web OAuth module. No user story works until these exist.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Create `language_automation/google_auth.py` per contracts/pipeline-credentials.md: `SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets.readonly"]`; `class AuthError(Exception)`; `is_hosted()` → `os.environ.get("FTM_HOSTED") == "1"`; `load_credentials(scopes=SCOPES)` with this exact resolution order: (1) `FTM_GOOGLE_CREDENTIALS` set → `Credentials.from_authorized_user_info(json.loads(...), scopes)`, refresh with `google.auth.transport.requests.Request()` if expired, never write to disk; malformed JSON or failed refresh → `AuthError("the Google sign-in for this run is invalid or expired")`; (2) else `is_hosted()` → `AuthError("no Google sign-in was provided for this run")`; (3) else today's behaviour: `token.json` if valid, else `InstalledAppFlow.from_client_secrets_file("credentials.json", scopes).run_local_server(port=0)` and save to `token.json`. Also `uses_token_file()` → True only in case (3), so callers know whether deleting `token.json` is meaningful.
- [X] T004 Edit `language_automation/fetch_lang_sheet.py`: `get_services()` builds `drive` and `sheets` from `google_auth.load_credentials()`; keep the return shape (`(drive_service, sheets_service)` or `False`) and the `✅ Services initialized successfully` line; on `AuthError` print `❌ Failed to initialize services: <message>` and return `False`. Remove the now-unused `InstalledAppFlow`/`Credentials` imports and the local `SCOPES`.
- [X] T005 [P] Edit `language_automation/fetch_drive_audios.py`: `get_drive_service()` builds the Drive client from `google_auth.load_credentials()`; remove the local `SCOPES`, `InstalledAppFlow` and `Credentials` imports and the `token.json` read/write.
- [X] T006 [P] Edit `language_automation/run_unity_check.py`: replace `get_sheets_service()`'s own `InstalledAppFlow.run_local_server` with `build('sheets', 'v4', credentials=google_auth.load_credentials())`; remove the local `SCOPES` and the `InstalledAppFlow` import. `read_unity_url_from_sheet` is unchanged.
- [X] T007 Edit `language_automation/generate_language.py` `authenticate()`: keep the exact lines `🔐 Authenticating with Google...` and `✅ Authenticated as <email>`; wrap `get_services()`/`get_drive_service()` so an `AuthError` (or `False` from `get_services`) prints `❌ Authentication failed: <message>` and `❌ Nothing was created or deleted.` then `sys.exit(1)`; keep the `@curiouslearning.org` re-check on `about.user.emailAddress` with its current two `❌` lines; delete `token.json` on refusal **only** when `google_auth.uses_token_file()` is True (never when credentials came from `FTM_GOOGLE_CREDENTIALS` or when hosted). All of this still runs before `verify_language_on_drive` (constitution I).
- [X] T008 Create `language_automation/web_signin.py` part 1 (config): `class SetupError(Exception)`; `ALLOWED_DOMAIN = "curiouslearning.org"`; `load_client_config()` reads the path in `FTM_OAUTH_CLIENT_FILE` (default `client_secret_web.json`, relative to the module's folder) and `FTM_PUBLIC_URL` (default `http://localhost:8501/`), returns `{"client_config": <parsed json>, "redirect_uri": <url>}`; raise `SetupError` with one of these exact reasons: `"<path> is missing"`, `"<path> can't be read"`, `"<path> isn't a Web application OAuth client (no web.client_id / web.client_secret)"`, `"FTM_PUBLIC_URL must be https when FTM_HOSTED=1"`. Set `os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"]="1"` always and `OAUTHLIB_INSECURE_TRANSPORT="1"` only when the redirect URI starts with `http://localhost`.
- [X] T009 `language_automation/web_signin.py` part 2 (pending store and start), per data-model.md `PendingSignIn`: `pending_store()` decorated `@st.cache_resource` returning `{"lock": threading.Lock(), "entries": {}}`; `SIGNIN_TIMEOUT_SECONDS = 180`; `start_signin(session_id)` creates an entry keyed by `state = secrets.token_urlsafe(32)` with fields `session_id`, `browser_nonce = secrets.token_urlsafe(16)`, `code_verifier`, `created = time.monotonic()`, `status = "pending"`, `email = None`, `credentials_info = None`, `reason = None`, and returns `(state, browser_nonce, auth_url)`. Build `auth_url` with `google_auth_oauthlib.flow.Flow.from_client_config(client_config, scopes=google_auth.SCOPES, redirect_uri=...)` and `flow.authorization_url(state=state, access_type="offline", prompt="select_account consent", include_granted_scopes="false", hd=ALLOWED_DOMAIN)` with PKCE enabled (`flow.code_verifier` stored). `expire_old()` removes every entry older than 180 s whenever the store is touched. `get_status(state)` returns the entry's status without consuming it.
- [X] T010 `language_automation/web_signin.py` part 3 (callback and admission), per contracts/web-signin.md "Callback": `admit(claims)` returns `(True, email)` only when `claims.get("email_verified") is True` **and** `claims.get("hd") == ALLOWED_DOMAIN` **and** `claims["email"].lower().endswith("@" + ALLOWED_DOMAIN)`, else `(False, email_or_None)`; `handle_callback(params, cookie_value, session_is_active)` → returns `(kind, message)` where `kind ∈ {"unknown", "failed", "refused", "success"}` and `message` is the exact callback-tab text from the contract table. Order of checks: unknown/expired/non-pending state → `"unknown"`; cookie guard (per T001 outcome) → `failed`; originating session not active → `failed` and the entry removed; `error` param → `failed`; `flow.fetch_token(code=..., code_verifier=...)` then `google.oauth2.id_token.verify_oauth2_token(creds.id_token, Request(), client_id)` → any exception → `failed` with "Sign-in failed. Please try again." (log the exception class and message to stderr only, never tokens); then `admit()` → `refused` or `success` with `credentials_info = json.loads(creds.to_json())`. The entry's `status`, `email`, `credentials_info`, `reason` are set under the lock.

**Checkpoint**: `python generate_language.py Hausa` from the command line still behaves exactly as before (desktop flow / `token.json`). With `FTM_HOSTED=1` and no `FTM_GOOGLE_CREDENTIALS` it exits 1 with "no Google sign-in was provided for this run" before Step 0.

---

## Phase 3: User Story 1 - A Curious Learning person signs in and adds a language (Priority: P1) 🎯 MVP

**Goal**: Pressing Generate shows "Authentication in progress" + a **Sign in with Google** button; after a successful sign-in in a new tab the generator tab shows "Authenticated as <email>" and the run continues for the typed language; later runs in the same page session don't ask again.

**Independent Test**: quickstart V1 and V2 locally with a `@curiouslearning.org` account.

### Implementation for User Story 1

- [X] T011 [US1] Edit `language_automation/app.py`: add **callback mode** right after `st.set_page_config(...)`: if `"code" in st.query_params or "error" in st.query_params`, call `web_signin.handle_callback(dict(st.query_params), <cookie value or None>, session_is_active=lambda sid: Runtime.instance().is_active_session(sid))`, show the returned message with `st.success` for `success` and `st.error` otherwise, then `st.query_params.clear()` and `st.stop()` so the generator form is never drawn in that tab.
- [X] T012 [US1] Edit `language_automation/app.py`: **setup check** at page load (before the form): `try: SIGNIN_CONFIG = web_signin.load_client_config() except web_signin.SetupError as e: st.error(f"Google sign-in isn't set up on this server: {e}. No language can be generated."); SIGNIN_CONFIG = None`. Treat `SIGNIN_CONFIG is None` as `busy` for the text input, the Generate button and the AI toggle, and never acquire the lock or start a run while it is None (FR-011).
- [X] T013 [US1] Edit `language_automation/app.py` `run_pipeline()`: add the **sign-in stage** before `subprocess.Popen`. If `st.session_state.get("google_signin")` is missing: `state, nonce, url = web_signin.start_signin(ctx.session_id)`; set `ui["auth"]` to the warning text from contracts/web-signin.md "Starting a sign-in"; render `st.link_button("Sign in with Google", url)` in `auth_box`'s place plus a fixed `st.html` script that sets `ftm_signin=<nonce>; Path=/; SameSite=Lax; Max-Age=600` (append `; Secure` when `FTM_PUBLIC_URL` is https); then loop every `REFRESH_SECONDS` until `web_signin.get_status(state)` is final, `SIGNIN_TIMEOUT_SECONDS` elapses (→ existing cancel path, reason "Google sign-in wasn't completed"), or `not session_is_open()` (→ existing cancel path, "The browser tab was closed"). On `success`: `web_signin.pop_result(state, ctx.session_id)` and set `st.session_state.google_signin = {"email": ..., "info": credentials_info, "at": <now>}`. Keep the existing cancelled rendering (`⏹️ Authentication cancelled: … Nothing was created or deleted.`) and return the result without starting the subprocess.
- [X] T014 [US1] Edit `language_automation/app.py` `run_pipeline()`: when the session is signed in, start the pipeline subprocess with `env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", FTM_GOOGLE_CREDENTIALS=json.dumps(st.session_state.google_signin["info"]))`; set `result["account"] = st.session_state.google_signin["email"]`. The pipeline's own `✅ Authenticated as` line still gates the steps and log (FR-010, FR-015). Do **not** add `FTM_GOOGLE_CREDENTIALS` to `run_ai_check`'s env.
- [X] T015 [US1] Edit `language_automation/app.py` text: update the page caption (`st.caption`) to say the sign-in opens in a new tab; update the `pipeline_lock()` comment (runs no longer "share token.json"); update the `AUTH_DONE` comment (sign-in is now the web flow). Leave `SIGNIN_PROMPT` handling in place (harmless for CLI wording).
- [ ] T016 [US1] Manual check: run quickstart V1 and V2 locally (`cd language_automation && python -m streamlit run app.py`) with a `@curiouslearning.org` account; confirm the generator tab shows the steps only after "Authenticated as", and the second language asks for no new sign-in. Record the result in `specs/005-web-google-signin/quickstart.md` (a "Result" column or a note under the table).

**Checkpoint**: A Curious Learning person can generate a language through the web sign-in. (Not shippable alone: until Phase 4's refusal UI is in place, a refused account is handled only by the pipeline's defence-in-depth check.)

---

## Phase 4: User Story 2 - Only curiouslearning.org accounts may add a language (Priority: P1)

**Goal**: Any account that isn't a verified, `curiouslearning.org`-managed Google account sees "Authentication failed" with the reason, no step runs, nothing is created, and the person can retry with another account.

**Independent Test**: quickstart V3, V4 and V5 locally with a personal Gmail account and a `@sutara.org` account; `lang/` and Drive unchanged (SC-003).

### Implementation for User Story 2

- [X] T017 [US2] Edit `language_automation/app.py` `run_pipeline()` sign-in stage: on `refused` set `result["state"] = "error"`, `result["authenticated"] = False`, `result["auth_reason"] = "only Curious Learning (curiouslearning.org) accounts can add languages (signed in as <email>)"`, render `ui["auth"] = ("error", "❌ Authentication failed: <auth_reason>. Nothing was created or deleted.")`, add that line to `result["log"]` and `result["errors"]`, set `status.update(label=f"**{lang}** · Authentication failed", state="error")`, and return without starting the subprocess. On `failed` do the same with the callback's reason ("sign-in was cancelled or didn't complete" or "sign-in failed"). The existing loop in the page body (`if res["state"] in ("cancelled", "error") and not res["authenticated"]: break`) already stops the remaining queued languages; keep it.
- [X] T018 [US2] Edit `language_automation/app.py`: on `refused`/`failed` ensure `st.session_state.pop("google_signin", None)` so the next Generate starts a fresh `start_signin()`; the auth URL's `prompt="select_account consent"` (T009) is what shows Google's account chooser (FR-007). Make sure `render_summary(result)` copes with a result that has no steps and `authenticated=False` (it already does for the current "Authentication failed" path; verify, don't rewrite).
- [ ] T019 [US2] Manual check: quickstart V3 (personal Gmail), V4 (`@sutara.org`), V5 (retry → account chooser → Curious Learning account succeeds). After V3 and V4 confirm `language_automation/lang/` is unchanged and no `_converted` sheet appeared on Drive. Record results in `specs/005-web-google-signin/quickstart.md`.

**Checkpoint**: US1 + US2 together are the shippable minimum: only Curious Learning accounts get past "Authentication in progress".

---

## Phase 5: User Story 3 - Each person's run uses only their own Google access (Priority: P1)

**Goal**: A sign-in belongs to one page session only, is consumed once, can't be completed from another browser, never reaches disk or another process, and doesn't survive a reload or a restart.

**Independent Test**: quickstart V6–V12 locally with two Curious Learning accounts and two browsers.

### Implementation for User Story 3

- [X] T020 [US3] Edit `language_automation/web_signin.py`: enforce **single use and session binding** per data-model.md rules: `pop_result(state, session_id)` returns the entry only when `entry["session_id"] == session_id` and the status is final, and **deletes** it from the store in the same locked section; `handle_callback` treats a non-`pending` entry as `"unknown"` ("This sign-in link has already been used or has expired…"); an entry whose originating session is no longer active (`session_is_active(entry["session_id"])` False) is removed and reported as `failed`.
- [X] T021 [US3] Edit `language_automation/web_signin.py` and `language_automation/app.py`: apply the **browser guard** according to T001's outcome. If feasible: `handle_callback` compares `cookie_value` (from `st.context.cookies.get("ftm_signin")`, passed in by `app.py`) with `entry["browser_nonce"]` and returns `failed` with "Please complete the sign-in in the same browser where you pressed Generate." on mismatch. If not feasible: skip the cookie comparison, leave the cookie-setting script out of T013, and make sure research R4 and the spec edge case already say so (done in T001).
- [X] T022 [US3] Audit `language_automation/google_auth.py`, `fetch_lang_sheet.py`, `fetch_drive_audios.py`, `run_unity_check.py`, `generate_language.py`: grep for `token.json` and confirm every write or delete is inside the `uses_token_file()` branch only, so credentials from `FTM_GOOGLE_CREDENTIALS` are never persisted (FR-009) and `FTM_HOSTED=1` can never reach the desktop flow (FR-011). Fix anything found.
- [X] T023 [US3] Edit `language_automation/app.py`: confirm `run_ai_check()` builds its env **without** `FTM_GOOGLE_CREDENTIALS` (contracts/pipeline-credentials.md "Not passed"); confirm `st.session_state.google_signin["info"]` is never copied into `result`, `history`, the log or any download (only `result["account"]`, the email, is stored); make sure nothing in `show_run()`/`render_summary()` prints `info`.
- [ ] T024 [US3] Manual check: quickstart V6 (abandoned sign-in → cancelled after 3 min), V7 (generator tab closed → lock released), V8 (link copied to another browser → rejected), V9 (callback URL reloaded → "already been used or has expired"), V10 (two browsers, A then B → B must sign in and B's log names B), V11 (reload → sign in again), V12 (`client_secret_web.json` renamed away → setup error, Generate disabled). Record results in `specs/005-web-google-signin/quickstart.md`.

**Checkpoint**: All three P1 stories work independently. No `token.json` appears in `language_automation/` after web runs.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation that the constitution requires, cleanup, and the full real-language verification.

- [X] T025 [P] Update `CLAUDE.md`: rewrite the "Google sign-in" subsection (web flow on Generate, new tab, `client_secret_web.json`, `FTM_OAUTH_CLIENT_FILE`, `FTM_PUBLIC_URL`, `FTM_HOSTED`, `FTM_GOOGLE_CREDENTIALS`, admission rule, CLI unchanged with `token.json`); update "Web UI (app.py)" bullets "On Generate"/"On failure" for the sign-in button and callback tab; add `google_auth.py` and `web_signin.py` to the module list; add spec `005-web-google-signin` to the spec list; keep the "Secrets" section accurate (`client_secret*.json` is ignored).
- [X] T026 [P] Update `README.md` Setup: add a step "Get the Web application OAuth client JSON from the Curious Learning Google Cloud admin and save it as `language_automation/client_secret_web.json` (needed for the web page; the command line still uses `credentials.json`)". Mention that sign-in opens in a new tab and that only `@curiouslearning.org` accounts are accepted.
- [X] T027 [P] Add a short status note at the top of `specs/002-google-domain-login/spec.md` and `specs/004-generator-page-flow/spec.md`: "2026-10-09: the browser sign-in is now the per-session web flow of spec 005; the `token.json` flow remains for the command line only."
- [X] T028 Cleanup in `language_automation/`: remove unused imports left by T004–T006 (`InstalledAppFlow`, `Credentials` where no longer referenced); run `python -m pyflakes` is not available, so use `python -W error -c "import app"`-style import checks from inside `language_automation/` for `google_auth`, `web_signin`, `fetch_lang_sheet`, `fetch_drive_audios`, `run_unity_check`, `generate_language` to catch NameErrors at import time.
- [ ] T029 Full manual verification (constitution, Development Workflow): quickstart V13 — generate `Hausa` through the web page as a Curious Learning account with the AI language check switched on; compare the Audio check summary and missing-audio list with `python generate_language.py Hausa` from the command line (FR-013, FR-014); run `FTM_HOSTED=1 python generate_language.py Hausa` and confirm it exits 1 before Step 0 with "no Google sign-in was provided for this run". Record all three results in `specs/005-web-google-signin/quickstart.md`.
- [X] T030 Final secret sweep before committing: `git status --porcelain --ignored` must show `language_automation/client_secret_web.json`, `credentials.json`, `token.json` and `.env` as ignored (`!!`), and `git diff --cached` must contain no `client_secret`, `refresh_token` or `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` values (constitution V).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 and T002 have no dependencies and run in parallel. T001's outcome decides T013's cookie script and T021.
- **Foundational (Phase 2)**: T003 first; then T004, T005, T006 in parallel; T007 after T004 and T005; T008 → T009 → T010 in order (same file). **Blocks every user story.**
- **User Story 1 (Phase 3)**: after Phase 2. T011 and T012 can be done in parallel only by different people, because both edit `app.py`; in a single session do T011 → T012 → T013 → T014 → T015 → T016.
- **User Story 2 (Phase 4)**: after US1's T013 (it extends the sign-in stage). T017 → T018 → T019.
- **User Story 3 (Phase 5)**: after Phase 2 for T020/T022; after T013 for T021/T023. T024 after all of them.
- **Polish (Phase 6)**: T025, T026, T027 in parallel at any time after Phase 2; T028 after Phase 5; T029 after T028; T030 last.

### User Story Dependencies

- **US1 (P1)**: depends only on Phase 2. Delivers the working sign-in and run.
- **US2 (P1)**: builds on US1's sign-in stage in `app.py` (T013). Admission itself is already enforced in Phase 2 (T010) and by the pipeline's re-check (T007); US2 adds the refusal presentation and retry.
- **US3 (P1)**: hardening of Phase 2 and US1 code; independently testable with two browsers once US1 works.

### Parallel Opportunities

- Phase 1: T001 ∥ T002.
- Phase 2: T004 ∥ T005 ∥ T006 (three different scripts) after T003.
- Phase 6: T025 ∥ T026 ∥ T027 (three different docs).
- `app.py` tasks (T011–T015, T017, T018, T021, T023) edit one file and should be sequential in a single session.

---

## Parallel Example: Foundational

```text
# After T003 (google_auth.py) exists, launch together:
Task: "Switch fetch_lang_sheet.get_services() to google_auth.load_credentials()"   (T004)
Task: "Switch fetch_drive_audios.get_drive_service() to google_auth"               (T005)
Task: "Switch run_unity_check.get_sheets_service() to google_auth"                 (T006)

# Independently, in the other new file:
Task: "web_signin.py config → pending store → callback"                            (T008 → T009 → T010)
```

## Parallel Example: Polish

```text
Task: "Update CLAUDE.md sign-in and Web UI sections"          (T025)
Task: "Update README.md setup for client_secret_web.json"     (T026)
Task: "Add status notes to specs 002 and 004"                 (T027)
```

---

## Implementation Strategy

### MVP First (User Story 1, then immediately User Story 2)

1. Phase 1: T001 decides the cookie guard; T002 gets the client file.
2. Phase 2: loader + web module. Checkpoint: CLI unchanged.
3. Phase 3: US1. Checkpoint: V1, V2 pass.
4. Phase 4: US2. **Don't share the page with the team before this**: it is what shows the refusal to non-Curious Learning accounts.
5. Phase 5: US3 hardening. Phase 6: docs and the real-language run.

### Incremental Delivery

- After Phase 4 the page is usable locally by the content team with the intended access control.
- Phase 5 closes the replay/other-browser/other-session gaps and must be done before any hosting work starts (the separate hosting feature depends on `FTM_HOSTED` and `FTM_GOOGLE_CREDENTIALS` behaving as contracted).

---

## Notes

- Keep the log contract: `🔐 Authenticating with Google...`, `✅ Authenticated as <email>`, and the four audio prefixes are unchanged (constitution IV).
- Never print tokens, `client_secret` or `credentials_info` anywhere: the run log is downloadable.
- No new pip dependency may be added (research R9). If an import is missing, the design is wrong, not the pin list.
- Commit after each phase; attribution per the session's rule.
