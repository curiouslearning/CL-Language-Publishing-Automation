# Feature Specification: Language Package Download

**Feature Branch**: `008-language-package-download`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "Let the content team download a generated language package from the hosted page: after a run that completes (or completes with warnings), offer a "Download language package (.zip)" button containing lang/<language>/ (the game JSON and the audios folder). On Cloud Run the files live only in the instance's memory and disappear when it scales to zero or redeploys, so the download must be available right after the run, clearly say it's temporary, and must not trigger a rerun mid-run. Builds on spec 005 research R10."

**Revision (2026-10-15, user decision)**:
- No permanent storage on the server: no Cloud Storage bucket, no Drive upload.
- A generated package stays on the server only while the page session that generated it is open, so it can be downloaded. When that session ends (tab closed, page reloaded, or the session times out), the package is deleted, downloaded or not. It must not keep using server memory.
- The downloaded zip on the user's computer is the only lasting copy. Drive stays the source to regenerate from.

## Context

Since spec 007 the generator runs on Cloud Run. There, a run writes the language package (game JSON + audio) into the server's memory, which shares the service's 2 GiB with the app itself. Today:
- nobody can reach those files;
- they stay in memory after the person has left, until the instance happens to shut down;
- every additional language adds to memory use.

This feature delivers the package to the person who generated it, and frees the memory as soon as their session is over.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Download the package right after a run (Priority: P1)

A content team member generates a language on the hosted page. When the run finishes as complete or complete-with-warnings, the run's summary shows a **Download language package (.zip)** button next to the existing log download. One click saves a single file with the language's game JSON and every audio file the run kept. Unzipped, it has the same folder layout as a locally generated `lang/<language>/`.

**Why this priority**: without it, the hosted page can't deliver what it generates.

**Independent Test**: on the hosted page, generate a small language, download the zip, unzip it, and compare it with the same language generated locally: the same JSON and the same set of mp3 files.

**Acceptance Scenarios**:

1. **Given** a run that finished as complete, **When** the user clicks the package download, **Then** a file named `<language>_<run start time>.zip` is saved. It contains one top-level folder `<language>/` with the game JSON, `audios/` (every mp3 the run kept) and `images/`.
2. **Given** a run that finished with warnings (e.g. missing audio), **When** the user downloads it, **Then** they get the package as it stands, and the summary's warnings stay visible.
3. **Given** a run that failed, was cancelled, or whose sign-in was refused, **When** its summary is shown, **Then** no package download is offered.
4. **Given** the user clicks the package download, **When** the download starts, **Then** the page doesn't reload or rerun, and runs in progress keep running.
5. **Given** the user already downloaded the package, **When** they click again in the same session, **Then** they get the same package again.

---

### User Story 2 - The package is cleaned up when the session ends (Priority: P1)

On the hosted page, a package is kept only for the page session that generated it. When the user closes the tab, reloads the page, or the session ends any other way, the server deletes that session's packages, whether they were downloaded or not, and the memory they used is freed. The page says this plainly next to the download button.

**Why this priority**: the user's explicit requirement. Packages left behind use the server's limited memory and can crash it for everyone.

**Independent Test**: generate a language on the hosted page and note that its package exists on the server. Close the tab. Within the cleanup time, the package is gone from the server and the server's memory use drops back.

**Acceptance Scenarios**:

1. **Given** a finished run with a package, **When** its summary is shown, **Then** a note next to the button says: the package is kept only until you close or reload this page, so download it now.
2. **Given** a session with one or more generated packages, **When** the tab is closed (or reloaded, or the session times out), **Then** all packages that session generated are deleted from the server within 2 minutes.
3. **Given** a package was downloaded, **When** the session ends, **Then** it's deleted the same way. The downloaded zip on the user's computer is unaffected.
4. **Given** a run is still in progress when the tab is closed, **When** the run is cancelled (existing behaviour), **Then** its partial language folder is deleted too.
5. **Given** a session ends, **When** cleanup runs, **Then** packages that belong to other, still-open sessions are left untouched.
6. **Given** the page runs locally on a laptop (not hosted), **When** the tab is closed, **Then** nothing is deleted: `lang/` stays the developer's working output, as today.

---

### User Story 3 - Several languages in one visit (Priority: P2)

After "Add another language", the earlier run moves to "Previous runs". Its package stays on the server, and downloadable, as long as the same session is open, so someone generating several languages in a row can download them at the end, before closing the tab.

**Why this priority**: convenient, but US1 already covers the need.

**Independent Test**: generate A, click "Add another language", generate B, then download A from "Previous runs". Close the tab: both are cleaned up.

**Acceptance Scenarios**:

1. **Given** language A was generated earlier in this session and nobody regenerated it since, **When** the user opens A under "Previous runs", **Then** A's download is offered and gives A's files.

---

### Edge Cases

