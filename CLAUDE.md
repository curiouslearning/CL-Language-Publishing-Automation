# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Tooling for publishing new languages for Curious Learning's **Feed the Monster (FTM)** game. There's no build system, no tests and no linter. Dependencies are pinned in `requirements.txt`. All the code is in `language_automation/`, a set of standalone Python scripts that pull one language's content JSON and audio files from Google Drive into `lang/<language>/`. A Streamlit web page (`app.py`) wraps them for the content team.

Two older Google Cloud Functions (`content_checking_script.py` and `assessment_content_checking_script.py`) checked Drive for missing audio and emailed a report. They were removed from this repo on 2026-10-05. Removing them doesn't affect any deployed copies. Assessment-content checking isn't covered by the pipeline.

Spec-driven workflow (GitHub spec-kit, `/speckit-*` commands): project rules are in `.specify/memory/constitution.md`, and feature specs go in `specs/NNN-*/`. Update the matching spec whenever behaviour changes.
- `001-baseline-language-pipeline`: the pipeline as built.
- `002-google-domain-login`: curiouslearning.org-only sign-in. Revised to use the existing `credentials.json` flow; the Streamlit login was removed.
- `003-ai-language-check`: the optional AI review.
- `004-generator-page-flow`: the web page as built (authentication display, one click per run, cancellation, regenerate prompt, Add another language).

## Running the pipeline

Run every script from inside `language_automation/`. `credentials.json` and `token.json` are read relative to the CWD. Language data paths come from `lang_paths.py` and are anchored to that folder.

```bash
cd language_automation
python generate_language.py Hausa           # full pipeline (entry point)
python -m streamlit run app.py              # web UI (the `streamlit` exe isn't on PATH here): runs generate_language.py as a
                                            # subprocess and turns its emoji-prefixed log lines into step notes

# individual steps, for debugging
python fetch_lang_sheet.py Hausa            # sheet -> Unity URL -> ftm_<lang>.json
python fetch_drive_audios.py Hausa          # download + convert audios
python check_missing_audios.py Hausa        # report audio referenced by JSON but not on disk
python fetch_unity_json.py <URL> <OUT_PATH>
```

What you need installed: `python -m pip install -r requirements.txt` and `ffmpeg` on PATH (non-mp3 audio is converted to 44.1 kHz stereo 192k mp3).

### Google sign-in

There is no separate login. The pipeline's own OAuth flow is the only authentication.
- **The flow:** a browser sign-in uses `credentials.json` and caches the result in `token.json`. It runs on the machine running the scripts or `app.py`. Delete `token.json` to re-auth.
- **Scopes:** `fetch_lang_sheet.py` and `fetch_drive_audios.py` ask for different scopes but share this token.
- **Domain check:** `generate_language.authenticate()` runs first and prints `🔐 Authenticating with Google...`. It asks Drive which account signed in (`about.user.emailAddress`). Anything that isn't `@curiouslearning.org` is refused: it deletes `token.json` and exits 1 before Step 1. On success it prints `✅ Authenticated as <email>`.

### Web UI (`app.py`)

- **On Generate:** the run's box shows only "Authentication in progress" (plus the sign-in link when Google asks). The steps and the log appear only after the `✅ Authenticated as` line.
- **On failure:** if sign-in fails or is refused, the box says "Authentication failed", with no steps.
- **One click per run:**
  - Generate goes through `on_generate`, which validates and queues the run, and the form clears on submit.
  - The input and the Generate button are **disabled** while a run is queued or running, or while another tab or user holds the lock.
  - Any rerun mid-run would interrupt and kill the run, so download buttons use `on_click="ignore"`.
  - After the run, `st.rerun()` re-enables the form, and the run is shown expanded under "Latest run".
- **Already generated:** if `lang/<language>/` already has its JSON and at least one mp3 (`existing_audio_count`), a dialog asks "Do you need to regenerate this language?".
  - **Yes** regenerates.
  - **No**, or closing the dialog, keeps the existing package and runs only the languages that don't exist yet.
