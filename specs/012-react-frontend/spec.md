# Feature Specification: React Frontend Without an Always-Open Connection

**Feature Branch**: `012-react-frontend`

**Created**: 2026-11-04

**Status**: Implemented (manual verification T023 pending)

**Input**: User description: "I want to change my frontend from Streamlit to any of the frontend technologies, like React or Next, so that I can make sure that the services are not running whenever the browser opens the frontend. Right now, Streamlit is working as a web socket is charging me money. I don't want those expenses. Suggest either Next.js or React.js to me, and apply that UI with the existing one. Make sure the UI looks similar and all the processes and all the things work properly."

## Context

The generator page is a Streamlit app. Every open Streamlit tab keeps a websocket to the server, and Cloud Run (request-based billing) bills for as long as any request is open. Spec 011 worked around this by pausing tabs after 15 idle minutes, but an open tab still bills the server for up to 15 minutes, and a tab that is in use bills the whole time, including while the person is only reading results.

This feature replaces the page with a static web page that only talks to the server when there is work to do: loading the page, starting a run (for the length of that run), and downloading its package. Between those, the page holds no connection, so the server can stop and stop billing.

**Decisions (user, 2026-11-04):**

- Frontend: **React** (single-page app, TypeScript). Next.js was not chosen: it needs its own Node server, which would be a second always-billed service, or a static export, which is a plain React app with extra tooling.
- Generated package: **held in the browser tab**. Right after a run the page fetches the zip into the tab. On the hosted server the copy on disk is deleted once it has been fetched; locally `lang/<language>/` is kept, as now.
- Google sign-in: **a Google sign-in popup in the page** (no new tab, no server-side pending store). It gives the tab a short-lived Google access token. The token is sent with each run, checked again on the server (verified `@curiouslearning.org` only), and never stored on the server or on disk.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate a language with the same page, without paying for open tabs (Priority: P1)

A content team member opens the generator, types a language, presses **Generate**, signs in with Google in a popup, watches the steps, the progress and the log, and gets the same audio check summary as today. While the page is just open (before, between or after runs), it holds no connection to the server.

**Why this priority**: This is the whole point: same workflow, no idle cost.

**Independent Test**: Open the hosted page, leave it open for 20 minutes without a run, and confirm in the Cloud Run request logs that no request is open during that time and the instance count drops to zero. Then generate Hausa and compare the page with the Streamlit page.

**Acceptance Scenarios**:

1. **Given** the page is open and no run is going, **When** 20 minutes pass, **Then** no request from that tab is open on the server, and the server can scale to zero.
2. **Given** the page is open, **When** the user types `Hausa` and presses **Generate** for the first time in this tab, **Then** the run's box shows only "Authentication in progress" with a **Sign in with Google** button, as today.
3. **Given** the user signs in with a verified `@curiouslearning.org` account, **When** the sign-in finishes, **Then** the run starts, and the steps, the "⏳" note with download progress (`n/N files`) and the scrolling log appear only after "✅ Authenticated as <email>".
4. **Given** a later run in the same tab within the token's lifetime, **When** Generate is pressed, **Then** no sign-in is asked again.
5. **Given** a run finishes, **When** the summary is drawn, **Then** it shows the "🎧 Audio check" section (missing audios, upper/lowercase look-alikes, standard spelling caption, unused audios removed), the mp3 count, the package download and **Download log**, worded as today.

---

### User Story 2 - The page behaves like today (Priority: P1)

All of the page flow of spec 004 and the related specs keeps working: one run at a time, input and Generate disabled while busy, several languages separated by commas, the "already generated" dialog, Add another language, Latest run / Previous runs, AI check and Show tokens toggles, package and log downloads.

**Why this priority**: The user asked that "all the processes and all the things work properly".

**Independent Test**: Walk through each acceptance scenario below on a local run and on the hosted page.

**Acceptance Scenarios**:

