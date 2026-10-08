# Implementation Plan: Google Sign-In Restricted to Curious Learning Accounts

**Branch**: `002-google-domain-login` (spec folder only) | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-google-domain-login/spec.md`

**Planning direction (user)**: "Keep the existing Streamlit app. Host it at a shared URL for the
content team. Each user signs in with Google, and the run uses that user's own Drive access.
Reject any account outside curiouslearning.org. No new dependencies unless they're justified."

## Summary

Put a Google sign-in gate in front of the existing Streamlit generator and host it on one small
Linux VM behind HTTPS.

- **Sign-in**: Streamlit's built-in login (`st.login`), configured to request Drive and Sheets
  permissions and to expose the user's access token.
- **Admission**: allowed only when Google's `hd` claim is `curiouslearning.org` and the email is
  verified.
- **Login on Generate**: the user types a language and presses Generate. If they're not signed
  in, the language is saved and they go straight to Google's login page, with no steps shown.
  After login, "Authenticating…" checks the domain, then checks the user's token with Google
  (audience, email, Drive scope, time left). Only on success do Steps 1–7 appear, for the saved
  language.
- **Never blocked**: closing the tab or abandoning a login cancels the run and frees the
  generator. This part is already fixed and verified in the current app.
- **Drive access**: the run subprocess gets the user's token through `FTM_GOOGLE_ACCESS_TOKEN`.
  A new `google_auth.py` builds credentials from it. Command-line runs keep using `token.json`.
- **Linux hosting** requires consistent lowercase language paths and a zip download of the
  package, so the team can get the output.
- **Hardening**: three fixes from the security review: clean Drive file names, validate language
  names, and add a timeout and `https`-only rule to the sheet URL fetch.

See [research.md](research.md) for the decisions and the four admin dependencies (D1–D4).

## Technical Context

**Language/Version**: Python 3.11+ on the server (3.13 locally today)

**Primary Dependencies**: `streamlit` (installed 1.64.0, uses `st.login`, `st.user`,
`expose_tokens`), `google-api-python-client`, `google-auth`, `google-auth-oauthlib` (command line
only), `requests`, plus **one new dependency, `Authlib`**, which `st.login` requires (R1). System
packages: `ffmpeg`, plus Caddy on the server.

**Storage**: Files only.
- `lang/<lang.lower()>/` holds the packages, on the VM's persistent disk.
- `logs/access.jsonl` is append-only.
- Login state is in Streamlit's signed cookie.
- There is no database.

**Testing**: No automated test suite exists (constitution, development workflow). Validation is
the manual scenarios V1–V13 in [quickstart.md](quickstart.md).

**Target Platform**: Ubuntu LTS VM on Google Compute Engine (`e2-small`), reached at
`https://<host>`, where the host name is chosen by Curious Learning IT. Windows stays supported for
local and command-line use.

**Project Type**: Internal web application (Streamlit) that wraps a command-line pipeline

**Performance Goals**:
- A run must fit inside the remaining lifetime of the user's Google token. The token check
  requires at least `MIN_TOKEN_SECONDS` left (default 1800), tuned in V13.
- Sign-in through to a started run takes under 1 minute (SC-003).

**Constraints**:
- No Drive, disk or subprocess action before "Authenticating…" ends in OK (FR-004).
- Tokens are never logged or stored on the server's disk.
- One run at a time (existing lock).
- The pipeline's log-line prefixes must not change (constitution IV).

**Scale/Scope**: about 5–20 content team users, occasional runs, one at a time. Two modules are
new (`google_auth.py`, `lang_paths.py`), five existing modules change, and deployment files are
added.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design (below).*

| Principle | Assessment | Status |
|---|---|---|
| **I. Verify before you touch disk** | The order is: Authenticating (domain + token) → Drive pre-check → wipe. A token about to expire is caught *before* the wipe (R4). Language-name validation happens before any lookup. | ✅ Pass. This feature strengthens it. |
| **II. Exact matching for language identity** | Lookup logic is unchanged. The folder name becomes lowercase, but matching against Drive still uses the name as typed, ignoring case. | ✅ Pass |
| **III. The game JSON is the source of truth for audio** | Unchanged | ✅ Pass |
| **IV. Stable log contract** | No pipeline prefix changes. New pipeline lines only use the existing `❌` style. `👤 Started by:` is added by the app to its own copy of the log. | ✅ Pass |
| **V. No secrets in the repo** | The OAuth client secret and cookie secret go in `.streamlit/secrets.toml`, which is gitignored. In web mode, tokens are passed only to the child process through its environment and never written to disk. `token.json` is not used in web mode. | ✅ Pass |
| Constraint: dependencies justified in plan | Authlib. See Complexity Tracking. | ✅ Justified |
| Constraint: consistent path casing for new code | Fixed for all code by `lang_paths()`. Required for Linux. | ✅ Pass. This feature resolves a known violation. |
| Constraint: Drive IDs as named constants | Unchanged. The new code adds no Drive IDs. | ✅ Pass |
| Workflow: manual verification task, CLAUDE.md updated | Quickstart V1–V13 become tasks, and updating CLAUDE.md is a task. | ✅ Pass |

**Gate result: PASS.** One justified dependency.

