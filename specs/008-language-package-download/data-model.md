# Data Model: Language Package Download

All state is in-process and in memory (single Cloud Run instance). Nothing is persisted.

## PackageEntry (registry, keyed by `lang.strip().lower()`)

| Field | Type | Rules |
|---|---|---|
| `owner_session` | str | Streamlit session id of the run that last claimed the language |
| `run_id` | str | uuid4 hex. A new one for every run; equals that run's `result["package_id"]` |
| `active` | bool | True from claim (before the pipeline subprocess starts) until the run, including the AI check, has ended. Never deleted while True |
| `inactive_since` | float \| None | Monotonic time the janitor first saw `owner_session` disconnected. Reset to None if it reconnects |

The registry is one dict guarded by one `threading.Lock`, created once per process (`st.cache_resource`). It has exactly one entry per language folder that a run has claimed.

### Lifecycle

```text
claim(lang, session, run_id)  ──>  active ──(run ends, any outcome)──> finished (active=False)
        ▲                                                                   │
        │ new claim by any session replaces the entry (old run → "replaced") │
        └───────────────────────────────────────────────────────────────────┤
                                     hosted only: owner disconnected ≥ 60 s │
                                                                            ▼
                                                  rmtree lang/<lang>/ + drop entry
```

## Run result (existing dict in `st.session_state.history`)

| New field | Type | Rules |
|---|---|---|
| `package_id` | str \| absent | Set when the pipeline subprocess is started (after sign-in). Absent for runs that never started the pipeline |

## Package availability (derived, never stored)

| State | Condition | Shown |
|---|---|---|
| `available` | result `state` ∈ {complete, warning}, entry exists, `entry.run_id == package_id`, not `active`, JSON file and folder exist | Download button (+ hosted note) |
| `regenerating` | entry `active` | "being generated again" note |
| `replaced` | entry exists with a different `run_id`, not active | "replaced by a later run" note |
| `gone` | no entry, or folder/JSON missing | "no longer on the server" note |
| (none) | result `state` ∈ {error, cancelled}, or no `package_id` | nothing |

## Zip file (built per click)

- Name: `<Language as typed>_<started with ":"→"-" and " "→"_">.zip`, the same stamp as the log download.
- Entries (ZIP_STORED), with `<lang>` = the lowercase folder name:
  - `<lang>/` and `<lang>/images/` (directory entries);
  - `<lang>/ftm_<lang>.json`;
  - `<lang>/audios/<file>.mp3` (every regular file in `audios/`);
  - plus any other regular file in the folder, relative path kept.
- Excluded by construction: anything outside `lang/<lang>/`. Symlinks are not followed.
