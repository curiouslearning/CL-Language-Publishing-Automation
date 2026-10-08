---
description: "Task list for 002 – Google Sign-In Restricted to Curious Learning Accounts"
---

# Tasks: Google Sign-In Restricted to Curious Learning Accounts

> **2026-10-05, design reverted by the user.** The Streamlit login (`st.login`, `auth_gate.py`,
> `google_auth.py`, `secrets.toml`, the access log, the zip download and `deploy/`) was removed.
> The existing `credentials.json` sign-in is used instead (see spec.md → Status).
>
> **Still in place** from the tasks below:
> - T005: cancel on tab close or sign-in timeout;
> - T006, T009–T012: `lang_paths` and name validation;
> - T033: safe Drive file names;
> - T034: `https`-only content URL;
> - T045: the progress counter.
>
> **New**: `generate_language.authenticate()` prints `🔐 Authenticating with Google...` and
> `✅ Authenticated as <email>`, and refuses non-curiouslearning.org accounts. `app.py` shows
> "Authentication in progress" until that line, then the steps. All other tasks are obsolete.

**Input**: Design documents from `specs/002-google-domain-login/`. These are plan.md, spec.md,
research.md, data-model.md, contracts/auth-states.md, contracts/pipeline-auth.md and
quickstart.md.

**Tests**: The spec doesn't ask for automated tests, and the repo has no test suite. Per the
constitution's development workflow, every story ends with a **manual verification** task that
uses the scenarios in [quickstart.md](quickstart.md).

**Paths**: Flat scripts in `language_automation/`, as described in plan.md → Project Structure.
Every pipeline script runs from inside `language_automation/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1, US2 or US3 from spec.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependency manifest, secrets layout, and keeping secrets out of git.

- [X] T001 [P] Create `requirements.txt` at the repo root, pinning today's versions:
  `streamlit==1.64.0`, `requests==2.32.5`, `google-api-python-client==2.187.0`,
  `google-auth==2.41.1`, `google-auth-oauthlib==1.2.3`, plus `Authlib` at the version
  `pip install Authlib` resolves (must be ≥ 1.3.2). Note `ffmpeg` (system package) in a comment.
  Then run `python -m pip install -r requirements.txt`.
- [X] T002 [P] Add `language_automation/.streamlit/secrets.toml` and `language_automation/logs/`
  to `.gitignore`.
- [X] T003 [P] Create `language_automation/.streamlit/secrets.toml.example`. Copy the TOML in
  [contracts/pipeline-auth.md](contracts/pipeline-auth.md) → "Server secrets", with placeholder
  values only (`<web client id>` etc.) and `redirect_uri = "http://localhost:8501/oauth2callback"`.
- [X] T004 [P] Create `language_automation/.streamlit/config.toml` with `[server]`
  `address = "127.0.0.1"` and `headless = true`. This addresses security finding #2: only
  localhost, or Caddy on the server, can reach the app.
- [x] T005 Cancel a run and release the one-run lock when its browser tab closes, or when a
  Google sign-in waits longer than `SIGNIN_TIMEOUT_SECONDS = 180`, in `language_automation/app.py`.
  *(Done 2026-10-05 and verified: research R5b, spec A1b.)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: consistent paths, name validation, one credentials builder, and the auth checks.
Every story needs these.

**⚠️ CRITICAL**: no user story work can begin until this phase is complete.

- [X] T006 [P] Create `language_automation/lang_paths.py` with:
  - `LANG_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")`
  - `validate_language_name(name)`: strips the name, then raises `ValueError` unless it matches
    `^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$`
  - `lang_dir(lang)` → `LANG_ROOT/<lang.lower()>`
  - `json_path(lang)` → `lang_dir/ftm_<lang.lower()>.json`
  - `audios_dir(lang)` and `images_dir(lang)`

  Spec: data-model.md → Language Paths.
