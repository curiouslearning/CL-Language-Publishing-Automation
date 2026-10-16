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
- `005-web-google-signin`: per-person web Google sign-in for the page (curiouslearning.org only). Hosting is out of scope; the user handles it separately.
- `006-ai-token-usage`: real input/output tokens and the answering model for every AI check, and the "Show tokens used" toggle.
- `007-gemini-key-cloud-run`: Gemini is the hosted AI provider. The project's restricted key lives in Secret Manager (`ftm-gemini-api-key`) and reaches Cloud Run as `GEMINI_API_KEY`.
- `008-language-package-download`: the generated package as a zip on the page. On the hosted page it's deleted once its page session ends.
- `009-auto-deploy-on-merge`: deploy on merge with Google Cloud Build triggers. **Superseded by 010**; the `ftm-deployer` identity and the newest-wins guard are kept.
- `010-circleci-cicd`: CI/CD on CircleCI, like our other projects: a build check on PRs, and deploy on merge to `main`.

## Hosting (Cloud Run; AI key: spec 007; CI/CD: spec 010)

`Dockerfile` + `cloudbuild.yaml` at the repo root follow spec 005 research R8: Cloud Run in `ftm-language-generator`, region `us-central1`, one instance (the lock and pending store are in-process), `--session-affinity`, `--timeout=3600`, `--allow-unauthenticated` (the page does its own sign-in). The deploy sets `FTM_HOSTED=1`, `FTM_PUBLIC_URL` (`https://<service>-<project number>.<region>.run.app/`, which must also be a redirect URI on the web OAuth client) and `FTM_OAUTH_CLIENT_FILE=/secrets/client_secret_web.json`. They're not in the image, so it can still run locally. Secrets come from Secret Manager, readable only by the runtime account `ftm-generator-run`:
- `ftm-oauth-web-client`, mounted as a file;
- `ftm-gemini-api-key`, set as the env var `GEMINI_API_KEY` (spec 007). It's an API key in the project, restricted to the Gemini API. `:latest` is resolved at instance start, so rotating it means a new secret version plus a redeploy.

If a secret is missing or not readable, the deploy fails and the old revision keeps serving. `.dockerignore` is an allow-list and `.gcloudignore` includes `.gitignore`: keep secrets out of both. One-time setup and deploy: README "Deploy to Cloud Run".

**CI/CD (CircleCI, spec 010):** `.circleci/config.yml`.
- **`build-check`** runs on every branch except `main`: `docker build`, nothing pushed.
- **`deploy`** runs only on `main`, with context `ftm-language-generator-gcp`. CircleCI only issues `CIRCLE_OIDC_TOKEN` to jobs that use a context.
  - It halts (`circleci-agent step halt`) when `git diff HEAD^1 HEAD` touches only `*.md`, `specs/`, `.specify/`, `.claude/` or `.github/`.
  - It signs in to Google Cloud with that OIDC token through workload identity pool `circleci` / provider `circleci-oidc`, which only accepts this CircleCI project id. It acts as `ftm-deployer`; no key is stored anywhere.
  - It then runs `gcloud builds submit --config cloudbuild.yaml --region=us-central1 --substitutions=_COMMIT_SHA=<short sha>`.
- **`cloudbuild.yaml`** builds and pushes to Artifact Registry repo `ftm`, then deploys as `ftm-deployer`.
  - **Newest wins:** the deploy step skips itself if the service's `ftm-build-time` label (createTime of the build that deployed it) is newer than its own build.
  - It sets the labels `ftm-build-time` and `commit-sha`.
- **`ftm-deployer`** has: `run.admin`, `cloudbuild.builds.editor`, `logging.logWriter` and `serviceusage.serviceUsageConsumer` on the project; `iam.serviceAccountUser` on `ftm-generator-run` and on itself; `artifactregistry.writer` on repo `ftm`; `storage.admin` on bucket `ftm-language-generator_cloudbuild` only. No Secret Manager access.
- A deploy replaces the running server, so merge code when nobody is generating.

