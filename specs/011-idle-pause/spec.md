# Feature Specification: Pause Idle Pages

**Feature Branch**: `011-idle-pause`

**Created**: 2026-10-27

**Status**: Implemented

**Input**: User description: "The server should only run when the website is being used. It shouldn't be running the whole day. Keeping the server running while nobody is using it is a problem. Fix it so that I can reduce the cost."

## Context

A cost review of `ftm-language-generator` (2026-10-27) found that about 96% of the bill ($4.00 of $4.16 in 30 days) was Cloud Run CPU and memory: about 38 billed instance hours in 12 days, while the generator was used for only a few runs.

The cause is open browser tabs. Every open Streamlit page keeps a websocket (`/_stcore/stream`) to the server. Cloud Run with request-based billing charges for as long as any request is open, so one tab left open keeps the service billed. The request logs showed websockets lasting exactly 3,601 s (the service's `--timeout=3600`) and then reconnecting. Instances started 70-80 times a day over a weekend with no runs.

Cloud Run already scales to zero (no minimum instances). The fix is to make idle tabs let go of the server.

## User Scenarios & Testing

### User Story 1 - An idle tab stops keeping the server running (Priority: P1)

A team member generates a language, downloads the package and leaves the tab open. After 15 minutes with no activity the page disconnects from the server and shows a "paused" page with a **Resume** button. With no open connections, Cloud Run stops billing and scales to zero.

**Acceptance Scenarios**:

1. **Given** a hosted page with no mouse, keyboard, touch or scroll activity for 15 minutes and no run in progress in that tab, **When** the time is up, **Then** the tab shows the paused page and its websocket to the server is closed.
2. **Given** an idle page, **When** one minute is left, **Then** a notice at the bottom says the page will pause in a minute. **When** the user moves the mouse or presses a key, **Then** the notice goes away and the timer starts again.
3. **Given** a run (sign-in, pipeline or AI check) is queued or in progress in this tab, **When** 15 minutes pass with no activity, **Then** the page does not pause. The timer starts again when the run finishes.
4. **Given** the paused page, **When** the user clicks **Resume**, **Then** the generator page loads again as a new page visit (sign in again on the next Generate).
5. **Given** the Google sign-in tab (the callback tab that says to go back to the generator tab), **When** it has had no activity for 2 minutes, **Then** it pauses too.
6. **Given** a package that was not downloaded, **When** the page pauses, **Then** the paused page says that packages that weren't downloaded have been removed from the server (spec 008 deletes them 60 s after the session ends).

## Requirements

- **FR-001**: On the hosted deploy (`FTM_HOSTED=1`) the page pauses after `FTM_IDLE_PAUSE_MINUTES` (default 15) without activity. Locally the default is 0 (never). Setting the variable overrides either default; 0 turns it off.
- **FR-002**: Pausing must close the page's connection to the server. Implemented by replacing the tab with a local page (a `blob:` URL; `about:blank` as a fallback), which unloads the Streamlit app.
- **FR-003**: A run queued or in progress in the same tab blocks the pause.
- **FR-004**: A one-minute warning is shown before pausing (or half the idle time, if that's shorter).
- **FR-005**: The Google sign-in callback tab pauses after `min(2, FTM_IDLE_PAUSE_MINUTES)` minutes.
- **FR-006**: The server side does not change: no new Cloud Run settings and no new services.

## Implementation

- `language_automation/idle_pause.py`: `idle_minutes()` and `install(running, minutes=None)`, which adds the watcher script with `st.html(..., unsafe_allow_javascript=True)`. The script installs once per tab (`window.__ftmIdle`) and every render updates its settings and counts as activity.
- The paused page's HTML is sent inside the script's JSON config with every `<` escaped as `\u003c`. Streamlit's HTML sanitizer (DOMPurify) drops a script whose text looks like markup.
- `app.py` calls `idle_pause.install(running=bool(pending_langs))` right after `busy` is computed, and `render_signin_callback` installs it with the short callback timeout before `st.stop()`.

## Success Criteria

- **SC-001**: An idle tab holds no connection to the server after the idle time (tested: 7 open connections before the pause, 0 after).
- **SC-002**: Cloud Run billed instance time falls to roughly the time people actively use the page. Check it in Billing reports (SKU "Services CPU (Request-based billing)") a week after deploying.