- **Same language, two sessions:** if another session regenerates a language, that package now belongs to the other session. The earlier session's run shows "replaced by a later run" instead of a download, and the earlier session's cleanup must not delete the other session's package.
- **Same language regenerated in the same session:** only the latest run offers the download. Earlier runs show "replaced by a later run".
- **Language being rebuilt right now:** no summary for that language offers a download until the run has finished.
- **Package gone for any other reason** (instance restarted, redeployed, crashed): the session is gone too, so no stale buttons remain. If a summary is still shown somehow, it says the package is no longer on the server and must be generated again.
- **Short disconnects** (laptop sleep, flaky network): cleanup happens only once the session has really ended, using the same detection as the existing tab-close cancellation. It doesn't happen on a momentary blip that reconnects.
- **Leftovers:** a package that no open session owns (e.g. left after an unexpected error) is also removed by the next cleanup pass. A fresh server starts empty.
- **Large languages:** preparing the download must not keep a second full copy of the package around beyond serving it. Packages up to at least 300 MB must download without the server running out of memory.
- **AI check results:** the small AI result cache isn't part of the package and isn't affected by this cleanup.
- **The "Do you need to regenerate this language?" dialog:** on the hosted page it only appears if this session still has that language's package, because other sessions' packages are cleaned up with their sessions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After a run whose result is complete or warning, the run's summary MUST offer a **Download language package (.zip)** action.
- **FR-002**: The download MUST contain exactly the language's generated folder: one top-level `<language>/` folder with the game JSON, `audios/` and `images/`. Nothing else: no logs, no AI cache, no other languages, no credentials.
- **FR-003**: The file MUST be named `<language>_<run start time>.zip`, in the same timestamp style as the existing log download.
- **FR-004**: Clicking the download MUST NOT reload or rerun the page, and MUST NOT interrupt, cancel or restart any run (spec 004 rule).
- **FR-005**: On the hosted page, a note next to the action MUST say the package is kept only until this page is closed or reloaded, and should be downloaded now.
- **FR-006**: The download MUST be offered only while the files on the server are still the ones produced by that run. Otherwise the action MUST be replaced by a note giving the reason: replaced by a later run, being regenerated, or no longer on the server.
- **FR-007**: No download MUST be offered for failed, cancelled or unauthenticated runs.
- **FR-008**: Runs moved to "Previous runs" MUST keep offering their download under the same rules while the session is open.
- **FR-009 (cleanup)**: On the hosted page, every language package MUST belong to the page session whose run last generated it. When that session ends (tab closed, reloaded, or timed out), the server MUST delete all packages it owns within 2 minutes, whether downloaded or not, including the partial folder of a run cancelled by the tab closing.
- **FR-010**: Cleanup MUST NOT delete a package owned by another session that's still open, and MUST NOT delete anything when the page runs locally (not hosted). Command-line runs are never affected.
- **FR-011**: A package that no open session owns MUST be removed by the next cleanup pass on the hosted page.
- **FR-012**: Any temporary file made to serve a download MUST be removed once it's served, or at the latest with its session's cleanup. Preparing downloads MUST NOT make the server run out of memory for packages up to at least 300 MB.
- **FR-013**: The download MUST be available only to the page session that shows the run. It MUST NOT be reachable through a public link.
- **FR-014**: `CLAUDE.md` (Web UI and Hosting sections) and the README MUST describe the download and the session cleanup. CLAUDE.md's "Not done yet: getting the generated package off the server" note MUST be removed.

### Key Entities

- **Language package**: the generated `<language>/` folder (game JSON, `audios/`, `images/`) left by one finished run.
- **Package owner**: the page session whose run last generated a language package (hosted page only). The package lives exactly as long as that session.
- **Package download**: a single zip file made from one package, named after the language and the run's start time.
- **Run result**: the existing per-run record shown in the summary. It now also says whether its package is still current and available.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a successful hosted run, the user can save the package in one click, within 10 seconds of the run finishing, for a typical language (about 10–50 MB).
- **SC-002**: The unzipped package matches a locally generated package for the same language: 100% of the same files, with identical JSON.
- **SC-003**: 0 runs are interrupted or restarted by a package download.
- **SC-004**: 0 downloads deliver a package from a different run than the one whose summary offered it.
- **SC-005**: Within 2 minutes of a session ending, 100% of that session's packages are gone from the server, and the server's memory use returns to what it was before those runs (within normal variation).
- **SC-006**: 0 packages belonging to still-open sessions are deleted by cleanup.
- **SC-007**: A 300 MB package downloads successfully on the hosted page without the service restarting.

## Assumptions

- The person downloading is the signed-in curiouslearning.org user of that page session (spec 005). No extra permission is needed.
- No permanent server-side copy (bucket or Drive) is wanted (user decision). Losing an undownloaded package only costs a re-run from Drive.
- "Session ended" uses the same detection the page already uses to cancel a run when its tab closes. Reloading the page starts a new session, so it ends the old one.
- The server runs as a single instance (spec 005 R8), so every session sees the same files and ownership can be tracked on that instance.
- Package sizes: Marathi is about 11 MB. Most languages are expected to be under 100 MB; 300 MB is a generous upper bound. The plan may raise the 2 GiB memory setting if testing shows it's needed.
- Local use keeps today's behaviour (`lang/` persists) because developers use it as their working output.
- Out of scope: several languages in one zip, choosing which files to include, the AI check output in the package (it has its own download), and changing what the pipeline produces.
