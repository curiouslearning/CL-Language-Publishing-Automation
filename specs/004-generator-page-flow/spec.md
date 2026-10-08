# Feature Specification: Generator Page Flow (as built)

**Feature Branch**: `004-generator-page-flow` (spec folder only; no branch created)

**Created**: 2026-10-06

**Status**: Implemented. This spec records what the page already does, the same way spec 001
records the pipeline. It collects the page behaviours that were requested and built during
2026-10-05 and 2026-10-06 without their own spec.

**Input**: User requests, in order:
- "show 'Authentication in progress'… if success show success and then show steps";
- "if the user closes the tab, cancel the process";
- "don't allow them to click the Generate button again at the same time… clear the input… ask
  'Do you need to regenerate this language?'";
- "once a success and every step completes… give an option at the bottom and on the top to add
  another language".

## Overview

The content team uses one web page to generate languages. This spec covers what a team member
sees from typing a language name to being ready for the next one:
- sign-in feedback;
- protection against double-clicks and abandoned runs;
- a confirmation before overwriting a language that's already generated;
- a clear way to start the next language.

The pipeline itself (spec 001) and the optional AI check (spec 003) are referenced, not
repeated.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See sign-in before the steps (Priority: P1)

After pressing Generate, the run first shows only **"Authentication in progress"**. If Google needs
a sign-in, a link to it is shown too. Only when sign-in succeeds does the page show **"Authenticated
as <email>"**, followed by the pipeline steps and the log.

**Why this priority**: People shouldn't see steps "running" while the generator is actually
waiting for them to sign in.

**Independent Test**: Generate a language while signed out. Only "Authentication in progress"
appears until sign-in completes, then the steps appear.

**Acceptance Scenarios**:

1. **Given** the user presses Generate, **When** sign-in hasn't completed, **Then** no step and
   no log line is shown, only "Authentication in progress".
2. **Given** sign-in succeeds with a `curiouslearning.org` account, **When** it completes,
   **Then** "Authenticated as <email>" is shown, and the steps and log follow.
3. **Given** sign-in fails, or the account isn't `curiouslearning.org`, **When** the run ends,
   **Then** it shows "Authentication failed", no steps are shown, and nothing was created.

---

### User Story 2 - One run at a time, never stuck (Priority: P1)

While a language is being generated, the language box, the Generate button and the AI toggle are
locked, so a second click can't start a duplicate run or interrupt the current one.

If the user closes the tab, or doesn't finish the Google sign-in within 3 minutes, the run is
cancelled and the generator becomes free for anyone.

**Why this priority**: Before this, a second click could kill the run in progress, and an
abandoned sign-in blocked everyone.

**Independent Test**: Start a run and try to click Generate: nothing happens. Close the tab
during sign-in: a new tab can start a run straight away.

**Acceptance Scenarios**:

1. **Given** a run is in progress, **When** the user looks at the form, **Then** the language
   box, Generate and the AI toggle are disabled, and the language box is empty.
2. **Given** another user's run is in progress, **When** someone opens the page, **Then** the
   form is disabled, with "Another language is being generated right now".
3. **Given** a run is in progress, **When** its browser tab is closed, **Then** the run is
   cancelled within seconds, and the generator is free.
4. **Given** Google sign-in is waiting, **When** it isn't completed within 3 minutes, **Then**
   the run is cancelled with "Nothing was created or deleted".
5. **Given** the run finishes, **When** the page refreshes, **Then** the form is enabled again,
   and the finished run is shown expanded under **Latest run**.

---

### User Story 3 - Confirm before regenerating (Priority: P2)

If the entered language already has its game content and audio on this computer, the page asks
**"Do you need to regenerate this language?"**, showing how many audio files it has, before
anything happens.

**Why this priority**: Regenerating deletes the folder and downloads everything again, which takes
time and can't be undone.

**Independent Test**: Generate a language that's already present. The question appears. "No"
leaves it untouched; "Yes" regenerates it.

**Acceptance Scenarios**:

1. **Given** the language folder has its game content and at least one audio file, **When** the
   user presses Generate, **Then** the question is shown and nothing has run yet. That includes
   no Google sign-in.
2. **Given** the question is shown, **When** the user answers "No" or closes it, **Then** the
   language is kept as it is ("Not regenerated: <language>"). Other new languages in the same
   request still run.