- [X] T007 [P] Create `language_automation/google_auth.py` with `get_credentials(scopes)`, which
  behaves exactly as in the table in [contracts/pipeline-auth.md](contracts/pipeline-auth.md):
  - `FTM_AUTH_MODE=web` with `FTM_GOOGLE_ACCESS_TOKEN` set: return
    `google.oauth2.credentials.Credentials(token=…)`. Never read or write `token.json` or
    `credentials.json`.
  - `web` without a token: print `❌ Not signed in: no Google access token was provided.` and
    `sys.exit(1)`.
  - Mode unset: today's `token.json` / `InstalledAppFlow.run_local_server` logic, moved here from
    `fetch_lang_sheet.get_services`.
- [X] T008 Make `get_services()` in `language_automation/fetch_lang_sheet.py`,
  `get_drive_service()` in `language_automation/fetch_drive_audios.py` and `get_sheets_service()`
  in `language_automation/run_unity_check.py` build their credentials with
  `google_auth.get_credentials(SCOPES)`. Keep each module's `SCOPES` and return values unchanged.
  (Depends on T007.)
- [X] T009 In `language_automation/generate_language.py`:
  - Call `lang_paths.validate_language_name()` on `sys.argv[1]` **before**
    `verify_language_on_drive`. On `ValueError`, print
    `❌ Invalid language name: use letters, digits, spaces, - or _.` and exit 1.
  - Replace every `os.path.join(os.getcwd(), "lang", …)` and `f"ftm_{lang_name}.json"` with
    `lang_paths` calls.
  - Keep every printed log prefix byte-identical (constitution IV).

  (Depends on T006.)
- [X] T010 [P] Use `lang_paths.json_path(language)` for `output_path` in
  `fetch_lang_sheet.fetch_language_sheet`, in `language_automation/fetch_lang_sheet.py`.
  (Depends on T006.)
- [X] T011 [P] In `language_automation/fetch_drive_audios.py`, use `lang_paths.audios_dir(lang)`
  in `main_wrapper` and `lang_paths.json_path(language)` in `download_json_drive_links`.
  (Depends on T006.)
- [X] T012 [P] Use `lang_paths.json_path()` and `lang_paths.audios_dir()` in
  `language_automation/check_unused_audio.py` (`clean_unused_audios`) and
  `language_automation/check_missing_audios.py` (`check_missing_audios`). Keep the function
  signatures, so `generate_language.py` calls still work. (Depends on T006.)
- [X] T013 [P] Create `language_automation/auth_gate.py` with:
  - Constants: `ALLOWED_DOMAIN = "curiouslearning.org"`, `MIN_TOKEN_SECONDS = 1800`,
    `MAX_SIGNIN_AGE_SECONDS = 8 * 3600`, `PENDING_TTL_SECONDS = 600`.
  - `MESSAGES`: the five message texts copied verbatim from
    [contracts/auth-states.md](contracts/auth-states.md) → Messages.
  - `is_allowed(user) -> (bool, reason)`. Require `user.get("hd") == "curiouslearning.org"`,
    `user.get("email_verified") is True`, and an email ending `@curiouslearning.org`. If `iat` is
    older than `MAX_SIGNIN_AGE_SECONDS`, return reason `expired`.
  - `check_token(access_token, expected_email, client_id) -> AuthCheck`. A dataclass whose
    `state` is one of `ok | expired | unreachable | refused`. Call
    `requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": …}, timeout=10)`
    and require: `aud == client_id`, `email == expected_email`, `"https://www.googleapis.com/auth/drive"`
    among the scopes, and `int(expires_in) >= MIN_TOKEN_SECONDS`.

  Never print or log the token.
- [ ] T014 Manual check, foundation:
  - Run quickstart **V9** (command line unchanged; `lang/hausa/ftm_hausa.json` is created).
  - Run **V10** (`FTM_AUTH_MODE=web` without a token: exits 1, folders untouched).
  - Run **V11** (`python generate_language.py "..\.."` is rejected before any Drive call).
  *(Partial, 2026-10-05: V10 and V11 passed, and `lang/` was byte-for-byte unchanged. **V9 (a full real Hausa run) is still to be done by the user**, because it rewrites local data and may create a Drive copy.)*