**Generated packages on Cloud Run (spec 008):** `lang/` lives in the container's in-memory filesystem and counts against the 2 GiB. The page's zip download is the only way out. When `FTM_HOSTED=1`, `package_store.start_janitor` (started once via `app.package_janitor`, a `st.cache_resource`) checks every 15 s:
- it deletes a language folder once its owning page session has been disconnected for 60 s (`is_active_session`; a reconnect resets the wait), downloaded or not;
- it also deletes folders a run in this process claimed but nobody owns any more;
- it never deletes during an active run, and never deletes a folder that existed before the process started (`_claimed`);
- each removal prints `🧹 Cleaned up lang/<lang> (session ended | no owner)` to the server log only.

Locally nothing is ever deleted.

Local testing uses the developer's personal Gemini API key (Google AI Studio) in `.env`, not a key from the `ftm-language-generator` project. The project's restricted key is used only by Cloud Run.

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

There is no separate login page. Sign-in happens when Generate is pressed (web page) or when a script starts (command line). Every Google client in the scripts comes from `google_auth.load_credentials()`, which resolves in this order:
1. **`FTM_GOOGLE_CREDENTIALS`** (JSON, set by `app.py` for the pipeline subprocess only): the web page's sign-in for this run. Used as granted, refreshed in memory, never written to disk. Invalid → `AuthError`.
2. **`FTM_HOSTED=1`** without it → refused ("no Google sign-in was provided for this run"). A server never falls back to `token.json`. This feature only defines the switch; the separate hosting work sets it.
3. **Command line:** `token.json`, refreshed if expired, else the desktop flow with `credentials.json` (`CLI_SCOPES` = drive + spreadsheets.readonly, exactly what `token.json` was always granted; asking for more on refresh fails with `invalid_scope`). Delete `token.json` to re-auth.

- **Web page (`web_signin.py`):** a **Web application** OAuth client in the dedicated Google Cloud project `ftm-language-generator` (Internal audience), read from `language_automation/client_secret_web.json` (gitignored; override with `FTM_OAUTH_CLIENT_FILE`). Redirect URI `FTM_PUBLIC_URL`, default `http://localhost:8501/`. Missing or invalid config → the page shows a setup error and disables Generate (fails closed).
  - Generate in a page session that isn't signed in → **Sign in with Google** button (new tab), PKCE, `prompt="select_account consent"`, `access_type=offline`.
  - Google returns to the app with `?state&code`; `app.py` runs **callback mode** in that tab only (`render_signin_callback`, then `st.stop()`). `handle_callback` checks the request is known, pending, under 3 min old, from the same browser (`ftm_signin` cookie vs nonce), and that the generator tab is still open; exchanges the code; verifies the ID token.
  - **Admission:** `email_verified is True` **and** `hd == "curiouslearning.org"` **and** the email ends with `@curiouslearning.org`. Anything else is refused.
  - The outcome sits in a process-wide pending store (`st.cache_resource`) until the generator tab pops it, once. The sign-in then lives only in that tab's `st.session_state.google_signin` (gone on reload, tab close or restart); later runs in the same tab don't ask again. Only the email is stored in a run (`result["account"]`).
  - The pending store and the one-run lock are in-process: the generator must run as a single process.
- **Domain re-check:** `generate_language.authenticate()` still runs first and prints `🔐 Authenticating with Google...`. It asks Drive which account signed in (`about.user.emailAddress`). Anything that isn't `@curiouslearning.org` is refused and exits 1 before Step 1 (it deletes `token.json` only on the command line). On success it prints `✅ Authenticated as <email>`.

### Web UI (`app.py`)