1. **Given** a run is in progress in any tab or by any user, **When** another tab presses Generate, **Then** it is told "⏳ Another language is being generated right now…" and nothing starts.
2. **Given** a language that already has its JSON and audios (locally: in `lang/<language>/`; hosted: a package fetched in this tab), **When** Generate is pressed, **Then** the "Language already generated" dialog asks "Do you need to regenerate this language?"; **Yes** regenerates, **No** or closing it runs only the languages that don't exist yet and says "Not regenerated: …".
3. **Given** `Hausa, IndianEnglish`, **When** Generate is pressed, **Then** both run one after the other, and if sign-in fails or is cancelled the remaining ones aren't started.
4. **Given** every run in the last batch is complete or finished with warnings, **Then** the success banner with **➕ Add another language** appears above "Latest run" and below the results; clicking it moves the runs to "Previous runs", empties and focuses the language box and scrolls to the top.
5. **Given** the AI check toggle is on, **When** a run produces the game JSON, **Then** the AI check runs after the pipeline, the run's title says "🤖 AI language check in progress…", and the AI section, the "🤖 AI check log" expander and **Download AI log** appear after the unused-audio result. "🔢 Show tokens used" appears indented under it and shows model and tokens for every run on the page.
6. **Given** an invalid name such as `../x`, **When** Generate is pressed, **Then** "Invalid language name: … Use letters, digits, spaces, - or _." is shown and nothing runs.

---

### User Story 3 - Download the package after the run (Priority: P2)

After a run, **📦 Download language package (.zip)** saves the zip immediately, without another request to the server, for as long as the tab stays open.

**Why this priority**: The zip is the only way to get a hosted run's output.

**Independent Test**: Generate a language on the hosted page, wait 30 minutes (the server has scaled to zero), click the package button and open the zip.

**Acceptance Scenarios**:

1. **Given** a successful or warning run, **When** it finishes, **Then** the page fetches the zip into the tab and shows the download button with the caption "Kept in this page only until you close or reload it. Download it now." (hosted) or "Also saved in `lang/<language>/` on this computer." (local).
2. **Given** the hosted server, **When** the zip has been fetched, **Then** the language folder is deleted from the server.
3. **Given** a later run of the same language in the same tab, **Then** the earlier run shows "📦 This package was replaced by a later run of <language>. Download it from that run." and its zip is dropped from the tab.
4. **Given** a failed, cancelled or unauthenticated run, **Then** no package is shown.

---

### User Story 4 - Cancelling and closing (Priority: P2)

Closing the tab during a run stops the run and frees the server for others, as today.

**Acceptance Scenarios**:

1. **Given** a run in progress, **When** the tab is closed or reloaded, **Then** the server stops the pipeline (and the AI check) and releases the one-run lock within a few seconds.
2. **Given** the sign-in popup is open, **When** it is closed without signing in, **Then** the run shows "⏹️ Authentication cancelled: Google sign-in wasn't completed. Nothing was created or deleted." and the remaining languages aren't started.

### Edge Cases

