# Data Model: React Frontend

All page state is in tab memory (React state). Nothing is written to browser storage.

## Run (page)

| Field | Type | Notes |
|-------|------|-------|
| id | string | page-local key |
| lang | string | as typed (trimmed) |
| started | string | `YYYY-MM-DD HH:MM:SS` (local time), used in file names like today |
| state | `running` \| `complete` \| `warning` \| `error` \| `cancelled` | |
| title | string | status title, e.g. "Step 5/7 · Download audio files from Drive" |
| authenticated | boolean | set by the `✅ Authenticated as` line |
| auth | {kind, text} | the authentication message box |
| account | string? | email |
| step | number? | index into STEPS |
| reached | number[] | optional steps reached |
| details | Record<number,string> | per-step progress text |
| note | {kind, text}? | message under the steps |
| finalStepsState | `complete` \| `error` \| null | how the step icons are drawn at the end |
| log, errors, missing, deleted, lookalike, standardized | string[] | same meaning as `app.py`'s result |
| unusedChecked, missingChecked | boolean | |
| inMissingList, audioTotal, audioDone | parser state | |
| ai | AiReport? | report JSON from `🤖 AI report:` |
| aiLog | string[] | |
| aiRunning | boolean | title shows "🤖 AI language check in progress…" |
| mp3Count | number? | from the server's `end` event |
| package | {status: `fetching` \| `ready` \| `error` \| `replaced`, blob?, error?} | null = no package |

## Sign-in (page)

`{ token, email, expiresAt }` or null. Cleared when a run is refused.

## Server state (process memory)

- **Run lock**: one `threading.Lock`; held from the start of `/api/runs` to the end of the stream.
- **Package registry** (`run_store`): `lang key → {package_id, active, finished_at, fetched}`. A new claim replaces the entry; `finish(touched=False)` restores the previous entry. Hosted janitor deletes inactive, fetched-or-expired entries (10 min) that a run in this process claimed.
