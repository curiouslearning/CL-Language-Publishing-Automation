# Implementation Plan: React Frontend Without an Always-Open Connection

**Branch**: `012-react-frontend` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/012-react-frontend/spec.md`

## Summary

Replace the Streamlit page (`app.py`) with a React + TypeScript single-page app built by Vite, and a small FastAPI server (`server.py`) that serves the built page and a JSON/NDJSON API. A run is one HTTP request that streams the pipeline's stdout (and the AI check's) as NDJSON events for as long as the run lasts; nothing else holds a connection, so Cloud Run can scale to zero between runs. The page parses the pipeline's log contract in TypeScript exactly as `app.py` did, keeps runs and the Google token in tab memory, signs in with a Google Identity Services popup, and fetches each run's zip into the tab right after the run. Streamlit, `web_signin.py` and `idle_pause.py` (spec 011) are removed. See [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.13 (image; 3.10+ locally) for the server and pipeline; TypeScript 5.9 for the page.

**Primary Dependencies**: Server: `fastapi` 0.162, `uvicorn` 0.54 (replace `streamlit`). Page (build time only, not in the runtime image): `react`/`react-dom` 19.3, `vite` 8.3, `@vitejs/plugin-react` 6.2, `typescript` 5.9. Google Identity Services script loaded at run time from `accounts.google.com`.

**Storage**: None new. `lang/<language>/` on disk as before (in-memory filesystem on Cloud Run); runs, packages and the token in browser tab memory.

**Testing**: No automated suite (constitution). `python -m compileall`, `npm run build` (type check + build), a server smoke test with FastAPI's test client, and manual verification with Hausa (tasks.md).

**Target Platform**: Cloud Run (Linux container, one instance at most) and developers' machines (Windows/Linux).

**Project Type**: Web application (static page + Python API) wrapping the existing scripts.

**Performance Goals**: Log lines appear in the page within 0.5 s of being printed; the page loads in under 2 s.

**Constraints**: No open connection while idle (SC-001); runs up to 60 min (`--timeout=3600`); one run at a time; zip up to a few hundred MB held in a tab.

**Scale/Scope**: A handful of content team members; one page; ~2,000 lines of new code.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Verify before touching disk | ✅ | Pipeline unchanged. The server verifies the Google token before claiming the language or starting the pipeline. |
| II. Exact matching | ✅ | Unchanged. |
| III. JSON is the source of truth | ✅ | Unchanged. |
| IV. Stable log contract | ✅ (amend wording) | The consumer of the prefixes moves from `app.py` to `web/src/runParser.ts`; same prefixes, same results. Constitution text names `app.py`/Streamlit, so it gets a MINOR amendment (2.0.0 → 2.1.0) in this change. |
| V. No secrets in the repo | ✅ | The page only receives the OAuth *client id* (public by design). The token stays in tab memory; `client_secret_web.json` stays gitignored and in Secret Manager. |
| Stack: new dependencies justified | ✅ | See Complexity Tracking. |
| `CLAUDE.md` updated with the change | ✅ | Task in tasks.md. |
| Manual verification with a real language | ✅ | Task in tasks.md. |

Post-design re-check (after research, data model, contracts): still passes; no new violations.

## Project Structure

### Documentation (this feature)

```text
specs/012-react-frontend/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── http-api.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
language_automation/
├── server.py              # NEW FastAPI app: /api/*, static page, run streaming, package download
├── run_store.py           # NEW one-run lock + package registry (replaces package_store.py)
├── google_auth.py         # CHANGED: accepts an access-token-only sign-in from the page
├── app.py                 # REMOVED (Streamlit page)
├── web_signin.py          # REMOVED (redirect sign-in + pending store)
├── idle_pause.py          # REMOVED (spec 011)
├── package_store.py       # REMOVED (replaced by run_store.py)
├── generate_language.py, ai_language_check.py, … (unchanged)
└── web/                   # NEW React + Vite page
    ├── package.json, package-lock.json, tsconfig.json, vite.config.ts, index.html
    └── src/
        ├── main.tsx, App.tsx, styles.css
        ├── api.ts           # fetch wrappers + NDJSON reader
        ├── googleSignin.ts  # GIS token client
        ├── runParser.ts     # log contract → run state (port of app.py handle())
        ├── types.ts
        └── components/      # RunBox, RunSummary, AiSection, RegenerateDialog, Alert, Toggle, Expander
Dockerfile                 # CHANGED: node stage builds web/, python stage serves it with uvicorn
cloudbuild.yaml            # CHANGED: no --session-affinity, no FTM_PUBLIC_URL
requirements.txt           # CHANGED: fastapi + uvicorn instead of streamlit
.dockerignore, .gitignore  # CHANGED: web/node_modules, web/dist
.circleci/config.yml       # CHANGED: test job also type-checks and builds the page
```

**Structure Decision**: Keep everything under `language_automation/` (constitution: all capability lives there). The page's source is `language_automation/web/`, built to `language_automation/web/dist/` which `server.py` serves.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| New Python deps `fastapi`, `uvicorn` (replacing `streamlit`) | An HTTP server that can stream a run as one request and serve static files | Python's `http.server`: no streaming responses with disconnect detection, no production-grade server. Flask: needs gunicorn and threads for streaming; FastAPI/uvicorn do both in one small dependency set. |
| A Node/npm build step (page only; not in the runtime image) | The user chose React; TypeScript + JSX need a build | Plain JS without a build: no React components/types, harder to maintain; the user does TypeScript. |
