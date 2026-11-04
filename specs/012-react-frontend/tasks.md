# Tasks: React Frontend Without an Always-Open Connection

**Input**: Design documents from `specs/012-react-frontend/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md

**Tests**: no automated suite (constitution). Verification: `compileall`, `npm run build` (type check), a throwaway server smoke script (not committed), and the manual checks in Phase 7.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files)
- **[Story]**: US1 generate without idle cost, US2 same page flow, US3 package in the tab, US4 cancelling

---

## Phase 1: Setup

- [X] T001 Create `language_automation/web/` (Vite + React + TypeScript): `package.json` (react 19.3, react-dom 19.3, vite 8.3, @vitejs/plugin-react 6.2, typescript 5.9, @types/react, @types/react-dom), `tsconfig.json`, `vite.config.ts` (dev proxy `/api` → `http://localhost:8080`), `index.html` (title "FTM Language Generator", 🌍 favicon, Source Sans 3), `npm install` to produce `package-lock.json`.
- [X] T002 [P] Replace `streamlit` with `fastapi` 0.162.0 and `uvicorn` 0.54.0 in `requirements.txt`; add `web/node_modules/`, `web/dist/` to `.gitignore` and keep them out of `.dockerignore`.

## Phase 2: Foundational (blocks all stories)

- [X] T003 `language_automation/google_auth.py`: `FTM_GOOGLE_CREDENTIALS` with only `{"token": …}` builds `Credentials(token=…)` (no refresh); full authorized-user JSON still works. Update docstring and `WEB_SCOPES`.
- [X] T004 `language_automation/run_store.py`: one-run lock; package registry `claim(lang) → package_id`, `finish(lang, package_id, touched, ok)`, `availability(package_id)`, `build_zip(package_id)` (ZIP_STORED, same layout as spec 008), hosted delete after fetch, `start_janitor()` (hosted: delete unfetched packages 10 min after the run, only folders claimed by this process, never during a run). Remove `package_store.py`.
- [X] T005 `language_automation/server.py`: FastAPI app per contracts/http-api.md: `/api/config` (client id from `FTM_OAUTH_CLIENT_FILE`/`client_secret_web.json`, fail closed with the same setup messages as `web_signin.load_client_config`), `/api/existing`, `/api/runs` (token check R4 → `auth` event, claim, pipeline subprocess with `FTM_GOOGLE_CREDENTIALS`, NDJSON `line`/`pipeline_end`/`ai_*`/`ping`/`end`, kill + unlock on disconnect), `/api/packages/{id}`, static `web/dist` with SPA fallback; `python server.py` runs uvicorn on `$PORT` (default 8080).
- [X] T006 [P] `web/src/types.ts`, `web/src/api.ts` (config, existing, startRun with NDJSON reader and AbortController, fetchPackage).
- [X] T007 [P] `web/src/googleSignin.ts`: load GIS script once, `requestToken(clientId, hint?)` → `{token, email?, expiresAt}`; errors `popup_closed`, `popup_failed_to_open`, timeout 3 min.
- [X] T008 `web/src/runParser.ts`: port `app.py`'s `STEPS`, markers, `AUDIO_FILE_DONE`/`AUDIO_TOTAL` regexes and `handle()` / final-state logic; `stepsLines(run)` for the step list.

## Phase 3: US1 – Generate without idle cost (P1) 🎯 MVP

- [X] T009 [US1] `web/src/styles.css`: Streamlit look (research R6).
- [X] T010 [US1] `web/src/components/*`: `Alert`, `StatusBox`, `Expander`, `Toggle`, `CodeLog` (320 px, auto-scroll), `RunSteps`, `RunSummary` (audio check section, mp3 count, package, Download log).
- [X] T011 [US1] `web/src/App.tsx`: title, caption, setup error, form, queue processing: sign-in box with **Sign in with Google** button, run stream → parser → state, final states and labels exactly as `app.py`.

## Phase 4: US2 – Same page flow (P1)

- [X] T012 [US2] Validation messages, comma-separated queue, disabled controls while busy, other-run warning (from `/api/config` `busy` and 409) with "Check again".
- [X] T013 [US2] `RegenerateDialog` (Yes / No / close = No, "Not regenerated: …").
- [X] T014 [US2] AI check toggle + caption ("Uses gemini (model)." / "Not configured: …"), indented Show tokens toggle (kept when AI is toggled off and on), `AiSection` (provider heading, usage, cached caption, unavailable/cannot_judge/no issues/n issues, warnings with badges, consistency), AI log expander + Download AI log.
- [X] T015 [US2] Latest run / Previous runs, success banner + **➕ Add another language** (top and bottom), scroll to top and focus the input.

## Phase 5: US3 – Package in the tab (P2)

- [X] T016 [US3] After `end` with `package_id`, fetch the zip into the run ("Preparing the package…"), download button + hosted/local caption; mark earlier runs of the same language `replaced` and drop their blob.

## Phase 6: US4 – Cancelling (P2)

- [X] T017 [US4] Abort the run's fetch on `pagehide`; popup closed / blocked / 3-min timeout → "⏹️ Authentication cancelled: …", stop the queue; refused → forget the token, "❌ Authentication failed: …".

## Phase 7: Hosting, docs, verification

- [X] T018 Remove `app.py`, `web_signin.py`, `idle_pause.py`; mark spec 011 superseded by 012.
- [X] T019 [P] `Dockerfile` (node build stage → python runtime, `CMD python server.py`), `cloudbuild.yaml` (drop `--session-affinity` and `FTM_PUBLIC_URL`), `.dockerignore`, `.circleci/config.yml` (test job: `npm ci && npm run build` in `web/`).
- [X] T020 [P] Constitution amendment 2.0.0 → 2.1.0 (stack and principle IV name the React page / `runParser.ts`).
- [X] T021 [P] `CLAUDE.md` and `README.md`: new page, server, local run, OAuth JavaScript origins, hosting flags, spec 012 entry.
- [X] T022 Verify: `python -m compileall language_automation`; `npm run build`; server smoke script (config, existing, 400/409/401 paths, a fake pipeline stream and disconnect → kill, zip download) — scratch only.
- [ ] T023 Manual (user): generate Hausa locally and on Cloud Run per quickstart.md; confirm the summary matches a Streamlit run, the zip opens, closing the tab cancels, and an idle tab holds no request.

## Dependencies

T001–T002 → T003–T008 → US1 (T009–T011) → US2/US3/US4 (any order) → Phase 7. T022 needs everything above; T023 is done by the user after deploy.