- **Refused account** (not `@curiouslearning.org`, unverified email): "❌ Authentication failed: only Curious Learning (curiouslearning.org) accounts can add languages (signed in as <email>). Nothing was created or deleted." The token is forgotten, so the next Generate asks again.
- **Expired token** (older than its lifetime): the page asks for sign-in again before starting a run instead of failing mid-run.
- **Popup blocked by the browser**: the run says the popup was blocked and to allow popups for this site, and nothing starts.
- **Sign-in not set up** (OAuth client missing or invalid on the server): the page shows the setup error and Generate is disabled (fails closed), as today.
- **Server restarted or redeployed mid-run**: the run shows as failed with the server's last message; nothing is left locked.
- **Large package**: a zip of a few hundred MB is held in the tab; the page shows "Preparing the package…" while it is fetched and an error if fetching fails, with no retry needed for the run itself.
- **Long downloads with no output**: the run's connection stays open (the server sends keep-alive lines) so proxies don't close it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The page MUST be a static web page served by the same service as the pipeline. It MUST open a connection to the server only to load, to read its settings, to run a language (for the duration of that run, including the AI check) and to fetch a package. No connection may stay open while no run is in progress in that tab.
- **FR-002**: The page MUST look like the current page: the same title, caption, controls, labels, icons, messages, colors (primary red button, green/blue/yellow/red message boxes), a centered narrow column, run boxes with a status title, expanders, and a fixed-height auto-scrolling log.
- **FR-003**: All behaviour of specs 003, 004, 005 (as revised by this spec), 006 and 008 (as revised by this spec) MUST be kept, as listed in User Stories 1–4.
- **FR-004**: Only one run at a time across all tabs and users. A second Generate MUST be refused without touching disk. The input, Generate and the toggles MUST be disabled while a run is queued or running in this tab.
- **FR-005**: Sign-in MUST happen in a Google popup on the first Generate of a tab (and again when the token has expired or was refused). The server MUST check every run's token with Google and admit only an email that is verified, whose hosted domain is `curiouslearning.org` and that ends with `@curiouslearning.org`, before starting the pipeline. The pipeline's own domain re-check (`✅ Authenticated as`) MUST stay.
- **FR-006**: The Google token MUST live only in the tab's memory: never in browser storage, never written to disk on the server, never logged, and passed to the pipeline subprocess only, never to the AI check.
- **FR-007**: The pipeline's stdout log contract (constitution principle IV) MUST be parsed by the new page with the same prefixes and the same results as `app.py` did.
- **FR-008**: If a run's connection closes before it finishes (tab closed or reloaded), the server MUST stop the pipeline and the AI check and release the lock.
- **FR-009**: After a successful or warning run, the page MUST fetch that run's package as a zip into the tab. On the hosted server the language folder MUST be deleted once fetched, or 10 minutes after the run if nobody fetches it, and never during a run. Locally nothing is deleted.
- **FR-010**: The server MUST be able to scale to zero between runs; the hosting no longer needs session affinity, and the idle pause of spec 011 MUST be removed because no idle connection exists any more.
- **FR-011**: The command line (`python generate_language.py <Language>`) MUST keep working unchanged.
- **FR-012**: Local development MUST work with one command for the server and the built page, and a dev mode with live reload for the page.

### Key Entities

- **Run**: one language's attempt: language, start time, state (`running`, `complete`, `warning`, `error`, `cancelled`), signed-in account, steps reached, log lines, errors, missing / deleted / look-alike / standardized audio lists, AI report and AI log, package (zip held in the tab, or the reason it isn't available). Kept only in the tab.
- **Sign-in**: the tab's Google access token, its email and expiry. Kept only in tab memory.
- **Server settings**: whether sign-in is set up (and the public client id), whether the server is hosted, the AI provider and model or why it isn't configured, whether a run is in progress.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A tab that is open with no run holds 0 open connections to the server after the page has loaded (verified in the browser network panel and the Cloud Run request logs).
- **SC-002**: Billed instance time for the service is no more than the time runs take plus a few minutes of shutdown delay per run (check Billing "Services CPU (Request-based billing)" a week after deploying).
- **SC-003**: Generating Hausa on the new page gives the same steps, audio check summary, missing/unused lists and package contents as the Streamlit page did.
- **SC-004**: Closing the tab during a run frees the server for another run within 10 seconds.
- **SC-005**: A content team member who used the Streamlit page can generate a language on the new page without instructions.

## Assumptions

- Users use a current desktop browser that allows popups for the site after a first prompt.
- The existing Web application OAuth client is reused; its "Authorized JavaScript origins" gets the hosted address and `http://localhost:8080` (and `http://localhost:5173` for page development). This is a one-time console step for the user.
- Google access tokens last about an hour; a run is much shorter, so one token covers a run. The pipeline does not need a refresh token.
- The service keeps one instance at most (the one-run lock lives in the server process).
- Packages are small enough to keep in a browser tab (peak server use so far was about 225 MB for everything).
- Hosting and CircleCI stay as in specs 005, 007 and 010; only the image's contents and a few deploy flags change.