- **On Generate:** the run's box shows only "Authentication in progress" plus a **Sign in with Google** button (first run in a page session only). The pipeline subprocess starts only after the web sign-in succeeded; the steps and the log appear only after its `✅ Authenticated as` line.
- **On failure:** if sign-in is refused or fails, the box says "❌ Authentication failed: <reason>. Nothing was created or deleted.", with no steps, and the pipeline never starts. An unfinished sign-in (3 min) or a closed tab gives "⏹️ Authentication cancelled". Remaining queued languages aren't started.
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
- **Show tokens used toggle** (spec 006): shown indented under the AI check toggle only while that's on; off by default, disabled while busy. Its value lives in `st.session_state.show_tokens` (the widget key is `show_tokens_toggle`, because Streamlit drops a hidden widget's state), so it survives the AI toggle going off and on. When on, `render_ai_section` calls `render_ai_usage` (model + input/output/total tokens) for every run on the page. Display only: counts are always recorded.
- **Package download** (spec 008): `render_summary` calls `render_package` right before "Download log".
  - **Ownership:** `package_store.py` keeps an in-process registry: language → owning session, `run_id`, active.
    - `run_pipeline` claims the language right before starting the pipeline subprocess (`result["package_id"]`).
    - It calls `finish` in a `finally` after the AI step. `touched=False` (stopped before the wipe step) hands the folder back to its earlier owner.
  - **Availability** (`package_store.availability`):
    - `available` → **📦 Download language package (.zip)**, `on_click="ignore"`. The data is a callable, so `build_zip` (ZIP_STORED, `<lang>/ftm_<lang>.json`, `audios/`, `images/`) only runs on click, on a Streamlit worker thread. That means no rerun, and it works mid-batch. It's followed by a caption: hosted "Kept on the server only until you close or reload this page…", local "Also saved in `lang/<lang>/`…".
    - `regenerating` / `replaced` / `gone` → a 📦 caption saying why.
    - Failed, cancelled or unauthenticated runs → nothing.
  - **Hosted "already generated" dialog:** `existing_audio_count` only counts this session's own packages (`owned_by`).
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
  - **`.env`** is gitignored, with `.env.example` as the template. It holds `GEMINI_API_KEY=` and `ANTHROPIC_API_KEY=`, plus optional `ANTHROPIC_WORKSPACE_ID=` (only for a Claude key that isn't scoped to a workspace; sent as the `anthropic-workspace-id` header), read by `read_env_file` (no python-dotenv). Real environment variables win over `.env`, which is how Cloud Run's secret is picked up. Keys are whitespace-stripped. With `FTM_HOSTED=1` (`is_hosted()`), the "not configured" reason names the missing Cloud Run secret instead of `.env`, and `app.py` drops its `.env.example` hint. An `api_key` in `config.json` is ignored.
  - It never switches to the other provider silently.
- **Token usage:** each reviewer turns the API's usage into the same dict (`claude_usage` / `gemini_usage`): `input_tokens`, `output_tokens` (thinking included, since it's billed as output), `thinking_tokens` (Gemini only), cache read/write counts. It's saved in the cache entry (`usage`) and in the report (`result["usage"]`, with `result["model"]` = the model that actually answered). A progress line `🤖 AI check: <model>, tokens: input N, output N, total N` goes to the AI log, and `render_ai_usage` shows model + input/output tokens under the AI section heading when the "Show tokens used" toggle is on. A cached run used 0 tokens and shows the earlier request's counts. An answer that was billed but unusable (cut off, refused, unreadable) still reports its usage.
- **Output contract:** `🤖 AI check:` and `⚠ AI check:` progress lines, then a last line `🤖 AI report: <json>`. Never use `❌` for findings, or `app.py` would count them as pipeline errors.

## Pipeline architecture (`generate_language.py`)

0. **`verify_language_on_drive`**: before anything on disk is touched, require both the language sheet (`find_language_sheet`) and the audio folder (`find_language_audio_folder`) to exist on Drive. If either is missing, exit 1 without creating or wiping any folder. Keep this ordering.
Before step 0, `lang_paths.validate_language_name` rejects anything except letters, digits, spaces, `-` and `_`. Then `authenticate()` runs (see Google sign-in above), and its Drive service is passed to step 0.

