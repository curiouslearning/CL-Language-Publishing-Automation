# Implementation Plan: Language Package Download

**Branch**: `008-language-package-download` (spec folder; work stays on `main`) | **Date**: 2026-10-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-language-package-download/spec.md`

## Summary

After a complete or warning run, the summary offers **📦 Download language package (.zip)**. The zip is built **only on click**, on a Streamlit worker thread, using `st.download_button` deferred data (Streamlit 1.64), so it never reruns the page or interrupts a run.

A new module `package_store.py` keeps a process-wide registry: language → owning session, `run_id`, active flag. That registry says whether a run's package is still the current one (available / regenerating / replaced / gone).

**On the hosted page only** (`FTM_HOSTED=1`), a janitor thread checks every 15 s. It deletes `lang/<language>/` once its owning session has been disconnected for 60 s, downloaded or not, and also removes folders nobody owns. The memory is freed within 2 minutes of the tab closing. Locally nothing is deleted.

## Technical Context

**Language/Version**: Python 3.13 (container), Python 3 locally

**Primary Dependencies**: Streamlit 1.64.0 (deferred `download_button` data, `Runtime.is_active_session`). Standard library only for the rest (`zipfile`, `io`, `shutil`, `threading`, `uuid`). No new dependency.

**Storage**: none persistent. Packages are in the container's in-memory filesystem; the registry is an in-process dict.

**Testing**: no suite (constitution). A scratch script for the registry/janitor logic (quickstart V1), plus manual local and hosted checks (V2–V7).

**Target Platform**: Cloud Run (`ftm-language-generator`, 1 instance, 2 GiB), and local Streamlit

**Project Type**: Streamlit web page + CLI scripts

**Performance Goals**: zip ready within 10 s for 10–50 MB (ZIP_STORED, no compression); cleanup within 2 min of session end

**Constraints**: peak memory ≈ 3× the package size during a download (R2). Never delete while a run is active; never delete another open session's package; never delete locally.

**Scale/Scope**: 1 new module (~120 lines), `app.py` wiring (~40 lines), docs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Verify before you touch disk | ✅ | The pipeline order is unchanged. Cleanup only deletes **hosted** folders whose owning session ended, or that nobody owns. It never touches a folder during an active run, and never deletes locally, so no previously good local build can be destroyed. A hosted package is by design not meant to outlive its session (user decision). |
| II. Exact language matching | ✅ N/A | |
| III. JSON is source of truth for audio | ✅ | The zip contains exactly what the pipeline left. Nothing is renamed or filtered. |
| IV. Stable log contract | ✅ | No pipeline prefix changes. The `🧹 Cleaned up` lines go to the server log only, not through `app.py` parsing. |
| V. No secrets | ✅ | The zip is built only from `lang/<lang>/` (no credentials can be in it). The media link is random and short-lived (R7). |
| Tech: no new dependency | ✅ | stdlib only |
| Tech: path casing via `lang_paths` | ✅ | All paths come from `lang_paths.lang_dir/json_path/audios_dir` |
| Workflow: CLAUDE.md updated | ✅ | Planned (Web UI, Hosting; remove the "Not done yet" note) |
| Workflow: manual verification with a real language | ✅ | quickstart V2–V4 |

**Post-design re-check**: passes. No Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/008-language-package-download/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/package-download.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code

```text
language_automation/
├── package_store.py    # NEW: registry (claim/finish/availability/owned_by), build_zip, sweep, start_janitor
└── app.py              # claim before Popen + finish in finally; package section in render_summary;
                        # hosted existing_audio_count uses owned_by; start janitor (hosted, cache_resource)
CLAUDE.md               # Web UI: package download; Hosting: session cleanup, remove "Not done yet"
README.md               # "What a run does" / Usage: download + temporary on the hosted page
cloudbuild.yaml         # only if V6 shows 2Gi isn't enough: --memory=4Gi
```

**Structure Decision**: one new module next to the existing ones in `language_automation/`, following the `web_signin.py` pattern (logic in a module, Streamlit wiring in `app.py`).

## Complexity Tracking

None.
