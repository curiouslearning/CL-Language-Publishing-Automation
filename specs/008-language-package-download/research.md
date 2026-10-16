# Research: Language Package Download

Findings checked against the installed Streamlit **1.64.0** (`requirements.txt` pins it) and against `app.py` as it is today.

## R1. How the zip reaches the browser

- **Decision**: use `st.download_button` with **deferred data**: `data=<callable>`, `on_click="ignore"`, `mime="application/zip"`.
  - The zip is only built when the user clicks.
  - Streamlit runs the callable on a worker thread (`DeferredFileHandler` → `asyncio.to_thread(media_file_mgr.execute_deferred)`), not on the script thread. So a click works while this session's script is busy with another language in the same batch, and triggers no rerun (FR-004).
- **Rationale**:
  - Passing bytes directly (`data=bytes`) would build every shown run's zip on every rerun, and keep them all in memory for the whole session. That conflicts with FR-012.
  - Deferred data builds one zip per click. Streamlit keeps that result only until the session's next rerun or its end (`clear_session_refs` / orphan pruning), then frees it.
- **Alternatives**:
  - A custom HTTP route (Tornado handler) streaming the zip. It needs session auth of its own and goes beyond Streamlit's public API.
  - Writing the zip to `/tmp` and serving it as a file. On Cloud Run `/tmp` is memory too, so there's no gain, and it would need extra cleanup.

## R2. Zip format and memory

- **Decision**:
  - Build with `zipfile.ZipFile(BytesIO(), "w", ZIP_STORED)`. mp3 is already compressed, so storing avoids CPU time for ~0% gain. The JSON is tiny.
  - Entries are `<language>/ftm_<lang>.json`, `<language>/audios/*.mp3`, and `<language>/images/` (an explicit directory entry, so it exists even when empty). `<language>` is the lowercase folder name, as in `lang/`.
  - Return `buffer.getvalue()` and drop the buffer.
- **Memory**: peak ≈ package files (already in memory) + zip bytes (≈ package size) + a brief second copy during `getvalue`/Streamlit's bytes conversion. That's about 3× the package size at peak and 2× until the session's next rerun. For 300 MB that's ≈ 0.9 GB peak on top of the app (~300 MB), under 2 GiB if no other large package is held. Session cleanup (R4) keeps other sessions' packages from piling up.
- **Decision on memory limit**: keep `--memory=2Gi`. The quickstart V6 test (300 MB) decides it. If it fails, raise it to `4Gi` in `cloudbuild.yaml`. The cost is minor, since billing is per request.
- **Alternatives**: `ZIP_DEFLATED` (CPU-heavy, no size gain on mp3); streaming zip generators (Streamlit's deferred API needs the complete bytes).

## R3. Knowing a package is still "this run's" (FR-006)

- **Decision**: a process-wide **package registry** (`st.cache_resource`, guarded by a `threading.Lock`) keyed by `lang.strip().lower()`. Each entry holds `{owner_session, run_id, active}`.
  - `run_pipeline` **claims** the language with a new `run_id` (uuid4 hex) right before starting the pipeline subprocess, i.e. before the wipe. It **finishes** the claim (`active=False`) when the subprocess and the AI check are done, in `finally`.
  - The run's `result["package_id"]` stores that `run_id`.
  - Availability at render and again inside the click callable:
    - `available`: entry exists, `run_id` matches, not active, folder and JSON exist;
    - `replaced`: entry with another `run_id` (any session);
    - `regenerating`: entry with this or another `run_id` and `active`;
    - `gone`: no entry, or the folder is missing.
  - If the state changes between render and click, the callable raises and Streamlit shows its own "failed to generate file" error. The next rerun shows the right note.
- **Rationale**: one instance (spec 005 R8), so in-process state is the truth, the same as the existing one-run lock and sign-in store.
- **Alternatives**: comparing folder modification times (fragile; the AI check and step 3c rewrite the JSON); a marker file inside the package (it would end up in the zip, or need excluding).

## R4. Detecting the end of a session and cleaning up (FR-009 to FR-011)

- **Decision**: a single **janitor** daemon thread, started once per process via `st.cache_resource`, **only when `FTM_HOSTED=1`**. Every 15 s, under the registry lock:
  1. For each entry that's not `active`: if `Runtime.instance().is_active_session(owner)` is false, record `inactive_since` (first time seen). If it has been inactive for **≥ 60 s**, `shutil.rmtree` the folder and drop the entry. If the session is active again (a reconnect), clear `inactive_since`.
  2. **Orphans**: a folder that a run **in this process** claimed, but that no registry entry owns any more, is removed. For example, a run that stopped before the wipe and had no earlier owner. **Folders that already existed when the process started are never deleted.** Implementation finding: the first version removed every unregistered folder, and a local smoke test with `FTM_HOSTED=1` deleted a developer's `lang/marathi/`. A fresh Cloud Run instance starts empty anyway, so limiting the sweep to `_claimed` loses nothing.
  3. Each removal prints `🧹 Cleaned up lang/<lang> (session ended)` to the server log (Cloud Logging). This is not part of the pipeline's log contract.
- **Timing**: worst case 60 s grace + 15 s interval + delete time, well under the 2-minute requirement (SC-005).
- **Runs cancelled by tab close**: `run_pipeline` already kills the subprocess within 0.2 s of `is_active_session` turning false. Its `finally` marks the claim not active, and the janitor deletes the partial folder after the grace period (US2-4). The `active` flag guarantees the janitor never deletes under a running pipeline.
- **Why `is_active_session`**: it's the same signal the page already trusts for cancellation (spec 004). The 60 s grace covers brief disconnects that reconnect with the same session.
- **Alternatives**:
  - Streamlit has no public session-end callback.
  - `st.context`/websocket hooks are internal.
  - Deleting right after a download was rejected: the user may need to re-download in the same session (US1-5).

## R5. Local vs hosted

- **Decision**: the registry and availability checks run everywhere (one code path; "replaced by a later run" is useful locally too). The janitor and orphan sweep run only with `ai_providers.is_hosted()` true. The hosted caption about temporary storage is shown only when hosted. Locally the caption says the package is also in `lang/<language>/`.
- **Rationale**: FR-010: local `lang/` is the developer's working output.

## R6. "Already generated" dialog on the hosted page

- **Decision**: when hosted, `existing_audio_count` only counts a language whose registry entry is owned by **this** session and not active. Folders owned by other sessions are treated as not existing, so the run proceeds and takes ownership (they'll see "replaced"). Locally, unchanged.
- **Rationale**: otherwise answering "No" would leave the user with a package they don't own and can't download.

## R7. Link privacy (FR-013)

- **Finding**: Streamlit serves the generated file at `/media/<random id>.zip`. The id is random, sent only to the clicking session, and pruned on the session's next rerun or end. The media endpoint itself doesn't check the session.
- **Decision**: accept. The link is unguessable, short-lived and never shown in the page. The download is only created for a signed-in session. Documented in CLAUDE.md.
- **Alternatives**: a custom authenticated route (see R1), rejected as disproportionate.

## R8. Where the code lives

- **Decision**: a new module `language_automation/package_store.py` holds the registry, `availability()`, `build_zip()` and the janitor loop, with session liveness passed in as a function. It has no Streamlit import at module level, so it can be exercised from a plain Python script (quickstart V1). `app.py` wires it in.
- No new dependency: only `zipfile`, `io`, `shutil`, `threading`, `uuid` from the standard library.
