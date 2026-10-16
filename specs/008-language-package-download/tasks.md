# Tasks: Language Package Download

**Input**: Design documents from `specs/008-language-package-download/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/package-download.md, quickstart.md

**Tests**: no automated suite (constitution). Verification uses a throwaway scratch script (quickstart V1, not committed) plus manual local/hosted checks.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 = download after a run, US2 = session cleanup (hosted), US3 = earlier runs in the same visit

---

## Phase 1: Setup

- [X] T001 Confirm the baseline:
  - `python -c "import streamlit; print(streamlit.__version__)"` prints `1.64.0`, matching the `requirements.txt` pin;
  - `inspect.getsource(st.download_button)` mentions deferred callables (research R1).

  Stop if not: the deferred-data design depends on it.

---

## Phase 2: Foundational (blocks all stories)

**Purpose**: the registry that all three stories read. File: `language_automation/package_store.py` (new). No Streamlit import at module level.

- [X] T002 Create `language_automation/package_store.py` with:
  - the module docstring (spec 008; logic only, wiring in `app.py`);
  - imports `io, os, shutil, threading, time, uuid, zipfile` and `lang_paths`;
  - `class Unavailable(Exception)`;
  - a module-level `_entries = {}` and `_lock = threading.Lock()`;
  - `_key(lang)` returning `lang.strip().lower()`.

  Entry fields, per data-model.md:
  - `owner_session` (str);
  - `run_id` (str, "uuid4 hex. A new one for every run");
  - `active` (bool, "Never deleted while True");
  - `inactive_since` (float | None, "Reset to None if it reconnects").
- [X] T003 In `language_automation/package_store.py`, implement `claim(lang, session_id) -> run_id`. It creates a new `uuid.uuid4().hex` and **replaces** any existing entry with `{owner_session: session_id, run_id, active: True, inactive_since: None}` under `_lock`.
- [X] T004 In `language_automation/package_store.py`, implement `finish(lang, run_id)`: under `_lock`, if the entry still has this `run_id`, set `active=False`.
- [X] T005 In `language_automation/package_store.py`, implement `availability(lang, run_id, state)`, following data-model.md "Package availability":
  - return `None` if `state` not in `("complete", "warning")` or `run_id` is falsy;
  - `"regenerating"` if the entry is `active`;
  - `"replaced"` if the entry exists with a different `run_id`;
  - `"gone"` if there's no entry, or `lang_paths.json_path(lang)` / `lang_paths.lang_dir(lang)` is missing;
  - else `"available"`.

**Checkpoint**: registry importable: `python -c "import package_store"` from `language_automation/`.

---

## Phase 3: User Story 1 - Download the package right after a run (P1) 🎯 MVP

**Goal**: one-click zip of `lang/<language>/` after a complete or warning run, no rerun.

**Independent Test**: quickstart V2 (local) and V3 (hosted).

- [X] T006 [US1] In `language_automation/package_store.py`, implement `build_zip(lang, run_id) -> bytes`:
  - if `availability(lang, run_id, "complete") != "available"`, raise `Unavailable` with the state;
  - write a `zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_STORED)` whose entries all sit under `<lang>/`, where `<lang>` is `os.path.basename(lang_paths.lang_dir(lang))`;
  - add explicit directory entries `<lang>/` and `<lang>/images/`;
  - walk `lang_paths.lang_dir(lang)` with `os.walk(followlinks=False)`, adding every regular file (skip symlinks) at `<lang>/<relative path with forward slashes>`;
  - re-check that the entry's `run_id` is unchanged after writing (raise `Unavailable("replaced")` if not), then return `buffer.getvalue()` and close the buffer.

  Zip rules from data-model.md: "Entries (ZIP_STORED)", "Excluded by construction: anything outside `lang/<lang>/`. Symlinks are not followed."
- [X] T007 [US1] In `language_automation/app.py` `run_pipeline`:
  - right before `subprocess.Popen` (after sign-in succeeded), set `result["package_id"] = package_store.claim(lang, get_script_run_ctx().session_id)`;
  - make sure `package_store.finish(lang, result["package_id"])` runs **after** the `after(result, status)` AI step, in a `try/finally` around the section from `Popen` through `after(...)`, so it also runs on cancellation and exceptions.

  Add `import package_store` with the other local imports.
- [X] T008 [US1] In `language_automation/app.py`, add `render_package(result, stamp)` and call it in `render_summary` right **before** the final `st.download_button(**log_button)`. That's after the mp3 count caption, and only on the authenticated path. Behaviour, per contracts/package-download.md:
  - `available` → `st.download_button("📦 Download language package (.zip)", data=lambda: package_store.build_zip(lang, pid), file_name=f"{result['lang']}_{stamp}.zip", mime="application/zip", key=f"pkg_{result['lang']}_{result['started']}", on_click="ignore", type="primary")`. Bind `lang`/`pid` as lambda defaults.
  - Then a caption: hosted (`ai_providers.is_hosted()`) → `Kept on the server only until you close or reload this page. Download it now.`; local → `` Also saved in `lang/<lang lower>/` on this computer. ``
  - `regenerating` / `replaced` / `gone` → the exact `st.caption` texts from the contract (`📦 <Lang> is being generated again right now, so this package isn't available.` / `📦 This package was replaced by a later run of <Lang>. Download it from that run.` / `📦 This package is no longer on the server. Generate <Lang> again to get it.`).
  - `None` → nothing.