**Checkpoint**: the command line works with lowercase paths. Web-mode credentials and the auth
checks are ready.

---

## Phase 3: User Story 1 – Sign in with a Curious Learning account to generate a language (P1) 🎯 MVP

**Goal**: type a language, press Generate, and go straight to Google login. After sign-in,
"Authenticating…" → ✅ → Steps 1–7 run for the saved language, using the user's own Drive access.

**Independent Test**: quickstart V1, V2, V2b, V2c, V7 and V8 as account **A**.

- [X] T015 [US1] Add a pending-request store to `language_automation/app.py`:
  - a `@st.cache_resource` dict;
  - `save_pending(languages)` and `take_pending()`, keyed by
    `st.context.cookies.get("_streamlit_xsrf")`, each holding `{"languages": [...], "created": time.time()}`;
  - discard entries older than `auth_gate.PENDING_TTL_SECONDS` (600 s) on every access.

  If the cookie is missing, store nothing and fall back to the user retyping after sign-in
  (research R5). (Data model: Pending Request.)
- [X] T016 [US1] In the Generate handler in `language_automation/app.py`:
  - Validate each comma-separated name with `lang_paths.validate_language_name`. Show
    `st.error` for invalid names, and nothing else happens.
  - If `not st.user.is_logged_in`, call `save_pending(langs)` and then `st.login("google")`.
  - No `st.status`, steps or subprocess may be created on this path (FR-004, FR-005a).
- [X] T017 [US1] Add `authenticate()` to `language_automation/app.py`. It shows
  `st.status("Authenticating…")`, then:
  - runs `auth_gate.is_allowed(st.user)`;
  - then runs `auth_gate.check_token(st.user.tokens["access"], st.user.email, st.secrets["auth"]["google"]["client_id"])`;
  - on `ok`, updates the status to ✅ `MESSAGES["ok"]` and returns the token;
  - on anything else, returns `None` and leaves the status showing the error (US2 tasks fill in
    those messages).
- [X] T018 [US1] Wire the flow in `language_automation/app.py`:
  - When the user is signed in and either presses Generate or `take_pending()` returns a request,
    call `authenticate()` first.
  - Only if it returns a token, acquire the existing `pipeline_lock()` and call `run_pipeline()`
    for each language. That is the only place the step list is drawn.
- [X] T019 [US1] Change `run_pipeline(lang)` to `run_pipeline(lang, access_token, email)` in
  `language_automation/app.py`. Add `FTM_AUTH_MODE="web"` and `FTM_GOOGLE_ACCESS_TOKEN=access_token`
  to the subprocess `env` dict only. The token must never be added to `result["log"]`, messages or
  `st.session_state` (FR-009, contract guarantees).
- [X] T020 [US1] At the top of `language_automation/app.py` for signed-in, allowed users, show
  `✅ Signed in as <email>` with a **Sign out** button that calls `st.logout()` (FR-007).
- [X] T021 [US1] In `render_summary`, in `language_automation/app.py`, replace
  `os.path.join(APP_DIR, "lang", result["lang"], "audios")` with
  `lang_paths.audios_dir(result["lang"])`, so the count works with lowercase paths.
- [ ] T022 [US1] Manual check: create a local `secrets.toml` from T003 using a real Web OAuth
  client (admin dependency D1). Then run quickstart **V1, V2, V2b, V2c, V7 and V8** as account
  **A**. Confirm the `_streamlit_xsrf` cookie survives the Google redirect, so the language
  continues without retyping. If it doesn't, apply the research R5 fallback and note it in
  research.md.
  *(Pending admin dependency D1. Simulated with fake Google users in the Streamlit test harness: V1, V2, the token kept out of logs and page, and V11 all passed. In headless Edge, closing the tab during a run cancels it and frees the lock.)*