3. **Given** the question is shown, **When** the user answers "Yes, regenerate", **Then** the
   language is generated again as normal.

---

### User Story 4 - Add another language after a successful run (Priority: P2)

When every language in the run has finished all its steps, the page shows **"✅ <languages>
generated. You can add another language now."** with an **➕ Add another language** button at the
top of the results, and a second **➕ Add another language** button at the bottom.

Clicking either one:
- moves the finished run into **Previous runs**;
- empties the language box and puts the cursor in it;
- scrolls back to the top.

**Why this priority**: After a long run, the team needs an obvious next step, wherever they are on
the page.

**Independent Test**: Generate a language successfully, scroll to the bottom and click **Add
another language**. The page returns to the top with an empty, focused language box, and the run
is listed under Previous runs.

**Acceptance Scenarios**:

1. **Given** every language in the last run finished all steps (completed, or completed with
   warnings), **When** the results are shown, **Then** the message and button appear above
   **Latest run**, and a second button appears below the last run's results.
2. **Given** a run failed, was cancelled, or failed sign-in, **When** the results are shown,
   **Then** neither button appears. The form is still available for another attempt.
3. **Given** the buttons are shown, **When** the user clicks either one, **Then** the finished run
   moves to Previous runs, the language box is empty and focused, the page is scrolled to the top,
   and the buttons disappear.
4. **Given** a run is in progress, **When** the page is drawn, **Then** the buttons are never
   shown, because any click would interrupt the run.

---

### Edge Cases

- **Several languages in one request**: the buttons appear only when **all** of them finished. The
  message lists them all.
- **Downloads during a run**: download buttons don't reload the page, so they can't interrupt a
  run.
- **Refreshing the page**: the browser session's run history is kept. A refresh during a run
  counts as closing the tab, so the run is cancelled.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After Generate, the page MUST show only "Authentication in progress", plus the
  sign-in link when one is needed, until the pipeline confirms sign-in. Only then MUST it show
  "Authenticated as <email>" followed by the steps and log.
- **FR-002**: A failed or refused sign-in MUST end with "Authentication failed", no steps, and
  nothing created.
- **FR-003**: The language box, Generate and the AI toggle MUST be disabled while a run is queued
  or running in this tab, or while another tab or user holds the generator.
- **FR-004**: The language box MUST be emptied when Generate is pressed.
- **FR-005**: A run MUST be cancelled, and the generator freed, when its tab closes, or when a
  Google sign-in isn't completed within 3 minutes.
- **FR-006**: Before running a language whose folder already has its game content and at least one
  audio file, the page MUST ask "Do you need to regenerate this language?". Nothing may run until
  the user answers. "No" or closing the question keeps it.
- **FR-007**: After the run, the form MUST be enabled again, and the run shown expanded under
  "Latest run". Earlier runs in the session are listed, collapsed, under "Previous runs".
- **FR-008**: When every language in the last run completed all its steps (state completed, or
  completed with warnings), the page MUST show an "Add another language" option at the top of the
  results and at the bottom.
- **FR-009**: Either "Add another language" option MUST move the finished run to Previous runs,
  empty and focus the language box, and scroll to the top.
- **FR-010**: No control that reloads the page MUST be available while a run is in progress.

### Key Entities

- **Run** (from spec 001): one language's generation. It has a state (completed, completed with
  warnings, failed, cancelled), a log, an audio summary and, when enabled, an AI report (spec 003).
- **Latest run / Previous runs**: the runs of this browser session, newest first. "Latest" is the
  last batch, until the user starts another language.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of runs, no step is displayed before sign-in is confirmed.
- **SC-002**: 0 duplicate or interrupted runs caused by clicking Generate or a download during a
  run.
- **SC-003**: An abandoned sign-in or closed tab frees the generator within 3 minutes, and within
  seconds for a closed tab.
- **SC-004**: An existing language is never regenerated without the user answering "Yes".
- **SC-005**: After a successful run, the team can start the next language in one click from the
  top or the bottom of the results.

## Assumptions

- The page runs on the computer whose browser handles the Google sign-in (see spec 002, revised).
- "Every step completed" means the pipeline reached its end: completed, or completed with
  warnings such as missing audio. Failed, cancelled or refused runs don't qualify.
- Run history lasts for the browser session only.
