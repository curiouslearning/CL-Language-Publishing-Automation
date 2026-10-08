# Feature Specification: Baseline – FTM Language Publishing Pipeline (as built)

**Feature Branch**: `001-baseline-language-pipeline` (spec folder only; no branch created)

**Created**: 2026-10-05

**Status**: Implemented. This spec records existing behavior; it does not propose new work.

**Input**: User description: "I want to make sure that whatever has been implemented till now should be created as a Markdown file using the existing spec kit feature."

## Overview

Curious Learning publishes new languages for the game *Feed the Monster* (FTM). Each language's
content is kept on a shared Google Drive. One **language sheet** describes the levels and puzzles,
and one **language audio folder** holds the recorded prompts and feedback. This tooling turns those
Drive sources into a ready-to-use **language package** on a local machine:

- the game content file,
- exactly the audio files that content needs, with the spelling the game expects,
- a report of what is still missing.

Before this tooling, someone assembled each language by hand. That was slow, and it was easy to
ship unused, misspelled or missing audio. This spec records the behavior as it exists today, so
that future specs can describe changes relative to it.

> **Later features:**
> - An optional AI review of a language's letters, words and sentences is specified in
>   `specs/003-ai-language-check/`. It's advisory and runs after this pipeline.
> - The web page's behaviour is specified in `specs/004-generator-page-flow/`, which supersedes the
>   page details in User Story 5 below:
>   - "Authentication in progress" before the steps;
>   - Generate locked during a run;
>   - cancelling when the tab closes or sign-in times out;
>   - "Do you need to regenerate this language?";
>   - "Add another language".
> - Google sign-in is checked first, before Step 1, and only `curiouslearning.org` accounts are
>   accepted (spec 002, revised).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate a language package from Drive (Priority: P1)

A content team member enters a language name, for example "Hausa". The system finds that
language's sheet and audio folder on Drive. It produces the game content file and downloads every
audio recording into a fresh local language package. Recordings that are not already in the game's
audio format are converted so that every file in the package has the same format.

**Why this priority**: This is the core purpose of the tooling. Without it there is nothing to
publish.

**Independent Test**: Run the pipeline for a language that is set up on Drive. Confirm that the
local package contains the content file and an `audios` folder of uniformly formatted audio files.

**Acceptance Scenarios**:

1. **Given** a language whose sheet and audio folder both exist on Drive, **When** the user
   generates it, **Then** a local package is created containing the game content file, an audio
   folder, and an (empty) images folder.
2. **Given** the language sheet is stored as an Excel file, **When** the user generates it,
   **Then** the system still reads the sheet and produces the content file.
3. **Given** a package for that language already exists locally, **When** the user generates it
   again, **Then** the old package is replaced and nothing stale from the previous run remains.
4. **Given** some recordings on Drive are in formats other than the game's, **When** they are
   downloaded, **Then** each one is converted to the game's audio format.
5. **Given** a single file fails to download, **When** the system has retried it several times,
   **Then** it skips that file and continues with the rest. The file then appears in the missing
   audio report.

---

### User Story 2 - Never lose data on a wrong or missing language (Priority: P1)

A user mistypes a language name, or the language has not been set up on Drive yet. The system
reports that the language was not found. Nothing on the local machine is created, changed or
deleted.

**Why this priority**: Every run wipes the language package first. Without this guard, one typo
could destroy a previously good package.

**Independent Test**: Generate a language name that does not exist on Drive. Confirm the run ends
with a clear "not found" message and that the local `lang/` folder is byte-for-byte unchanged.

**Acceptance Scenarios**:

1. **Given** no language sheet matches the name, **When** the user generates it, **Then** the run
   stops with a message naming the language and the missing item ("no language sheet"). No local
   folder is touched.
2. **Given** the sheet exists but there is no matching audio folder, or that folder has no "Feed
   the Monster" subfolder, **When** the user generates it, **Then** the run stops with "no audio
   folder". No local folder is touched.
