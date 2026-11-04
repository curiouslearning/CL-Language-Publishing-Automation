# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Tooling for publishing new languages for Curious Learning's **Feed the Monster (FTM)** game. There's no build system, no tests and no linter. Dependencies are pinned in `requirements.txt`. All the code is in `language_automation/`: standalone Python scripts that pull one language's content JSON and audio files from Google Drive into `lang/<language>/`, and a web page for the content team (spec 012): a React + TypeScript page in `language_automation/web/` (built with Vite) served with its API by `server.py` (FastAPI).

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
- `011-idle-pause`: **superseded by 012** (the page no longer holds a connection while idle). Was: an idle hosted page pauses after 15 minutes (`FTM_IDLE_PAUSE_MINUTES`) so its websocket closes and Cloud Run can stop billing. Never during a run in that tab.
- `012-react-frontend`: the React page + FastAPI server replacing Streamlit, so an open tab holds no connection and Cloud Run scales to zero between runs. Google sign-in is a popup (token kept in tab memory, checked on the server per run); the package zip is fetched into the tab right after the run.

## Hosting (Cloud Run; AI key: spec 007; CI/CD: spec 010; page: spec 012)

`Dockerfile` + `cloudbuild.yaml` at the repo root: Cloud Run in `ftm-language-generator`, region `us-central1`, `--min-instances=0 --max-instances=1` (the one-run lock and the package registry are in-process), `--timeout=3600` (a run is one request), `--no-session-affinity`, `--allow-unauthenticated` (the page does its own sign-in). The Dockerfile has two stages: `node:22-slim` runs `npm ci && npm run build` in `language_automation/web` (type check + Vite), then `python:3.13-slim` + ffmpeg gets the scripts and `web/dist` only (no Node at run time) and runs `python server.py` (`HOST=0.0.0.0`, `PORT` from Cloud Run). The deploy sets `FTM_HOSTED=1` and `FTM_OAUTH_CLIENT_FILE=/secrets/client_secret_web.json`; they're not in the image, so it can still run locally. Secrets come from Secret Manager, readable only by the runtime account `ftm-generator-run`:
- `ftm-oauth-web-client`, mounted as a file (only `web.client_id` is read now);
- `ftm-gemini-api-key`, set as the env var `GEMINI_API_KEY` (spec 007). It's an API key in the project, restricted to the Gemini API. `:latest` is resolved at instance start, so rotating it means a new secret version plus a redeploy.

If a secret is missing or not readable, the deploy fails and the old revision keeps serving. `.dockerignore` is an allow-list and `.gcloudignore` includes `.gitignore`: keep secrets out of both (and `web/node_modules`, `web/dist`). One-time setup and deploy: README "Deploy to Cloud Run".

**Why the page costs nothing while idle (spec 012):** Cloud Run (request-based billing) bills while any request is open. The old Streamlit page kept a websocket per open tab (spec 011 paused idle tabs as a workaround). The React page holds no connection: it makes short requests (load, `/api/config`, `/api/existing`), one streaming request per run that lasts exactly as long as the run, and one request per package. Between runs the service scales to zero. `idle_pause.py` and spec 011 are gone.