- [ ] T009 [US1] Manual check, quickstart V2 (local, `FTM_HOSTED` unset):
  - generate `Marathi`; the button and the local caption appear;
  - the downloaded zip unpacks to `marathi/` with the same file list as `lang/marathi/` and an identical JSON;
  - clicking doesn't rerun the page;
  - closing the tab leaves `lang/marathi/` in place.

**Checkpoint**: MVP: the download works locally and on Cloud Run (no cleanup yet).

---

## Phase 4: User Story 2 - The package is cleaned up when the session ends (P1)

**Goal**: on the hosted page, a session's packages are deleted within 2 minutes after it ends. Others are untouched; nothing changes locally.

**Independent Test**: quickstart V1 (logic) + V4 and V5 (hosted).

- [X] T010 [US2] In `language_automation/package_store.py`, implement `sweep(is_alive, now, grace=60) -> list[str]`. Under `_lock`:
  - **Owned entries:** for each entry with `active` False:
    - if `is_alive(owner_session)`, set `inactive_since=None`;
    - else set `inactive_since` to `now` if it is None;
    - once `now - inactive_since >= grace`, `shutil.rmtree(lang_paths.lang_dir(key), ignore_errors=True)`, delete the entry, and print `🧹 Cleaned up lang/<key> (session ended)`.
  - **Orphans:** for each sub-folder of `lang_paths.LANG_ROOT` (if it exists) whose name isn't a registry key, `rmtree` it and print `🧹 Cleaned up lang/<name> (no owner)`.
  - **Never** delete an entry while `active` is True.
  - Return the removed keys. Wrap each removal in `try/except OSError`, printing a `⚠ Cleanup failed` line, so one failure doesn't stop the sweep.
- [X] T011 [US2] In `language_automation/package_store.py`, implement `start_janitor(is_alive, interval=15, grace=60)`. It starts one daemon thread looping `sweep(is_alive, time.monotonic(), grace)` then `time.sleep(interval)`, catching and printing any exception so the loop survives. Guard it with a module-level flag so a second call is a no-op.
- [X] T012 [US2] In `language_automation/app.py`, add:

  ```python
  @st.cache_resource
  def package_janitor():
      if ai_providers.is_hosted():
          package_store.start_janitor(session_alive)
      return True
  ```

  Call `package_janitor()` once near the top of the page, after `st.set_page_config`. Locally, it starts nothing (FR-010).
- [X] T013 [US2] In `language_automation/app.py` `existing_audio_count(lang)`, when `ai_providers.is_hosted()`, return 0 unless `package_store.owned_by(lang, get_script_run_ctx().session_id)` (research R6). Add `owned_by(lang, session_id)` to `language_automation/package_store.py`: True if the entry exists, isn't `active`, and `owner_session == session_id`. Local behaviour is unchanged.
- [X] T014 [US2] Run quickstart V1 with a scratch script in the session scratchpad (not in the repo). Using fake `lang/zz_*` folders, verify:
  - grace timing;
  - another session's package kept;
  - orphan removed;
  - `active` entries never removed;
  - `build_zip` entries;
  - `replaced` after a second claim, and `build_zip` then raising `Unavailable`.

  Delete the fake folders afterwards.