- **Add another language:** when every run in the last batch is `complete` or `warning` and nothing is busy, a success banner with **➕ Add another language** appears above "Latest run", with a second button below the results. `start_new_language` sets `last_batch = 0` (the run moves to Previous runs), clears `lang_input`, and sets `focus_form`. On the next render, a fixed `st.html(..., unsafe_allow_javascript=True)` script scrolls to the top and focuses the language box. Spec 004 records the whole page flow.
- **AI language check toggle** (`key="ai_check"`, off by default, disabled while busy): when it's on, `run_pipeline(lang, after=ai_step)` runs `ai_language_check.py` as a subprocess after the pipeline, under the same lock and tab-close cancel. It only runs if the user is authenticated, the run wasn't cancelled, and the game JSON exists. While it runs, only the run's title says so: nothing appears under the steps. Its output and warnings go to a separate `result["ai_log"]`, never into the pipeline log. `render_summary` shows `render_ai_section` and `render_ai_log` (an "AI check log" expander and a "Download AI log" button) right after the unused-audio result. When it's off, nothing is called.
- **Cancellation:** a run is cancelled, and the one-run lock released, if its browser tab closes (`Runtime.is_active_session`). It's also cancelled if a Google sign-in isn't completed within `SIGNIN_TIMEOUT_SECONDS` (3 min).

## AI language check (`ai_language_check.py` + `ai_providers.py`, spec 003)

`python ai_language_check.py Hindi` reviews an already generated `ftm_<lang>.json`. It's advisory: it never writes to `lang/` or the sheet, and never fails a run.

