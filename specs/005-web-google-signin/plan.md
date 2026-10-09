# Implementation Plan: Per-Person Web Google Sign-In for the Generator

**Branch**: `005-web-google-signin` (spec folder only) | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-web-google-signin/spec.md`

**Scope**: sign-in only. Hosting (container, Cloud Run, deploy instructions, zip download) is out of scope; the user is handling it separately (spec, Out of Scope).

## Summary

The Streamlit generator gets a **web Google sign-in** in place of the desktop `run_local_server` flow.

**Sign-in on Generate (unchanged UI):**
- **Before sign-in:** in a page session that isn't signed in, the run's box shows "Authentication in progress" with a **Sign in with Google** button that opens Google in a new tab.
- **Callback:** Google returns to the app. The new tab exchanges the code (PKCE). It verifies Google's ID token: signature, audience, `email_verified`, `hd == curiouslearning.org`, and the email domain. It hands the result to the waiting session through a single-use, 3-minute, browser-bound pending store.
- **On success:** the waiting session shows "Authenticated as <email>" and starts the pipeline.
- **On refusal or failure:** "Authentication failed" with the reason, and the pipeline never starts.

**Per-person access:**
- **Held in memory:** the person's credentials live only in that page's `st.session_state`.
- **Passed to each run:** each pipeline subprocess receives them through the `FTM_GOOGLE_CREDENTIALS` environment variable.
- **Shared loader:** a new `google_auth.py` builds every Google client from that variable. The command line keeps `token.json` with the desktop flow.
- **Server switch:** `FTM_HOSTED=1` stops the scripts from ever falling back to `token.json`. It's for the separate hosting work to set.

**No new Python dependencies.** It works anywhere the generator's web address is registered with the OAuth client: `http://localhost:8501/` now, the hosted address later.

## Technical Context

**Language/Version**: Python 3.13 (current local), 3.11+ supported. Windows stays supported.

**Primary Dependencies**:
- Already pinned: `streamlit` 1.64.0, `google-auth` (`id_token.verify_oauth2_token`), `google-auth-oauthlib` (`Flow` for the web flow, `InstalledAppFlow` for the CLI), `google-api-python-client`, `requests`.
- No additions (R9).

**Storage**: none persistent.
- Sign-ins are held in process memory: `st.session_state`, plus a `st.cache_resource` pending store.
- `lang/` is unchanged.

**Testing**: no automated suite (constitution). Manual scenarios V1–V13 in [quickstart.md](quickstart.md), including a real-language run.

**Target Platform**: wherever `app.py` runs. Validated locally at `http://localhost:8501/`. The hosted environment is out of scope.

**Project Type**: internal web app (Streamlit) wrapping a command-line pipeline.

**Performance Goals**: pressing Generate to a started run in under 1 minute, including sign-in (SC-001).

**Constraints**:
- **Domain check:** curiouslearning.org only, decided by verified ID-token claims.
- **No sign-in on disk:** no sign-in is written to disk by the app.
- **Fails closed:** without the sign-in configuration, nothing runs.
- **One process:** the one-run lock and the pending store are in-process. That holds as long as the generator runs as one process; noted for the hosting work.

**Scale/Scope**: a handful of content-team users, one run at a time.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | How |
|---|---|---|
| I. Verify before you touch disk | ✅ | Sign-in and the domain check happen in the app **before** the subprocess starts. The pipeline keeps `authenticate()` (it prints `✅ Authenticated as` and re-checks the Drive email) and `verify_language_on_drive` before any wipe. |
| II. Exact matching | ✅ | Untouched. |
| III. Game JSON is the audio source of truth | ✅ | Untouched. |
| IV. Stable log contract | ✅ | `🔐 Authenticating with Google...` and `✅ Authenticated as <email>` stay. No prefix changes. |
| V. No secrets in the repository | ✅ | The web client JSON is the gitignored `client_secret_web.json` (matched by `client_secret*.json`), or the path in `FTM_OAUTH_CLIENT_FILE`. Sign-ins stay in memory or the child's env, never on disk. |
| Tech: no new deps without justification | ✅ | None added. |
| Tech: CWD convention / path casing | ✅ | Unchanged. |
| Tech: Drive IDs as constants | ✅ | Unchanged. |
| Workflow: manual verification on a real language, CLAUDE.md updated | ✅ | V12 (Hausa). CLAUDE.md is a tasks item. |

**Post-design re-check (after Phase 1)**: still passing. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/005-web-google-signin/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0: decisions R1–R12 (R8, R10 deferred to the hosting work)
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1: validation scenarios V1–V13
├── contracts/
│   ├── web-signin.md            # callback URL, state lifecycle, admission rule, UI messages
│   └── pipeline-credentials.md  # FTM_GOOGLE_CREDENTIALS / FTM_HOSTED contract for the scripts
├── checklists/
│   ├── requirements.md
│   └── auth.md                  # sign-in requirements-quality review (/speckit-checklist)
└── tasks.md             # /speckit-tasks (not created here)
```

### Source Code (repository root)

```text
README.md                       # EDIT setup: web OAuth client file (client_secret_web.json) for the web page
CLAUDE.md                       # EDIT Google sign-in + Web UI sections
language_automation/
├── google_auth.py              # NEW  load_credentials(scopes): FTM_GOOGLE_CREDENTIALS → else (not hosted) token.json/desktop flow
├── web_signin.py               # NEW  web OAuth: client config, auth URL (PKCE, state, select_account),
│                               #      pending store, callback handling, ID-token admission check
├── app.py                      # EDIT callback page; sign-in stage in run_pipeline; session creds; env to subprocess;
│                               #      setup error when not configured
├── generate_language.py        # EDIT authenticate(): uses google_auth; keeps domain re-check + log lines
├── fetch_lang_sheet.py         # EDIT get_services() → google_auth
├── fetch_drive_audios.py       # EDIT get_drive_service() → google_auth
└── run_unity_check.py          # EDIT drop its own InstalledAppFlow (unused helper) → google_auth
```

**Structure Decision**: keep the single `language_automation/` package (constitution). Sign-in logic goes into two small modules:
- **`google_auth.py`**: loads credentials for the scripts.
- **`web_signin.py`**: the web flow, used only by `app.py`.

No hosting files.

## Complexity Tracking

No constitution violations to justify.