---

## Phase 5: User Story 3 - Several languages in one visit (P2)

**Goal**: runs under "Previous runs" keep their download while the session is open.

**Independent Test**: generate A, "Add another language", generate B, then download A from Previous runs.

- [X] T015 [US3] Confirm in `language_automation/app.py` that `show_run` → `render_summary` → `render_package` is used for **both** "Latest run" and "Previous runs", with the `key` unique per run (`pkg_<lang>_<started>`). Fix it if any path skips `render_package`. With an unchanged registry entry, an earlier run of a different language stays `available`.

---

## Phase 6: Polish & Cross-Cutting

- [X] T016 [P] Update `CLAUDE.md`:
  - **Web UI section:** a "Package download (spec 008)" bullet covering the button, deferred zip on click (`on_click="ignore"`), the availability states and their notes, `package_store.py`, `result["package_id"]`, and that the hosted "already generated" dialog only counts this session's packages.
  - **Hosting section:** replace "Not done yet: getting the generated package off the server (R10's zip download)." with the session cleanup: janitor every 15 s, 60 s grace, orphans, `🧹 Cleaned up` server-log lines, hosted only.
  - **Spec list:** add `008-language-package-download`.
- [X] T017 [P] Update `README.md`:
  - "What a run does": add step 5, "Offers the package as a zip to download".
  - Usage: a note that on the hosted page the package is kept only until the tab is closed or reloaded, so download it right away.
  - The layout table's `specs/` row: "(001–008)".
- [ ] T018 Deploy (`gcloud builds submit --config cloudbuild.yaml --project=ftm-language-generator`). Then run quickstart V3, V4 and V5 on the service URL:
  - download;
  - batch download mid-run;
  - tab close → `🧹` log line within 2 minutes (`gcloud run services logs read ftm-language-generator --region=us-central1 --project=ftm-language-generator --limit=50`);
  - two-tab isolation;
  - mid-run close;
  - reload;
  - replaced/regenerating notes.
- [ ] T019 Quickstart V6: generate the largest available language, download it, and watch Cloud Run memory metrics. If the service restarts or runs out of memory, set `--memory=4Gi` in `cloudbuild.yaml`, redeploy and repeat. Record the package size and peak memory in `specs/008-language-package-download/research.md` R2.
- [X] T020 Quickstart V7: `python generate_language.py Hausa` from `language_automation/` behaves as before, and nothing under `lang/` is deleted afterwards.
- [ ] T021 Set Status to "Implemented" in `specs/008-language-package-download/spec.md` and tick completed tasks here.

---

## Dependencies & Execution Order

- T001 → T002 → T003 → T004 → T005 (all in `package_store.py`, sequential).
- **US1**: T006 (`package_store.py`) → T007 → T008 (`app.py`, sequential) → T009.
- **US2**: T010 → T011 (`package_store.py`) → T012, T013 (`app.py`, after T007/T008 to avoid edit clashes) → T014. US2 needs the claim/finish wiring from T007.
- **US3**: T015 after T008.
- **Polish**: T016 ∥ T017 any time after the design is settled. T018 needs all code tasks. T019 needs T018. T020 any time after T007.

### Parallel opportunities

- T016 ∥ T017 (different docs). T014 (scratch script) can run alongside T012/T013, since it touches only `package_store.py` logic, already complete.
- `package_store.py` and `app.py` tasks are otherwise sequential: two files, each edited by several tasks.

### Parallel example: User Story 2

```text
T014 scratch-script verification of sweep()/build_zip()   (package_store.py done)
T012/T013 app.py wiring                                    (different file)
```

## Implementation Strategy

1. **MVP** = Phases 1–3: the download works (locally verified). Deployable on its own, but the hosted memory isn't freed yet.
2. Add **US2** before the hosted rollout, since cleanup is the user's explicit requirement. Deploy US1 + US2 together (T018).
3. **US3** is a confirmation pass.
4. Then Polish: docs, the large-package memory test, CLI regression.
5. Don't deploy while someone is running a language: the new revision replaces the running one.