1. **Wipe** `lang/<language>/` with `shutil.rmtree`. Every run starts from scratch, but mp3s that already exist are skipped during download within a single run.
2. Create `audios/` and `images/`. `images/` isn't populated yet.
3. **`fetch_lang_sheet`**: in the Drive folder `18SRLdZK-...`, find the spreadsheet whose name **exactly** matches the language, ignoring case and any `.xlsx`/`.xls` extension (`is_exact_name`). Drive's `name contains` query only narrows the list. If it's an Excel file, first copy it to a Google Sheet (a `_converted` copy stays in Drive). Read the **hyperlink in cell `metadata!D1`** (`run_unity_check.py`). That's the Unity/Cloud Function URL that generates the game JSON. `fetch_unity_json` accepts only `https://` URLs, with a timeout, and saves the result to `lang_paths.json_path(lang)`.
4. **`fetch_drive_audios`**: under root folder `1ObyoMA9...`, find the subfolder whose name exactly matches the language, ignoring case (`search_folder(..., exact=True)`). Inside it, find the `Feed the Monster` subfolder, which is still matched by substring. Recursively download every `.mp3/.wav/.ogg/.m4a`. Drive file names are untrusted: `download_convert_to_mp3` uses only the sanitized base name and skips any name that would land outside `audios/`. Don't go back to substring matching for the language: `English` used to pick up `EnglishWestAfrican`.
   - **"Step 3b"** (as the code numbers it) runs only if the JSON contains Drive share links in place of audio URLs (e.g. `FeedbackAudios: ".../file/d/<id>/view?usp=sharing"`). `download_json_drive_links` in `fetch_drive_audios.py` downloads each linked file as `<Drive file name>.mp3`. It overwrites any same-named file from step 4 and adds a `_<id[:6]>` suffix when two links have the same name. It then **rewrites the link in `ftm_<lang>.json`** to `<audio URL prefix used elsewhere in the JSON><name>.mp3`, so steps 5 and 6 match it by basename.
5. **`clean_unused_audios`**: `find_used_audios` builds the set of basenames from `Levels[].Puzzles[].prompt.PromptAudio`, `FeedbackAudios[]` and `OtherAudios{}` in the JSON. Any other audio file is deleted (`🗑 Deleted:`), except `great.mp3` and `amazing.mp3`. The exception is a file that matches a required-but-missing name under `normalize_audio_name` (NFC, casefold, standard vowel signs). That file is **kept as is, never renamed**, and reported as `🔍 Look-alike: <drive file> ≈ <json name>` for the team to check. The JSON name is then reported missing. Since vowel signs are already standardized (below), in practice this now only catches upper/lowercase differences.
6. **`check_missing_audios`**: the reverse check, using the same `find_used_audios`. It only prints the results and never fails the run.

The Streamlit UI (`app.py`) parses the `🗑 Deleted:`, `🔍 Look-alike:`, `🔤 Standard spelling:`, `❌ Missing audio files:` and `✔ Audio cleanup completed` lines into its "Audio check" summary. Keep those prefixes stable.

**Look-alike vowel signs (auto-fixed, user decision 2026-10-14, overrides the 2026-10-06 warn-only rule for this case):** `spelling.py` holds `SPELLING_VARIANTS` (`ा+े`→`ो`, `ा+ै`→`ौ`) and `standard_spelling`. `download_convert_to_mp3` and `download_json_drive_links` save audio files under the standard spelling, and "Step 3c" in `generate_language.py` runs `standardize_json_file` on `ftm_<lang>.json` before the audio checks, printing `🔤 Standard spelling: <as typed> → <standard> (<n> places)`. `app.py` shows those as one caption line, no warning. Example: Marathi's sheet has काे / खाे / ज्ञाे / ङाे / क्षाे typed as `ा+े`; they now become को / खो / ज्ञो / ङो / क्षो and match Drive's को.mp3 / खो.mp3. Other look-alikes (upper/lowercase) are still warn-only.

### Gotchas

- **Always build language paths with `lang_paths`.** Every path is `lang/<lang.lower()>/` and `ftm_<lang.lower()>.json`. The casing used to be mixed, which only worked on Windows. Don't reintroduce `os.path.join("lang", lang)`.
- Audio references come from URL basenames. Drive share links are handled only because step 3b rewrites them first.
- Drive folder IDs and the shared-drive ID are hardcoded throughout.

## Secrets: read before committing

`.gitignore` excludes these. Keep it that way.
- `credentials.json`, an OAuth *desktop* client (command line).
- `client_secret*.json`, including `language_automation/client_secret_web.json`, the *web* OAuth client for the page.
- `token.json`, which holds a refresh token with full Drive scope.
- `.env` anywhere (AI API keys, in `language_automation/.env`), except `.env.example`; and `language_automation/.ai_cache/`. The same files must stay excluded in `.dockerignore`.
- `.venv/`, the generated `lang/` data and `.claude/settings.local.json`.

Never hardcode credentials. Use environment variables or local untracked files.