3. **Given** two languages whose names overlap (e.g. "English" and "EnglishWestAfrican"), **When**
   the user generates "English", **Then** only the language named exactly "English" is used. Case
   differences and sheet file extensions are ignored.

---

### User Story 3 - Reconcile audio with the game content (Priority: P2)

After download, the system compares the audio folder with the audio names the content file
references:

- It removes recordings the content doesn't use.
- When a recording's name differs from the content's spelling only by accent or composition, case,
  or certain look-alike Devanagari vowel sign sequences, it **keeps the recording as is and warns**
  that the names look alike. It does not rename anything. *(Changed 2026-10-06; it used to rename
  automatically.)*
- It reports every referenced recording that is still missing.

**Why this priority**: The game asks for audio by exact name. Unused files bloat the package,
misspellings make audio go silent in-game, and missing files must be recorded by the content team.

**Independent Test**: Generate a language where Drive has one extra recording, one recording with
a near-match spelling, and one referenced recording absent. Confirm the extra is removed, the
near-match is kept and reported as a look-alike, and the absent one is listed as missing.

**Acceptance Scenarios**:

1. **Given** a downloaded recording that the content doesn't reference, **When** reconciliation
   runs, **Then** it is deleted and listed as removed. The exceptions are the always-kept
   recordings "great" and "amazing".
2. **Given** a recording whose name matches a referenced-but-missing name except for spelling
   normalization, **When** reconciliation runs, **Then** the recording is kept unchanged and
   reported as a look-alike ("Drive file ≈ name in the sheet: please check"). The content's name
   is also listed as missing, with a note that Drive has a look-alike.
3. **Given** a referenced recording that is on neither Drive nor disk, **When** reconciliation
   runs, **Then** it is listed as missing, and the run still completes successfully.
4. **Given** every referenced recording is present, **When** reconciliation runs, **Then** the
   system reports that no audio is missing.

---

### User Story 4 - Content that links directly to Drive recordings (Priority: P2)

Some language sheets put a Drive share link where an audio file name would normally go (for
example, for feedback audio). The system downloads each linked recording and gives it a usable
name. It then updates the content file so the link is replaced by a normal audio reference.

**Why this priority**: Without this, linked recordings would be reported missing and the game
couldn't load them, even though the audio exists.

**Independent Test**: Generate a language whose content contains Drive share links. Confirm each
linked recording is in the audio folder and that the content file no longer contains share links.

**Acceptance Scenarios**:

1. **Given** the content contains a Drive share link for an audio, **When** the language is
   generated, **Then** that recording is downloaded under its Drive file name, and the content's
   reference is rewritten to match the other audio references.
2. **Given** two different links point to recordings with the same file name, **When** they are
   downloaded, **Then** both are kept under distinct names, and each reference points to its own
   file.
3. **Given** the content contains no Drive links, **When** the language is generated, **Then**
   this step is skipped entirely.

---

### User Story 5 - Run it from a web page with live progress (Priority: P3)

A non-technical content team member opens a web page and enters one or more language names,
separated by commas. They watch each step progress, including an "N of M files" counter during
download. At the end they see an audio summary: missing, renamed (with a prompt to fix the
spelling in the sheet), and removed. They can download the full log. Earlier runs from the same
session stay visible.

**Why this priority**: It removes the need for a terminal. The command line still offers the same
pipeline to technical users.

**Independent Test**: Open the web page, submit "Hausa", and confirm steps 1–7 tick off, the
download counter advances, and the summary and log download appear at the end.

**Acceptance Scenarios**:

1. **Given** the page is open, **When** the user submits a language, **Then** each pipeline step
   is shown as pending, in progress, done or failed while the run proceeds.
2. **Given** the user's Google sign-in has expired, **When** the run needs Drive access, **Then**
   the page tells the user to complete sign-in and shows a link to the sign-in page.
3. **Given** a run is already in progress, **When** another user submits, **Then** they are told
   to try again later, and no second run starts.
4. **Given** the user submits several languages, **When** the run proceeds, **Then** they are
   generated one after another, each with its own progress and summary.