**Post-design re-check (after data-model and contracts)**: still PASS.
- The contracts keep every Drive, disk and subprocess action behind Stage B = OK.
- `access.jsonl` excludes tokens.
- The `.streamlit/config.toml` binding to `127.0.0.1` means only Caddy (HTTPS) can reach the app.
  This also fixes security finding #2.
- No new violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-google-domain-login/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R9 decisions, admin dependencies D1–D4
├── data-model.md
├── quickstart.md        # V1–V13 validation, deploy outline
├── contracts/
│   ├── auth-states.md   # what the user sees, exact messages
│   └── pipeline-auth.md # env-var contract, secrets.toml layout
├── checklists/requirements.md
└── tasks.md             # created by /speckit-tasks
```

### Source Code (repository root)

```text
requirements.txt                    # NEW: pinned deps incl. Authlib (also addresses review #7)
.gitignore                          # + language_automation/.streamlit/secrets.toml, logs/
language_automation/
├── app.py                          # CHANGED: auth stages A/B, sign-in/out, gate history,
│                                   #   pass token via env, 👤 line, zip download, access log
├── auth_gate.py                    # NEW: is_allowed(user), check_token(token) → AuthCheck,
│                                   #   messages, access-log writer (keeps app.py readable)
├── google_auth.py                  # NEW: single credentials builder (web token | token.json)
├── lang_paths.py                   # NEW: validate_language_name(), lang_dir(), json_path(), audios_dir()
├── generate_language.py            # CHANGED: validate name first; use lang_paths
├── fetch_lang_sheet.py             # CHANGED: get_services → google_auth; use lang_paths
├── fetch_drive_audios.py           # CHANGED: get_drive_service → google_auth; sanitize Drive names (#1)
├── fetch_unity_json.py             # CHANGED: timeout + https-only (#5)
├── check_unused_audio.py           # CHANGED: use lang_paths
├── check_missing_audios.py         # CHANGED: use lang_paths
└── .streamlit/
    ├── config.toml                 # NEW: server.address=127.0.0.1 (Caddy fronts it), headless
    └── secrets.toml.example        # NEW: template, no real values
deploy/
├── README.md                       # NEW: VM setup steps D1–D4, update procedure
├── ftm-generator.service           # NEW: systemd unit (runs streamlit from language_automation/)
└── Caddyfile                       # NEW: HTTPS reverse proxy with websocket support
```

**Structure Decision**: keep the flat script layout of `language_automation/`. That matches
existing conventions and the constitution's "standalone scripts" rule. The new modules are small
helpers imported by name, just as the existing scripts import each other. Deployment files go in
a separate top-level `deploy/` folder, so the pipeline folder stays runnable on its own.

## Implementation phases (summary for /speckit-tasks)

1. **Foundations**: `requirements.txt`, `.gitignore`, `lang_paths.py` (with casing fix and name
   validation), `google_auth.py`. Rewire the pipeline modules to use them. Verify that the command
   line still works (V9, V10, V11).
2. **US1 + US2, the sign-in gate**: `auth_gate.py`, Stage A and Stage B in `app.py`, token handoff,
   gated history, sign-out. Verify V1–V8.
3. **US3, attribution**: the `👤` log line and `access.jsonl` events.
4. **Hosting**: the zip download, `.streamlit/config.toml`, the `deploy/` files, and security
   fixes #1 and #5. Deploy, then run V12 and V13 and set `MIN_TOKEN_SECONDS`.
5. **Docs**: CLAUDE.md (auth modes, lowercase paths, hosting) and the spec 001 baseline notes.

## Spec amendments made during planning (please confirm)

These were found by reading Streamlit's login code. They are recorded in spec.md → Clarifications
→ *Planning amendments*.

| # | Change | Why |
|---|---|---|
| A1 *(revised by user)* | Type the language, press Generate, and go straight to the Google login page with no steps shown. After login, the run continues with the saved language. Closing or abandoning the login cancels it, and the generator stays free. | The user's requested flow. The language survives the redirect through a pending-request store keyed by the browser's `_streamlit_xsrf` cookie (R5). |
| A1b *(bug, fixed now)* | Closing the tab, or abandoning a sign-in, cancels the run and frees the lock. | The user reported that the generator stayed blocked after closing the login tab. Already fixed in `app.py` and verified (R5b). |
| A2 | "Cancelled" and "failed" sign-in share one message. | Streamlit returns both to the start page without saying which happened. A refused domain is still a separate message. |
| A3 | Re-sign-in is needed about every hour before a run, and the 8-hour limit still applies. | Google access tokens last about an hour, and Streamlit keeps no refresh token. Re-sign-in is one click. |
| A4 | New: after a run, the user can **download the package as a .zip**. | On a hosted server the team can't see `lang/` otherwise. *Open question: should packages go somewhere else instead, such as Drive or the CDN?* |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New dependency **Authlib** | `st.login` (Streamlit's own login, already installed) needs it to talk to Google. | A hand-written OAuth flow with `google-auth-oauthlib` adds security-sensitive code to maintain, and it can't keep users signed in, because Streamlit can't set cookies (R1). |
| New infrastructure (VM + Caddy) | The spec needs a shared HTTPS address and one long-lived instance, for the run lock and the packages. | Cloud Run (temporary disk, multiple instances, timeouts), a tunnel to a laptop, and Community Cloud were all rejected (R6). |
