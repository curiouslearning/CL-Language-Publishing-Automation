# Research: React Frontend Without an Always-Open Connection

## R1. Why the cost goes away

Cloud Run with request-based billing bills an instance while at least one request is open (plus a short idle period before it scales to zero). Streamlit keeps one websocket per tab, so an open tab = a billed instance (spec 011). With a static page, an open tab holds no request. Requests only exist while the page loads (a few ms), reads `/api/config`, runs a language (as long as the run, which is real work) and fetches a zip.

**Decision**: run = one streaming HTTP request (NDJSON), not polling. Polling would keep the instance warm as long as a tab polls, and the run's work (downloads, ffmpeg) needs CPU, which request-based billing only allocates while a request is open. A streamed request gives CPU for exactly the run's length and tells the server immediately when the tab goes away (FR-008).

## R2. React vs Next.js

**Decision**: React + Vite (TypeScript), built to static files served by the Python server.
**Rationale**: The backend has to be Python (the pipeline). Next.js would add a Node server (second service, its own billing and deploy) or, with `output: "export"`, produce what Vite produces with more tooling. No SEO or server rendering is needed.

## R3. Server framework

**Decision**: FastAPI + uvicorn, single process, single worker (the one-run lock is in-process; Cloud Run `--max-instances=1`).
**Streaming**: `StreamingResponse` over an async generator. The pipeline runs with `subprocess.Popen` + a reader thread + `queue.Queue` (works the same on Windows and Linux; asyncio subprocesses need the Proactor loop on Windows). The generator polls the queue every 0.1 s, sends `{"type":"ping"}` every 10 s without output, and checks `request.is_disconnected()`. When the client goes away Starlette cancels the generator; its `finally` kills the subprocess and releases the lock.

## R4. Google sign-in without a server session

**Decision**: Google Identity Services *token model* (`google.accounts.oauth2.initTokenClient`) with the existing **Web application** OAuth client id, scopes `openid email drive spreadsheets.readonly`, `hd: "curiouslearning.org"` (hint only), `prompt: "select_account"` on first use. Called from a click (popup needs a user gesture), exactly where the "Sign in with Google" button sits today.
**Server check per run** (before claiming anything):
1. `GET https://oauth2.googleapis.com/tokeninfo?access_token=…` → `aud`/`azp` must equal our client id (a token issued to another app is refused), `expires_in > 60`, and the Drive scope must be granted.
2. `GET https://openidconnect.googleapis.com/v1/userinfo` with the token → `admit()` (unchanged rule: `email_verified is True`, `hd == curiouslearning.org`, email ends with `@curiouslearning.org`).
The token is then passed to the pipeline subprocess as `FTM_GOOGLE_CREDENTIALS={"token": "…"}`; `google_auth.load_credentials` builds `Credentials(token=…)` (no refresh token, no client secret needed). The pipeline still checks the domain itself and prints `✅ Authenticated as`.
**Alternatives**: redirect/code flow (needs a pending store that dies when the instance scales to zero); GIS code model in a popup (needs the client secret on the server and a server exchange; no benefit since the access token ends up being used the same way).
**Lifetime**: tokens last ~1 h. The page keeps `expires_at` and asks again when fewer than 10 minutes remain before a run. Runs are minutes long.
**Setup**: the OAuth client needs "Authorized JavaScript origins": the Cloud Run URL, `http://localhost:8080`, `http://localhost:5173`. The redirect URI is no longer used.

## R5. Packages

**Decision**: after the run the server keeps the folder; the stream's final event carries a `package_id` (random 128-bit, unguessable) when the run produced a package. The page immediately `GET /api/packages/{id}` and keeps the zip as a `Blob` in tab memory; the download button saves it with an object URL (no server request).
Hosted: the folder is deleted right after the zip has been sent, or 10 minutes after the run if nobody fetched it (a janitor thread), never during a run. Locally nothing is deleted and the package can be fetched again while it is the latest run of that language.
"Already generated" (hosted) is decided in the page from its own runs that still hold a zip; locally the server counts `lang/<language>/` as before (`/api/existing`).

## R6. Look and feel

Streamlit's look is reproduced with plain CSS (no UI library): Source Sans 3 (Google Fonts), a 736 px centered column, primary button `#ff4b4b`, alert boxes (success `#dff3e4/#177233`, info `#e0edfb/#1c4f8b`, warning `#fffbe6/#926c05`, error `#ffeaea/#7d353b`), status box with spinner/✅/❌ title, expanders with chevrons, toggles, a modal dialog, a 320 px auto-scrolling code block. Same texts and emoji as `app.py`.

## R7. Hosting changes

`--session-affinity` and `FTM_PUBLIC_URL` are no longer needed. `--min-instances=0 --max-instances=1 --timeout=3600` stay. `FTM_OAUTH_CLIENT_FILE` stays: the server reads only `web.client_id` from it for `/api/config` and the token audience check. The Dockerfile gets a `node:22-slim` build stage; the runtime image stays `python:3.13-slim` + ffmpeg, without Node.

## R8. Idle pause

Removed: an idle tab has no connection to close. Spec 011 is marked superseded by 012.