**CI/CD (CircleCI, spec 010):** `.circleci/config.yml`.
- **Layout:** the same as FeedTheMonsterJS: reusable `commands:` (`gcloud-login`, `build-and-deploy`, no parameters: one environment), the job `test` on every branch, and `build-and-deploy-prod` on `main` with `requires: [test]`. Workflow `cloud-run-deploy-workflow`.
- **`test`** (`cimg/python:3.13.2`): `python -m compileall language_automation`, `docker build` (which also type-checks and builds the page). Nothing pushed.
- **`build-and-deploy-prod`** (`google/cloud-sdk:slim`) runs only on `main`, with context `ftm-language-generator-gcp`. CircleCI only issues `CIRCLE_OIDC_TOKEN` to jobs that use a context.
  - It halts (`circleci-agent step halt`) when `git diff HEAD^1 HEAD` touches only `*.md`, `specs/`, `.specify/`, `.claude/` or `.github/`.
  - It signs in to Google Cloud with that OIDC token through workload identity pool `circleci` / provider `circleci-oidc`, which only accepts this CircleCI project id. It acts as `ftm-deployer`; no key is stored anywhere.
  - It then runs `gcloud builds submit --async` (with `--gcs-source-staging-dir=gs://ftm-language-generator_cloudbuild/source`; the default bucket needs a project-wide bucket list that `ftm-deployer` doesn't have), waits for the build, prints its Cloud Build log (`gcloud logging read`, hence `roles/logging.viewer`), and on failure ends with a ❌ line naming the failed Cloud Build step and its reason.
- **`cloudbuild.yaml`** builds and pushes to Artifact Registry repo `ftm`, then deploys as `ftm-deployer`.
  - **Newest wins:** the deploy step skips itself if the service's `ftm-build-time` label (createTime of the build that deployed it) is newer than its own build.
  - It sets the labels `ftm-build-time` and `commit-sha`.
- **`ftm-deployer`** has: `run.admin`, `cloudbuild.builds.editor`, `logging.logWriter`, `logging.viewer` and `serviceusage.serviceUsageConsumer` on the project; `iam.serviceAccountUser` on `ftm-generator-run` and on itself; `artifactregistry.writer` on repo `ftm`; `storage.admin` on bucket `ftm-language-generator_cloudbuild` only. No Secret Manager access.
- A deploy replaces the running server, so merge code when nobody is generating.

**Generated packages (specs 008, 012; `run_store.py`):** `lang/` lives in the container's in-memory filesystem and counts against the service's 1 GiB. Right after a run, the page fetches the zip (`GET /api/packages/<package_id>`) into the tab as a Blob; the download button saves that Blob without another request, until the tab is closed or reloaded. When `FTM_HOSTED=1`:
- the folder is deleted as soon as its zip has been sent (one fetch; later fetches get 410);
- a package nobody fetched is deleted 10 minutes after its run (`run_store.start_janitor`, every 30 s), and so are folders a run in this process claimed but nobody owns any more;
- it never deletes during a run, and never a folder that existed before the process started (`_claimed`);
- each removal prints `🧹 Cleaned up lang/<lang> (downloaded | not downloaded | no owner)` to the server log only.

Locally nothing is ever deleted, and the latest run's package can be fetched again.

Local testing uses the developer's personal Gemini API key (Google AI Studio) in `.env`, not a key from the `ftm-language-generator` project. The project's restricted key is used only by Cloud Run.

## Running the pipeline

Run every script from inside `language_automation/`. `credentials.json` and `token.json` are read relative to the CWD. Language data paths come from `lang_paths.py` and are anchored to that folder.

```bash
cd language_automation
python generate_language.py Hausa           # full pipeline (entry point)

# web page (spec 012): build the page once, then run the server on http://localhost:8080
(cd web && npm ci && npm run build)
python server.py
# page development with live reload: python server.py, and in web/: npm run dev (http://localhost:5173, /api proxied to :8080)

# individual steps, for debugging
python fetch_lang_sheet.py Hausa            # sheet -> Unity URL -> ftm_<lang>.json
python fetch_drive_audios.py Hausa          # download + convert audios
python check_missing_audios.py Hausa        # report audio referenced by JSON but not on disk
python fetch_unity_json.py <URL> <OUT_PATH>
```

What you need installed: `python -m pip install -r requirements.txt`, `ffmpeg` on PATH (non-mp3 audio is converted to 44.1 kHz stereo 192k mp3), and Node.js 20+ to build the page.

### Google sign-in

Sign-in happens when Generate is pressed (web page) or when a script starts (command line). Every Google client in the scripts comes from `google_auth.load_credentials()`, which resolves in this order:
1. **`FTM_GOOGLE_CREDENTIALS`** (JSON, set by `server.py` for the pipeline subprocess only): the web page's sign-in for this run. From the page it's `{"token": "<access token>"}`, used without a refresh token (it lasts about an hour, longer than a run). A full authorized-user JSON still works. Never written to disk. Invalid → `AuthError`.
2. **`FTM_HOSTED=1`** without it → refused ("no Google sign-in was provided for this run"). A server never falls back to `token.json`.
3. **Command line:** `token.json`, refreshed if expired, else the desktop flow with `credentials.json` (`CLI_SCOPES` = drive + spreadsheets.readonly, exactly what `token.json` was always granted; asking for more on refresh fails with `invalid_scope`). Delete `token.json` to re-auth.

- **Web page (spec 012, `web/src/googleSignin.ts`):** Google Identity Services *token model* popup with the **Web application** OAuth client of the Google Cloud project `ftm-language-generator` (Internal audience). The server reads its `client_id` from `language_automation/client_secret_web.json` (gitignored; override with `FTM_OAUTH_CLIENT_FILE`) and gives it to the page in `/api/config`. Missing or invalid → the page shows a setup error and disables Generate (fails closed). The client's **Authorized JavaScript origins** must list every address the page is served from (Cloud Run URL, `http://localhost:8080`, `http://localhost:5173`); redirect URIs aren't used any more.
  - The first Generate in a tab shows **Sign in with Google** in the run's box (the popup needs a click). Scopes `openid email drive spreadsheets.readonly`, `hd` hint `curiouslearning.org`. Not completed within 3 min, popup closed → "⏹️ Authentication cancelled"; popup blocked → "❌ Authentication failed: the browser blocked Google's sign-in popup…".
  - The token lives only in the tab's memory (`signin` ref), never in browser storage; it's reused for later runs until less than 10 minutes are left, then the page asks again. Refused or expired → forgotten.
  - **Server check per run** (`server.verify_token`, before anything is claimed or started): `tokeninfo` (`aud`/`azp` = our client id, `expires_in ≥ 60`, Drive and Sheets scopes granted) and `userinfo` → **admission** `email_verified is True` **and** `hd == "curiouslearning.org"` **and** the email ends with `@curiouslearning.org`. Anything else is refused ("only Curious Learning (curiouslearning.org) accounts can add languages (signed in as …)").
- **Domain re-check:** `generate_language.authenticate()` still runs first and prints `🔐 Authenticating with Google...`. It asks Drive which account signed in (`about.user.emailAddress`). Anything that isn't `@curiouslearning.org` is refused and exits 1 before Step 1 (it deletes `token.json` only on the command line). On success it prints `✅ Authenticated as <email>`.

### Web page (`server.py` + `web/`, spec 012; flow from specs 003, 004, 006, 008)

**Server (`server.py`, FastAPI + uvicorn, one process):** API contract in `specs/012-react-frontend/contracts/http-api.md`.
- `GET /api/config`: hosted flag, sign-in client id or setup error, AI provider/model or why it's not configured, `busy`.
- `POST /api/existing`: local only, mp3 counts of languages already in `lang/` (hosted: `{}`).
- `POST /api/runs` (`Authorization: Bearer <token>`, `{lang, ai_check}`): 400 invalid name, 503 sign-in not set up, 401 no token, 409 another run. Otherwise an NDJSON stream: `auth`, `line` (pipeline stdout), `pipeline_end`, `ai_start`/`ai_line`/`ai_report`, `ping` (every 5 s of silence), `end` (`package_id` when the run produced a package, `mp3_count`). The lock (`run_store.run_lock`) is taken inside the stream and held until it ends. If the connection closes (tab closed or reloaded), `RunResponse` closes the generator and its `finally` kills the pipeline/AI check, finishes the package claim and releases the lock (server log: `server: run <lang> cancelled`).
- The pipeline subprocess gets `FTM_GOOGLE_CREDENTIALS={"token": …}`; the AI check never gets it. The AI check runs only if `ai_check`, the pipeline printed `✅ Authenticated as`, and the game JSON exists.
- `GET /api/packages/<id>`: the zip (ZIP_STORED, `<lang>/ftm_<lang>.json`, `audios/`, `images/`), or 410 with the reason.
- Every other GET serves `web/dist` (`index.html` for unknown paths; `/assets/*` cached forever, `index.html` `no-cache`).

**Page (`web/src`, React 19 + TypeScript + Vite, no UI library):** styled like the Streamlit page (`styles.css`).
- `runParser.ts` is the port of `app.py`'s `handle()`: `STEPS` markers, audio progress regexes, the `🗑 Deleted:`, `🔍 Look-alike:`, `🔤 Standard spelling:`, `❌ Missing audio files:` and `✔ Audio cleanup completed` lines, and the end-of-run states (`complete`, `warning`, `error`, `cancelled`) with the same texts. Runs are kept in React state only.
- **One click per run:** the input, Generate and the toggles are disabled while a run is queued or running in this tab, or another tab/user holds the lock (`busy` from `/api/config` or a 409; "Check again" re-reads it). The form clears on submit. Comma-separated languages run one after another; a failed or cancelled sign-in stops the rest.
- **On Generate:** the run's box shows only "Authentication in progress" (plus **Sign in with Google** when a token is needed); steps, the note and the 320 px auto-scrolling log appear after the `✅ Authenticated as` line. "⚠️ Keep this page open until the run finishes." is shown while it runs.
- **Already generated:** locally `/api/existing`; hosted, a package this tab still holds. The dialog asks "Do you need to regenerate this language?": **Yes** regenerates, **No**/close/Esc runs only the new languages and says "Not regenerated: …".
- **After a batch:** the runs move to **Latest run** (expanded); earlier ones to **Previous runs**. When every run is `complete` or `warning`, a success banner with **➕ Add another language** (top and bottom) moves them to Previous runs, empties and focuses the input and scrolls to the top.
- **AI language check toggle** (off by default) and **🔢 Show tokens used** (indented, only while the AI toggle is on; its value survives the AI toggle going off and on). The AI section, the "🤖 AI check log" expander and **Download AI log** follow the unused-audio result. While the AI check runs, only the run's title says so.
- **Package:** "📦 Preparing the language package…", then **📦 Download language package (.zip)** with the caption "Kept in this page only until you close or reload it. Download it now." (hosted) or "Also saved in `lang/<lang>/` on this computer." (local). A later run of the same language marks earlier ones "replaced" and drops their zip. Failed, cancelled or unauthenticated runs show nothing. **Download log** is last.

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
  - **`.env`** is gitignored, with `.env.example` as the template. It holds `GEMINI_API_KEY=` and `ANTHROPIC_API_KEY=`, plus optional `ANTHROPIC_WORKSPACE_ID=` (only for a Claude key that isn't scoped to a workspace; sent as the `anthropic-workspace-id` header), read by `read_env_file` (no python-dotenv). Real environment variables win over `.env`, which is how Cloud Run's secret is picked up. Keys are whitespace-stripped. With `FTM_HOSTED=1` (`is_hosted()`), the "not configured" reason names the missing Cloud Run secret instead of `.env`, and the page drops its `.env.example` hint. An `api_key` in `config.json` is ignored.
  - It never switches to the other provider silently.
- **Token usage:** each reviewer turns the API's usage into the same dict (`claude_usage` / `gemini_usage`): `input_tokens`, `output_tokens` (thinking included, since it's billed as output), `thinking_tokens` (Gemini only), cache read/write counts. It's saved in the cache entry (`usage`) and in the report (`result["usage"]`, with `result["model"]` = the model that actually answered). A progress line `🤖 AI check: <model>, tokens: input N, output N, total N` goes to the AI log, and `render_ai_usage` shows model + input/output tokens under the AI section heading when the "Show tokens used" toggle is on. A cached run used 0 tokens and shows the earlier request's counts. An answer that was billed but unusable (cut off, refused, unreadable) still reports its usage.
- **Output contract:** `🤖 AI check:` and `⚠ AI check:` progress lines, then a last line `🤖 AI report: <json>`. Never use `❌` for findings, or the page would count them as pipeline errors.

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

The web page (`web/src/runParser.ts`) parses the `🗑 Deleted:`, `🔍 Look-alike:`, `🔤 Standard spelling:`, `❌ Missing audio files:` and `✔ Audio cleanup completed` lines into its "Audio check" summary. Keep those prefixes stable.

**Look-alike vowel signs (auto-fixed, user decision 2026-10-14, overrides the 2026-10-06 warn-only rule for this case):** `spelling.py` holds `SPELLING_VARIANTS` (`ा+े`→`ो`, `ा+ै`→`ौ`) and `standard_spelling`. `download_convert_to_mp3` and `download_json_drive_links` save audio files under the standard spelling, and "Step 3c" in `generate_language.py` runs `standardize_json_file` on `ftm_<lang>.json` before the audio checks, printing `🔤 Standard spelling: <as typed> → <standard> (<n> places)`. The page shows those as one caption line, no warning. Example: Marathi's sheet has काे / खाे / ज्ञाे / ङाे / क्षाे typed as `ा+े`; they now become को / खो / ज्ञो / ङो / क्षो and match Drive's को.mp3 / खो.mp3. Other look-alikes (upper/lowercase) are still warn-only.

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
