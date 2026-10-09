# Data Model: Per-Person Web Google Sign-In for the Generator

Nothing is persisted. Every entity lives in the Streamlit server process and disappears on restart.

## PendingSignIn

Process-wide store: `st.cache_resource` dict keyed by `state`, guarded by a `threading.Lock`.

| Field | Type | Notes |
|---|---|---|
| `state` | str (key) | 32 random bytes, URL-safe. Sent to Google and returned on the callback. |
| `session_id` | str | Streamlit session that pressed Generate. Only this session may consume the entry. |
| `browser_nonce` | str | Random. Also set as the `ftm_signin` cookie in that browser (research R4). |
| `code_verifier` | str | PKCE verifier for the token exchange. |
| `created` | float | `time.monotonic()`. |
| `status` | enum | `pending` → `success` \| `refused` \| `failed` \| `expired` |
| `email` | str \| None | From the verified ID token (`success`/`refused`). |
| `credentials_info` | dict \| None | Authorized-user info (`token`, `refresh_token`, `client_id`, `client_secret`, `token_uri`, `scopes`, `expiry`). Only when `success`. |
| `reason` | str \| None | User-facing reason for `refused`/`failed`. |

**Rules**
- **Expiry:** an entry older than `SIGNIN_TIMEOUT_SECONDS` (180 s) counts as `expired`, and is removed whenever the store is touched.
- **Callback:** the callback may change `pending` → a final state once only. A second callback for the same `state` finds a non-pending entry, or none, and shows "This sign-in link has already been used or has expired".
- **Consuming:** the originating session **pops** the entry once it reaches a final state. It is gone after one read.
- **Cookie check:** a callback whose `ftm_signin` cookie ≠ `browser_nonce` → `failed` ("complete the sign-in in the same browser you pressed Generate in").
- **Inactive session:** a callback whose `session_id` is no longer active → `failed`, and the entry is removed.

```text
pending ──callback ok + admitted──▶ success ──popped by session──▶ (gone)
   │  └─callback ok + not CL───────▶ refused ──popped──▶ (gone)
   │  └─exchange/verify error,
   │    wrong browser, denied ───────▶ failed  ──popped──▶ (gone)
   └─180 s, or tab closed───────────▶ expired ──removed──▶ (gone)
```

## SessionSignIn

`st.session_state["google_signin"]`

| Field | Type | Notes |
|---|---|---|
| `email` | str | Verified curiouslearning.org address. |
| `info` | dict | Authorized-user info passed to each pipeline run as `FTM_GOOGLE_CREDENTIALS`. |
| `at` | str | Sign-in time (display/log). |

**Rules**
- **When set:** only from a popped `success` entry.
- **When it ends:** it exists only in this session. A reload or a new tab is a new session, so there's no sign-in.
- **Replacing it:** it is cleared before a new sign-in starts (e.g. after a refusal). It is never copied to another session, the pending store or disk.

## Run (extends spec 001/004 `result`)

| New field | Notes |
|---|---|
| `account` | Email from `SessionSignIn`, also printed by the pipeline as `✅ Authenticated as <email>` (FR-015). |
| `auth_reason` | Reason shown under "Authentication failed" when the sign-in stage ends `refused`/`failed`/`expired`. |

The `authenticated` flag keeps its meaning: it is set by the pipeline's `✅ Authenticated as` line, which the steps and log depend on.

## Configuration (environment)

| Name | Where | Meaning |
|---|---|---|
| `FTM_OAUTH_CLIENT_FILE` | app | Path to the web OAuth client JSON (default `client_secret_web.json`). |
| `FTM_PUBLIC_URL` | app | Redirect URI / app base URL (default `http://localhost:8501/`). |
| `FTM_HOSTED` | app + scripts | `1` on a server: no desktop flow, no `token.json`, https required. Defined here; set by the separate hosting work. |
| `FTM_GOOGLE_CREDENTIALS` | pipeline subprocess only | Authorized-user JSON for this run (see [contracts/pipeline-credentials.md](contracts/pipeline-credentials.md)). |