5. **Given** the run fails, **When** it stops, **Then** the page marks the failed step and shows
   the error. A run that completes but reports some errors is shown as "finished with errors".
6. **Given** the user submits an empty name, **When** they press Generate, **Then** they are asked
   to type a language name.

---

### Removed: Automated content verification reports (legacy)

Two older Cloud Functions emailed missing-audio reports for FTM content and for assessment
sheets. They were **removed from the repository on 2026-10-05**. Their FTM check duplicates User
Story 3. The assessment-content check has no replacement yet. If it's needed, create a new
feature for it.

---

### Edge Cases

- **Language name differs only in case** (e.g. "hausa" vs "Hausa"): it matches. However, the
  local package path uses the name as typed. This works only on case-insensitive filesystems
  (Windows today). See Assumptions.
- **Audio folder exists but has no "Feed the Monster" subfolder**: this is treated as "no audio
  folder". The run stops before anything local is touched (User Story 2).
- **Content file can't be produced** (e.g. the sheet's metadata link is missing or the generator
  fails): the run stops at the sheet step with an error.
- **The same recording appears in nested subfolders**: within one run, a file that already exists
  locally is skipped instead of downloaded again.
- **Format conversion fails for a file**: the failure is logged, the file counts as processed,
  and it will then appear in the missing report.
- **User closes or refreshes the web page mid-run**: the run in progress is stopped. No orphaned
  background run is left behind.

## Requirements *(mandatory)*

### Functional Requirements

**Language lookup and safety**

- **FR-001**: The system MUST accept a language name from either the command line or the web
  page.
- **FR-002**: The system MUST confirm that both the language sheet and the language audio folder
  exist on Drive before creating, wiping or modifying any local data. If either is missing, it
  MUST stop with a non-success result.
- **FR-003**: The system MUST match a language by exact name, ignoring letter case and sheet file
  extensions. It MUST NOT choose a sheet or folder whose name merely contains the language name.

**Package generation**

- **FR-004**: The system MUST start each run from an empty local language package. Any previous
  package for that language is replaced.
- **FR-005**: The system MUST produce the game content file from the language sheet. It MUST use
  the content-generation link stored in the sheet's metadata, and it MUST support sheets stored as
  Excel files.
- **FR-006**: The system MUST download every recording under the language's "Feed the Monster"
  audio folder, including nested subfolders. It MUST deliver every recording in the game's single
  audio format (mp3, 44.1 kHz, stereo).
- **FR-007**: The system MUST retry a failed download several times before skipping that file, and
  then continue with the remaining files.
- **FR-008**: When the content references audio by Drive share link, the system MUST download each
  linked recording. It MUST give recordings that share a file name distinct names, and it MUST
  rewrite each link in the content file to a standard audio reference.

**Audio reconciliation**

- **FR-009**: The system MUST determine the required audio set from the content's puzzle prompts,
  feedback audio, and other audio entries.
- **FR-010**: The system MUST delete downloaded recordings that are not in the required set,
  except the always-kept recordings ("great", "amazing").
- **FR-011** *(revised 2026-10-06, user decision)*: When a recording's name matches a required
  name only after normalizing for Unicode composition, letter case, or look-alike Devanagari vowel
  sign sequences, the system MUST **keep the recording unchanged** (neither rename nor delete it)
  and **warn** that the two look alike. The fix is the content team's. The system MUST NOT rename
  or "correct" names on the basis of similarity.
- **FR-011a** *(added 2026-10-06)*: The results MUST explain each look-alike:
  - the pair (Drive file ≈ name in the sheet), stating that they look the same but are typed with
    different characters, so the game won't find the recording until they match;
  - every sheet text typed with a look-alike sequence (ा + े instead of ो, or ा + ै instead of
    ौ), with its standard form and where it appears. This includes texts whose recordings happen to
    match.

  The missing-audio list MUST point out a missing name that has a look-alike on Drive.
- **FR-012**: The system MUST report every required recording that is absent after
  reconciliation. Missing audio MUST NOT cause the run to fail.