**Checkpoint**: an allowed user can go from typing a language to a finished run, with sign-in in
between and their own Drive access.

---

## Phase 4: User Story 2 – Refuse everyone else, with nothing created (P1)

**Goal**: other domains, cancelled or expired sign-ins and Google errors all end in a clear
error. No steps appear, nothing is created, and the generator stays free.

**Independent Test**: quickstart V3, V4, V5 and V6, with the `lang/` hash snapshot unchanged and
no `_converted` copy on Drive.

- [X] T023 [US2] Add the refused path to `language_automation/app.py`. When `is_allowed` fails
  with a domain reason:
  - show `st.error(MESSAGES["refused"].format(email=…))` and a **Use a different account** button
    that calls `st.logout()`;
  - hide the language form and history;
  - discard any pending request.
- [X] T024 [US2] Add the `expired` and `unreachable` outcomes of `authenticate()` to
  `language_automation/app.py`. Show the matching `MESSAGES` text. For `expired`, also show a
  **Sign in again** button that calls `save_pending(langs)` and then `st.login("google")`. No run
  starts.
- [X] T025 [US2] Add the cancelled path to `language_automation/app.py`. On page load, if
  `not st.user.is_logged_in` and `take_pending()` returns a request (they came back without
  completing login), discard it and show `st.warning(MESSAGES["cancelled"])` above an empty form
  (FR-005, A2).
- [X] T026 [US2] Gate the history in `language_automation/app.py`: draw "Previous runs" only after
  `is_allowed` succeeds (FR-008). Anyone not signed in sees only the form. Refused users see only
  the refusal.