- **Items:** `build_items` collapses the puzzles into unique items (Indian English: 750 puzzles become 255 items, about 1.5 K tokens). Each item is one compact line. Recording names are sent only when they differ from the expected letter or word (`recording_differs`).
- **Code checks, no AI:** `consistency_warnings` reports letters that don't spell the word, and a letter that isn't in the word. These are always reported, even when the AI is unavailable.
- **AI checks, one request, never retried** (the only exception is Gemini's `fallback_models`, after a busy or 404 answer that used no tokens; see Config):
  - The AI reports misspelled words, letters foreign to the language, bad feedback sentences and mismatched recording names.
  - Both providers get the same JSON Schema (`ai_output_schema.json`). Claude uses `output_config.format` with `max_retries=0`; Gemini uses `response_json_schema`.
  - Any failure, including a rate limit, gives `status: "unavailable"` with the reason. It's never reported as "no issues".
- **Cache:** `.ai_cache/<sha256(provider|model|lang|item lines)>.json`. Unchanged content reuses the earlier result and makes **no** API call. Only successful results are cached.
- **Config:** two files in `language_automation/`.
  - **`config.json`** is tracked and holds no secrets. `"provider": "gemini"` (default, free key) or `"claude"` (paid), plus each provider's `model`.
    - Gemini also accepts `temperature` and `max_output_tokens`. These are only sent when set; a cut-off answer (`MAX_TOKENS`) is reported as such.
    - `fallback_models` are tried in order **only** after a busy (5xx) or not-usable-by-this-key (404) answer. Neither uses tokens. Google's message for each is kept in the report. A 429 or a bad key stops immediately.
    - `python ai_language_check.py --list-models` lists the models the key can use. It's a free lookup.
    - Claude has `effort` (default `low`) and `fallbacks` (default `true`, which sends `fallbacks="default"`; set it to `false` if the API rejects it alongside structured output).
  - **`.env`** is gitignored, with `.env.example` as the template. It holds `GEMINI_API_KEY=` and `ANTHROPIC_API_KEY=`, read by `read_env_file` (no python-dotenv). Real environment variables win over `.env`. An `api_key` in `config.json` is ignored.
  - It never switches to the other provider silently.
- **Output contract:** `🤖 AI check:` and `⚠ AI check:` progress lines, then a last line `🤖 AI report: <json>`. Never use `❌` for findings, or `app.py` would count them as pipeline errors.

## Pipeline architecture (`generate_language.py`)

0. **`verify_language_on_drive`**: before anything on disk is touched, require both the language sheet (`find_language_sheet`) and the audio folder (`find_language_audio_folder`) to exist on Drive. If either is missing, exit 1 without creating or wiping any folder. Keep this ordering.
Before step 0, `lang_paths.validate_language_name` rejects anything except letters, digits, spaces, `-` and `_`. Then `authenticate()` runs (see Google sign-in above), and its Drive service is passed to step 0.

1. **Wipe** `lang/<language>/` with `shutil.rmtree`. Every run starts from scratch, but mp3s that already exist are skipped during download within a single run.
2. Create `audios/` and `images/`. `images/` isn't populated yet.
3. **`fetch_lang_sheet`**: in the Drive folder `18SRLdZK-...`, find the spreadsheet whose name **exactly** matches the language, ignoring case and any `.xlsx`/`.xls` extension (`is_exact_name`). Drive's `name contains` query only narrows the list. If it's an Excel file, first copy it to a Google Sheet (a `_converted` copy stays in Drive). Read the **hyperlink in cell `metadata!D1`** (`run_unity_check.py`). That's the Unity/Cloud Function URL that generates the game JSON. `fetch_unity_json` accepts only `https://` URLs, with a timeout, and saves the result to `lang_paths.json_path(lang)`.
4. **`fetch_drive_audios`**: under root folder `1ObyoMA9...`, find the subfolder whose name exactly matches the language, ignoring case (`search_folder(..., exact=True)`). Inside it, find the `Feed the Monster` subfolder, which is still matched by substring. Recursively download every `.mp3/.wav/.ogg/.m4a`. Drive file names are untrusted: `download_convert_to_mp3` uses only the sanitized base name and skips any name that would land outside `audios/`. Don't go back to substring matching for the language: `English` used to pick up `EnglishWestAfrican`.
   - **"Step 3b"** (as the code numbers it) runs only if the JSON contains Drive share links in place of audio URLs (e.g. `FeedbackAudios: ".../file/d/<id>/view?usp=sharing"`). `download_json_drive_links` in `fetch_drive_audios.py` downloads each linked file as `<Drive file name>.mp3`. It overwrites any same-named file from step 4 and adds a `_<id[:6]>` suffix when two links have the same name. It then **rewrites the link in `ftm_<lang>.json`** to `<audio URL prefix used elsewhere in the JSON><name>.mp3`, so steps 5 and 6 match it by basename.
5. **`clean_unused_audios`**: `find_used_audios` builds the set of basenames from `Levels[].Puzzles[].prompt.PromptAudio`, `FeedbackAudios[]` and `OtherAudios{}` in the JSON. Any other audio file is deleted (`🗑 Deleted:`), except `great.mp3` and `amazing.mp3`. The exception is a file that matches a required-but-missing name under `normalize_audio_name` (NFC, casefold, Devanagari `ा+े`→`ो` and `ा+ै`→`ौ`). That file is **kept as is, never renamed**, and reported as `🔍 Look-alike: <drive file> ≈ <json name>` for the team to check. The JSON name is then reported missing. Constitution III says never auto-correct names on the basis of similarity (user decision, 2026-10-06).
6. **`check_missing_audios`**: the reverse check, using the same `find_used_audios`. It only prints the results and never fails the run.

The Streamlit UI (`app.py`) parses the `🗑 Deleted:`, `🔍 Look-alike:`, `❌ Missing audio files:` and `✔ Audio cleanup completed` lines into its "Audio check" summary. Keep those prefixes stable.

**Look-alike spellings:** after a run, `lookalike_spellings(lang)` scans the JSON's prompt texts, letters and feedback for `SPELLING_VARIANTS` (`ा+े` instead of `ो`, `ा+ै` instead of `ौ`). The audio summary shows one "Please check: look-alike spellings. Nothing was renamed or changed." warning. It lists the `🔍 Look-alike` file pairs and every look-alike sheet text with its standard form and levels, and the missing-audio list marks names that have a look-alike on Drive. Warn only: never change data on similarity. Example: Marathi's sheet has काे / खाे / ज्ञाे / ङाे / क्षाे typed as `ा+े`.

### Gotchas

- **Always build language paths with `lang_paths`.** Every path is `lang/<lang.lower()>/` and `ftm_<lang.lower()>.json`. The casing used to be mixed, which only worked on Windows. Don't reintroduce `os.path.join("lang", lang)`.
- Audio references come from URL basenames. Drive share links are handled only because step 3b rewrites them first.
- Drive folder IDs and the shared-drive ID are hardcoded throughout.

## Secrets: read before committing

`.gitignore` excludes these. Keep it that way.
- `credentials.json`, an OAuth *desktop* client.
- `token.json`, which holds a refresh token with full Drive scope.
- `.env` anywhere (AI API keys, in `language_automation/.env`), except `.env.example`; and `language_automation/.ai_cache/`.
- `.venv/`, the generated `lang/` data and `.claude/settings.local.json`.

Never hardcode credentials. Use environment variables or local untracked files.