**Reporting and web page**

- **FR-013**: The system MUST print a distinct, stable status line for each step and for each
  deleted, renamed or missing file, so that the web page can show them.
- **FR-014**: The web page MUST show step-by-step progress, a per-file download counter, Google
  sign-in prompts, and a final audio summary listing missing, renamed and removed files. It MUST
  also offer the run log as a download.
- **FR-015**: The web page MUST allow only one run at a time across all users. It MUST accept
  several comma-separated languages and process them one after another.
- **FR-016**: The web page MUST keep earlier runs from the current browser session visible, with
  their outcome, log and summary.

*(FR-017 and FR-018, covering the legacy verification services, were retired on 2026-10-05.)*

### Key Entities

- **Language**: a named FTM language (e.g. Hausa). It is identified by the exact name of its sheet
  and audio folder on Drive.
- **Language Sheet**: the spreadsheet on Drive that holds a language's levels and puzzles. Its
  metadata contains the link used to generate the game content file.
- **Game Content File**: the generated per-language content the game loads. It is the source of
  truth for which audio names are required.
- **Language Audio Folder**: the Drive folder of recordings for one language. Recordings are
  under a "Feed the Monster" subfolder, possibly nested further.
- **Recording**: one audio file. Its name must exactly match a name the content references.
- **Language Package**: the local output for one language: the content file, an audio folder and
  an images folder (images are not populated yet).
- **Run**: one generation attempt for one language. It has a start time, a log, errors, and lists
  of deleted, renamed and missing recordings. Its outcome is complete, finished with errors, or
  failed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A content team member can produce a complete language package with a single action:
  typing a name and pressing Generate. No manual file handling is needed.
- **SC-002**: 0 local language packages are lost or modified when a run is started with a name
  that does not exist on Drive.
- **SC-003**: After a successful run, 100% of recordings in the package are referenced by the
  content or are on the always-kept list, and 100% are in the game's audio format.
- **SC-004**: Every required recording that is absent appears in the end-of-run missing list, so
  that the list has no false negatives.
- **SC-005**: Every spelling-only mismatch the normalization covers is fixed automatically and
  reported back to the content team, so that they can correct the sheet.
- **SC-006**: A user who never opens a terminal can follow which step a run is on and see how many
  of the language's audio files have downloaded so far.

## Assumptions

- Users have access to the shared Curious Learning Drive and complete a one-time Google sign-in on
  the machine that runs the tooling.
- The tooling runs on one Windows workstation. The way the local package path is built relies on
  case-insensitive file names, so it is not portable to Linux or macOS as-is.
- The location of language sheets and audio on Drive is fixed and known to the tooling. It is not
  configured per run.
- One run at a time is acceptable. Runs are infrequent, and concurrent runs would conflict over
  local data and the sign-in token.
- Image assets are out of scope. The images folder is created empty for a future feature.
- The content-generation service linked from each sheet is available and returns valid content.

## Known Limitations (as of baseline)

- If a failure happens after the pre-check (e.g. the content can't be generated), the previous
  local package has already been wiped. No last-known-good copy is kept.
- Security findings from the 2026-10-05 review. Resolved unless noted:
  - ~~Crafted Drive file names can write outside the package~~: names are sanitized.
  - The web page has no login of its own and Streamlit listens on all network interfaces.
    *Open.* Since 2026-10-05, every run requires the pipeline's Google sign-in with a
    curiouslearning.org account, but anyone on the network can open the page and start one.
  - ~~The content URL is fetched without checks or a timeout~~: only `https`, with a timeout.
  - ~~The language name isn't validated before the folder wipe~~: it is now validated.
  - The sign-in still requests full Drive access. *Open.* It's needed for the Excel-to-Sheet copy.
- ~~Non-portable path casing~~. Resolved by spec 002: every path is `lang/<lang.lower()>/`.
- ~~Abandoned Google sign-ins block the web page for everyone~~. Fixed 2026-10-05: closing the
  tab, or a 3-minute sign-in timeout, cancels the run.