- [ ] T027 [US2] Manual check: run quickstart **V3** (account **B**, including clicking through
  Google's "unverified app" warning), **V4, V5** (temporarily set `MIN_TOKEN_SECONDS = 3599`) and
  **V6**. Take the `lang/` hash snapshot before and after each, and expect no difference. Check
  the Drive sheets folder for new `_converted` files, and expect none.
  *(Pending D1. Simulated: V3 sutara.org refused with no form, V4 cancelled, V5 expired token, and Drive scope not granted all passed. Domain and token checks passed 15/15 unit cases, covering look-alike domains, Gmail, unverified email, 8 h age, another app's token, another user's token, a short-lived token, and Google down.)*

**Checkpoint**: US1 and US2 together satisfy the user's core request.

---

## Phase 5: User Story 3 – Know who ran what (P2)

**Goal**: every run, and every refused attempt, is attributed to an account.

**Independent Test**: run as two allowed accounts and attempt once as **B**. Check the first log
lines and `logs/access.jsonl`.

- [X] T028 [P] [US3] Add `log_event(event, **fields)` to `language_automation/auth_gate.py`. It
  appends one JSON object per line to `language_automation/logs/access.jsonl`, creating the
  folder, under a `threading.Lock`. Fields:
  - `ts`: ISO-8601 UTC;
  - `event`: one of `signin_ok | signin_refused | token_expired | run_started | run_finished`;
  - `email`: string or null;
  - `hd`: only on `signin_refused`;
  - `lang`: only on run events;
  - `outcome`: `complete | warning | error`, only on `run_finished`.

  Raise an error if a field named `token` or `access_token` is ever passed. (Data model: Access
  Log Entry.)
- [X] T029 [US3] Call `log_event` from `language_automation/app.py`:
  - `signin_ok` once per session;
  - `signin_refused` once per session, using the `refusal_logged` session flag;
  - `token_expired`;
  - `run_started` and `run_finished` around each `run_pipeline`. A `cancelled` outcome is logged
    as `error` with `"cancelled": true`.
- [X] T030 [US3] In `run_pipeline` in `language_automation/app.py`, set
  `result["user_email"] = email` and insert `👤 Started by: <email>` as the first line of
  `result["log"]`. Show it as a caption in `render_summary` (FR-010).
- [ ] T031 [US3] Manual check: run the Independent Test above. Confirm every run's downloaded log
  starts with `👤 Started by:` and that `access.jsonl` contains no token values.
  *(Pending D1 for real accounts. Simulated: the 👤 first line and signin_ok, signin_refused, token_expired, run_started and run_finished events are written, and no token is in access.jsonl.)*

---

## Phase 6: Hosting & package delivery (FR-013, research R6–R7)

**Goal**: the generator is at the shared HTTPS URL, and users can download what it produced.

- [X] T032 Add a **Download language package (.zip)** button to `render_summary` in
  `language_automation/app.py`. Show it only when `result["state"]` is `complete` or `warning`.
  Build the zip in memory with `zipfile` and `io.BytesIO` from `lang_paths.lang_dir(result["lang"])`,
  named `<lang>_<started>.zip` (FR-013).
- [X] T033 [P] Harden `download_convert_to_mp3` in `language_automation/fetch_drive_audios.py`
  against crafted Drive file names (security finding #1):
  1. Compute `name = os.path.basename(name.replace("\\", "/"))`.
  2. Then `base = INVALID_NAME_CHARS.sub("_", base).strip()`.
  3. Skip a file whose base is empty, `.` or `..`, printing `❌ Skipped unsafe file name: <original>`.
  4. Assert that the final `output_mp3` and `temp_input` resolve inside `output_dir`.
- [X] T034 [P] In `language_automation/fetch_unity_json.py`, reject URLs that don't start with
  `https://` (`❌ Refusing non-https content URL`). Use `requests.get(url, timeout=(10, 300))`
  (security finding #5).
- [X] T035 [P] Create `deploy/ftm-generator.service`, a systemd unit:
  - `WorkingDirectory=/opt/ftm/language_automation`
  - `ExecStart=/opt/ftm/.venv/bin/python -m streamlit run app.py`
  - `Restart=on-failure`
  - a dedicated `ftm` user
- [X] T036 [P] Create `deploy/Caddyfile`: `<host> { reverse_proxy 127.0.0.1:8501 }`. Caddy handles
  HTTPS and WebSocket upgrades automatically.
- [X] T037 [P] Create `deploy/README.md` covering:
  - admin dependencies D1–D4 from research.md (no personal names);
  - VM setup (Ubuntu, `apt install python3-venv ffmpeg caddy`);
  - cloning to `/opt/ftm` and `pip install -r requirements.txt`;
  - creating `secrets.toml` with `redirect_uri = "https://<host>/oauth2callback"`;
  - enabling the service and Caddy;
  - updating (`git pull` + restart).
- [ ] T038 Manual check: deploy to the VM. Run quickstart **V12** (Linux casing) and **V13**
  (time the largest language), then set `MIN_TOKEN_SECONDS` in
  `language_automation/auth_gate.py` to the measured run time plus a 10-minute margin.
  *(Pending D2 and D3, the VM and DNS.)*

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T039 [P] Update `CLAUDE.md`:
  - web mode versus command-line auth (`FTM_AUTH_MODE`, `FTM_GOOGLE_ACCESS_TOKEN`, `google_auth.py`);
  - lowercase `lang/<lang>/` paths through `lang_paths.py`, with the casing gotcha marked resolved;
  - `auth_gate.py`, the cancel-on-tab-close behavior, `logs/access.jsonl`, and the `deploy/`
    folder;
  - running with `.streamlit/secrets.toml`.
- [X] T040 [P] Update the Known Limitations in `specs/001-baseline-language-pipeline/spec.md`.
  Mark as resolved by 002: path casing, network exposure (#2), crafted file names (#1), and the
  URL fetch (#5).
- [ ] T041 Run the full quickstart (V1–V13) against the shared URL, and check spec SC-001 to
  SC-006. Record the results in `specs/002-google-domain-login/checklists/requirements.md` →
  Notes.
  *(Pending deployment.)*

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none. T005 is already done.
- **Foundational (Phase 2)**: T006 and T007 first. T008 depends on T007. T009–T012 depend on T006.
  T013 is independent. T014 comes last. **This phase blocks every story.**
- **US1 (Phase 3)**: needs Phase 2 and admin dependency **D1**, a Web OAuth client, for T022.
- **US2 (Phase 4)**: needs T017 (`authenticate()`) from US1, because it fills in that function's
  failure branches. It can be built right after T017, in parallel with T018–T021.
- **US3 (Phase 5)**: T028 can start any time after Phase 2. T029 and T030 need T018 and T019.
- **Hosting (Phase 6)**: T033, T034 and T035–T037 can start after Phase 2. T032 needs T021.
  T038 needs D2, D3 and every earlier phase.
- **Polish (Phase 7)**: after Phase 6.

### Within `app.py`

T015 → T016 → T017 → T018 → T019 → T020 → T021 → T023–T026 → T029–T030 → T032. They are
sequential because they all edit the same file.

### Parallel opportunities

```text
Phase 1:  T001, T002, T003, T004              (different files)
Phase 2:  T006 ‖ T007 ‖ T013, then T009 ‖ T010 ‖ T011 ‖ T012 (after T006) and T008 (after T007)
Phase 5+: T028 (auth_gate.py) ‖ T033 (fetch_drive_audios.py) ‖ T034 (fetch_unity_json.py)
          ‖ T035 ‖ T036 ‖ T037 (deploy/)
Phase 7:  T039 ‖ T040
```

---

## Implementation Strategy

### MVP (US1 + US2: the user's core request)

1. Phase 1 → Phase 2, then the **T014 check** (the command line still works).
2. Phase 3 (US1) → **T022 check** locally with a localhost redirect.
3. Phase 4 (US2) → **T027 check**. Refusals leave nothing behind.
4. **Stop and demo locally.** At this point only Curious Learning accounts can generate, using
   their own Drive access, and abandoned logins never block the generator.

### Incremental delivery

5. Phase 5 (US3): attribution.
6. Phase 6: zip download, hardening, deploy to the shared URL.
7. Phase 7: docs and the full validation.

Commit after each phase checkpoint.

## Notes

- Keep pipeline log prefixes byte-identical (constitution IV). `app.py` parses them.
- Nothing may touch Drive, disk or a subprocess before `authenticate()` returns a token (FR-004).
- Never print, log, display or store access tokens.

## Phase 8: Convergence

- [ ] T042 End a signed-in session after 8 hours of **inactivity**, not only 8 hours after
  sign-in. Keep a server-side last-activity time per user email in `language_automation/app.py`
  (an `st.cache_resource` dict). Refresh it on every page interaction. Treat a gap greater than
  `auth_gate.MAX_SIGNIN_AGE_SECONDS` as `expired`. per FR-006 (partial)
- [ ] T043 Make **Use a different account** in `language_automation/app.py` (both the page-level
  refusal and the refusal inside `authenticate()`) go straight to Google's account chooser by
  calling `sign_in(pending languages)`, i.e. `st.login`, instead of `st.logout`, so the user can
  retry with another account in one step. per US2/AC4 (partial)
- [ ] T044 In web mode (`FTM_AUTH_MODE=web`), make `verify_language_on_drive`'s not-found
  message in `language_automation/generate_language.py` also say
  `If the spelling is right, ask for access to this language's sheet and audio folder on Drive.`
  Keep the existing `❌` lines unchanged. per spec Edge Cases: Curious Learning account without
  Drive access (partial)
- [ ] T045 Add `❌ Skipped unsafe file name: ` to the `AUDIO_FILE_DONE` pattern in
  `language_automation/app.py`, so a skipped file still counts toward the "N/M files" progress.
  per Constitution IV / T033 (partial)
