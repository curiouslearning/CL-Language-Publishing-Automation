# Data Model: Google Sign-In Restricted to Curious Learning Accounts

**Plan**: [plan.md](plan.md). Nothing here needs a database. State lives in the signed Streamlit
login cookie, in the Streamlit session, and in one append-only log file.

## Signed-in User

This comes from `st.user`, i.e. the Google ID token claims stored in Streamlit's signed cookie.

| Field | Source | Rule |
|---|---|---|
| `email` | `st.user["email"]` | Required. Must end with `@curiouslearning.org`. |
| `email_verified` | `st.user["email_verified"]` | Must be `true`. |
| `hd` | `st.user["hd"]` | Must equal `curiouslearning.org` (FR-002, FR-003). It is missing for personal Gmail accounts, which are therefore refused. |
| `iat` | `st.user["iat"]` | The sign-in is treated as expired if it's more than 8 hours old (FR-006). |
| `access_token` | `st.user.tokens["access"]` | Never logged, displayed or written to disk. It is handed only to the run subprocess (FR-009). |

**Status**: `allowed` if every rule passes, otherwise `refused`.

## Auth Check (per stage)

This is computed during each "Authenticating…" stage. It is not stored.

| Field | Meaning |
|---|---|
| `state` | `authenticating` → `signed_out` \| `refused` \| `expired` \| `ok` (see [contracts/auth-states.md](contracts/auth-states.md)) |
| `token_seconds_left` | `expires_in` from Google tokeninfo. Must be ≥ `MIN_TOKEN_SECONDS` before a run. |
| `token_audience_ok` | The tokeninfo `aud` equals our OAuth client ID. |
| `token_email_ok` | The tokeninfo `email` equals `Signed-in User.email`. |
| `token_scope_ok` | The scopes include `https://www.googleapis.com/auth/drive`. |

## Session (Streamlit `st.session_state`)

| Field | Meaning |
|---|---|
| `history` | Existing list of Run results for this browser session. It is now shown only when the state is `ok` (FR-008). |
| `refusal_logged` | A flag, so that a refused attempt is written to the access log once per session (FR-011). |

## Pending Request (server memory, `st.cache_resource`)

| Field | Meaning |
|---|---|
| key | The browser's `_streamlit_xsrf` cookie value |
| `languages` | The comma-separated languages entered before sign-in, each already validated |
| `created` | When the request was saved. It's discarded after 10 minutes (FR-001a). |

It is consumed once, on return from a successful sign-in, and discarded on refusal, expiry or a
not-signed-in return. It holds no lock and starts no process.

## Run *(extends spec 001)*

| New field | Meaning |
|---|---|
| `user_email` | The account that started the run (FR-010). It becomes the first log line: `👤 Started by: <email>`. |
| `package_zip` | Built on demand after a run finishes as `complete` or `warning`, from `lang/<lang.lower()>/` (amendment A4). |

The rest is unchanged from spec 001, including the states `running` → `complete` \| `warning` \|
`error`.

## Access Log Entry (`language_automation/logs/access.jsonl`)

There is one JSON object per line. The file is append-only and gitignored.

| Field | Type | Notes |
|---|---|---|
| `ts` | ISO-8601 UTC string | |
| `event` | `signin_ok` \| `signin_refused` \| `token_expired` \| `run_started` \| `run_finished` | |
| `email` | string or null | Null if Google didn't return one |
| `hd` | string or null | Only on `signin_refused` |
| `lang` | string | Only on run events |
| `outcome` | `complete` \| `warning` \| `error` | Only on `run_finished` |

Tokens are never included.

## Language Paths *(consistency fix, R7)*

| Path | Rule |
|---|---|
| Package folder | `lang/<lang.lower()>/` |
| Content file | `lang/<lang.lower()>/ftm_<lang.lower()>.json` |
| Audio folder | `lang/<lang.lower()>/audios/` |

**Validation**: `lang` must match `^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$`. Anything else is rejected
before any Drive lookup or folder operation.
