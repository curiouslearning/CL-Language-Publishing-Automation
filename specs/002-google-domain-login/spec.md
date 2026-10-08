# Feature Specification: Google Sign-In Restricted to Curious Learning Accounts

**Feature Branch**: `002-google-domain-login` (spec folder only; no branch created)

**Created**: 2026-10-05

**Status**: Revised 2026-10-05. Implemented with the **existing** Google sign-in
(`credentials.json` → `token.json`). The separate Streamlit login was removed at the user's
request.

> **Final decision (user, 2026-10-05)**: "Don't integrate a separate sign-in authentication from
> Streamlit. It's already handled with the existing code."
>
> What is in effect now:
> - **On Generate**: the user types a language and presses Generate. The pipeline's own Google
>   sign-in runs, and the run's box shows only **"Authentication in progress"**, with no steps and
>   no log.
> - **On success**: it shows **"Authenticated as <email>"**, and then the steps run.
> - **Curious Learning only**: only `@curiouslearning.org` accounts proceed. Any other account
>   stops before Step 1 with "Authentication failed", nothing is created, and its `token.json` is
>   deleted.
> - **Never blocked**: closing the tab, or not finishing sign-in within 3 minutes, cancels the run
>   and frees the generator.
>
> **Still met**: FR-002 (curiouslearning.org only, checked against the account Google reports),
> FR-004 (nothing created on failure), FR-005 (refusal message), FR-005a (authentication shown
> before the steps), FR-001b (tab close cancels), FR-012, SC-002 and SC-006.
>
> **Withdrawn**: everything specific to a separate web login or to hosting. That is FR-001a,
> FR-003 (Google `hd` claim; the email-domain check is used instead), FR-006, FR-007, FR-008,
> FR-009 (per-user tokens; runs use the shared `token.json`), FR-010, FR-011, FR-013, US3, and
> amendments A1–A4 and I1. The rest of this document is kept as a record of the earlier design.

**Input**: User description: "content team will be using a web URL and will be logging in with google before adding new language to test, as only the curiouslearning.org emails can do this. When the user adds the language name from the Streamlit UI, it asks for login from Google, and a Curious Learning account can only allow it. If it fails, the language-adding process should fail and shouldnt create anything."

## Overview

Today the language generator web page has no login. Anyone who can reach it can start a run, and
every run uses the Google access of whoever set up the machine. The 2026-10-05 security review
flagged this (see `specs/001-baseline-language-pipeline/spec.md`, Known Limitations).

The content team will now open the generator at a shared web address. Before any language is
generated, the person MUST sign in with Google using a Curious Learning account. Anyone else is
refused. A refused or failed sign-in stops the request before anything is created, deleted or
changed.

## Clarifications

### Session 2026-10-05

- Q: Which accounts may sign in? → A: **Only `curiouslearning.org` accounts.** No other domain (including `sutara.org`) and no personal accounts.
- Q: Whose Drive access does a run use? → A: **The signed-in person's own.** The Google sign-in that
  asks for Drive access *is* the login. The sheets, Drive-linked audio and audio folders are on
  Curious Learning's Drive. They can be read only by Curious Learning accounts, or by someone the
  Curious Learning Drive has explicitly shared them with. A run can read only what the signed-in
  person can see there.
- Two layers of protection: (1) the generator admits only `curiouslearning.org` accounts (FR-002).
  (2) Curious Learning's Drive sharing decides what each admitted person can read (FR-009). Layer 2
  alone isn't enough: an outside person who was given Drive access must still be refused by
  layer 1.
- Q: What should the page show while signing in? → A: An **"Authenticating…"** state comes first.
  Then either an error, with no steps shown and nothing run, or a success message, after which
  the automation steps appear and start.
- Observed: today a non-Curious Learning account sees Google's "Google hasn't verified this app"
  warning screen. That screen is only a warning and can be clicked through, so it is **not**
  treated as access control (see FR-003).

### Planning amendments (2026-10-05, from `/speckit-plan`, to be confirmed by the user)

- **A1 (revised by the user, 2026-10-05)**: The user first enters the language name and presses
  Generate. If they're not signed in, they are **taken straight to the Google login page**. No
  automation steps are shown. After a successful login they return to the generator, and the run
  for **the language they entered** continues automatically: "Authenticating…" → ✅ → steps.
  If the user closes the login tab or abandons the login, the request is **cancelled**. Nothing is
  created, nothing is left running, and the generator is immediately free for a new language.
- **A1b (user-reported bug, 2026-10-05)**: closing the generator tab while a run is in progress
  (including while it waits for sign-in) MUST cancel that run and free the generator for others.
  An abandoned sign-in MUST NOT block the generator. This is now fixed in the current app: a run
  is cancelled when its browser tab closes, or after 3 minutes waiting for a sign-in nobody
  completes.
- **A2**: A cancelled sign-in and a failed sign-in show one combined message ("Sign-in was
  cancelled or didn't complete"), because the sign-in service can't tell them apart. A refused
  account still gets its own message. This refines FR-005.
- **A3**: Google's Drive access from a sign-in lasts about one hour. Before a run, the user may be
  asked to sign in again (one click) if too little time is left. The 8-hour limit in FR-006 still
  applies to the sign-in itself.
- **I1 (implementation, 2026-10-05)**:
  - Without sign-in configuration, the page **fails closed**: it shows a setup error and runs
    nothing.
  - For one person's own computer only, `FTM_LOCAL_NO_LOGIN=1` turns sign-in off. A warning
    banner is shown, and runs use that computer's `token.json`, as the command line does. This
    keeps the tool usable locally until the web OAuth client exists.
  - It MUST NOT be set on the shared server. `deploy/README.md` and the systemd unit say so.
- **A4**: **New FR-013.** After a run finishes, the signed-in user can download the language
  package as a single .zip file, because the hosted server's folders aren't reachable by the team.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign in with a Curious Learning account to generate a language (Priority: P1)

A content team member opens the generator's web address, enters a language name, and presses
Generate. If they are not signed in yet, they are asked to sign in with Google. They choose their
Curious Learning account, and the language run starts. While they stay signed in, later runs in
the same session don't ask again.

**Why this priority**: This is the feature's purpose. Only authorized staff can publish languages.

**Independent Test**: From a browser that isn't signed in, open the web address and submit "Hausa".
Confirm the Google sign-in appears and that a Curious Learning account can complete it. Confirm the
run then proceeds exactly as in the baseline.

**Acceptance Scenarios**:

1. **Given** a user who isn't signed in, **When** they submit a language name, **Then** they are
   taken to the Google login page. No automation steps are shown.
1a. **Given** the user completes the login, **When** they return to the generator, **Then**
   "Authenticating…" is shown, then "Signed in as <email>", and the run for the language they
   entered starts without retyping.
1b. **Given** the user closes the login tab or doesn't finish logging in, **When** that
   happens, **Then** the request is cancelled. Nothing is created, and another language can be
   started right away.
2. **Given** the user signs in with a `curiouslearning.org` account, **When** sign-in completes,
   **Then** the page shows "Signed in as <email>". Only after that do the automation steps appear,
   and the language run starts.
3. **Given** a signed-in user, **When** they submit another language in the same session,
   **Then** the run starts without asking them to sign in again.
4. **Given** a signed-in user, **When** they choose "Sign out", **Then** the next submission asks
   them to sign in again.

---

### User Story 2 - Refuse everyone else, with nothing created (Priority: P1)

Someone signs in with a personal Gmail account or another organization's account, cancels the
sign-in, or sign-in fails for another reason. They see a clear message that only Curious Learning
accounts can generate languages. The language request is abandoned. No folder is created or
wiped, nothing is downloaded, and no file on Drive is created or changed.

**Why this priority**: The user's explicit requirement. A failed sign-in must leave no trace and
grant no access.

**Independent Test**: Submit a language while signing in with a non-Curious Learning Google
account. Confirm the refusal message appears. Confirm the local language folders are byte-for-byte
unchanged, and that no new file (such as a converted sheet copy) appears on Drive.

**Acceptance Scenarios**:

1. **Given** a user signs in with any account that isn't `curiouslearning.org` (including
   `sutara.org` and personal Gmail), whether or not they clicked through Google's "unverified
   app" warning, **When** sign-in completes, **Then** the "Authenticating…" status becomes the
   error "Only Curious Learning (curiouslearning.org) accounts can generate languages". No
   automation steps are shown, and no run starts.
2. **Given** a user cancels or closes the Google sign-in, **When** they return to the page,
   **Then** the request is abandoned with a message, and no run starts.
3. **Given** sign-in fails for any other reason (network error, Google unavailable, expired
   attempt), **When** the failure is detected, **Then** the request is abandoned with a message,
   and no run starts.
4. **Given** a refused user, **When** they choose "Use a different account", **Then** they can
   try again with another Google account without reloading the page.
5. **Given** any refused or failed sign-in, **When** an operator checks afterwards, **Then** no
   language folder was created, wiped or modified, and no Drive file was created or changed.

---

### User Story 3 - Know who ran what (Priority: P2)

An operator reviewing past runs can see which Curious Learning account started each run.

**Why this priority**: Once several people share one web address, attribution is needed to answer
"who regenerated Hausa this morning?". It's lower priority than the access control itself.

**Independent Test**: Run a language as two different allowed accounts. Confirm each run's summary
and downloaded log name the account that started it.

**Acceptance Scenarios**:

1. **Given** a completed or failed run, **When** the user views it or downloads its log, **Then**
   the log records the signed-in account's email address and the start time.
2. **Given** a refused sign-in attempt, **When** an operator reviews the generator's records,
   **Then** the attempt is recorded with the refused account and the time. The refused user never
   sees any run content.

---

### Edge Cases

- **Account switching mid-session**: if the person signs out and back in as another allowed
  account, new runs are attributed to the new account.
- **Session expires while a run is in progress**: the run already in progress finishes. The next
  submission asks for sign-in again.
- **Curious Learning account without access to the language's Drive content**: sign-in succeeds.
  The run then stops at the existing Drive pre-check ("language not found"), before anything
  local is created or wiped (spec 001, FR-002). The message suggests asking for Drive access.
- **Outside account that has been given access to Curious Learning's Drive** (e.g. a `sutara.org`
  developer with shared access): refused by the generator anyway. Drive access doesn't replace the
  `curiouslearning.org` requirement.
- **Google's "unverified app" warning**: a non-Curious Learning user may click through it. The
  organization check after sign-in still refuses them (FR-003).
- **Several Google accounts in one browser**: the sign-in shows an account chooser. If the person
  picks a non-allowed account, User Story 2 applies, and they can retry with another account.
- **Email address that only looks like the organization's** (e.g. `someone@curiouslearning.org.example.com`
  or a Gmail address containing "curiouslearning"): refused. Only accounts the organization
  actually owns are accepted, not addresses that merely contain its name.
- **Previous runs list for a user who isn't signed in**: hidden. The run history and logs are
  shown only to signed-in, allowed users, because logs list Drive file names and IDs.
- **Another user's run in progress**: the existing one-run-at-a-time rule still applies after
  sign-in. The second allowed user is asked to try again later, and nothing is created for them.
- **Command-line use**: unchanged by this feature (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

**Sign-in gate**

- **FR-001**: The web page MUST require Google sign-in before starting any language run. A
  submission from someone who isn't signed in MUST trigger the sign-in before any other step.
- **FR-001a**: The language name entered before sign-in MUST be kept, so that after a successful
  sign-in the run for that language continues without retyping it. A pending request that isn't
  completed by a sign-in within 10 minutes MUST be discarded.
- **FR-001b**: Closing the browser tab, or abandoning the sign-in, MUST cancel the request or run.
  It MUST stop any work started for it and release the one-run-at-a-time lock within 5 seconds of
  the tab closing, or within 3 minutes for an abandoned sign-in. Nothing may be left running.
- **FR-002**: The system MUST allow a run only when the signed-in account belongs to the
  `curiouslearning.org` organization. Every other account MUST be refused, including other
  organizations such as `sutara.org` and personal Gmail accounts.
- **FR-003**: The system itself MUST perform the organization check after sign-in, based on the
  account's verified organization membership as reported by Google. It MUST NOT rely on a text
  match of the email address, and MUST NOT rely on Google's consent or "unverified app" screens
  to keep other accounts out.
- **FR-004**: When sign-in is refused, cancelled or fails, the system MUST abandon the request. It
  MUST create, wipe, download or modify nothing locally, and create or change nothing on Drive.
- **FR-005**: The page MUST show a clear message for each failure type: account not allowed,
  sign-in cancelled, or sign-in failed. For a refused account, it MUST offer to try another
  account.
- **FR-005a**: After a submission, authentication MUST be shown as its own stage before any
  automation step:
  1. "Authenticating…" while sign-in or the check is in progress.
  2. Then **either** an error, with no automation steps displayed and nothing run, **or**
     "Signed in as <email>".
  3. Only after success does the automation step list (spec 001, Steps 1–7) appear, and the run
     begin.
  A user who is already signed in in the session still sees a brief success confirmation before
  the steps.

**Session**

- **FR-006**: A successful sign-in MUST last for the browser session, so a signed-in user can
  start further runs without signing in again. It MUST end on sign-out or after a period of
  inactivity (default: 8 hours).
- **FR-007**: The page MUST show the signed-in account and provide a "Sign out" action.
- **FR-008**: The run history and run logs MUST be visible only to signed-in, allowed users.

**Drive access during a run**

- **FR-009**: The system MUST access Google Drive during a run with the signed-in person's own
  access, granted during their sign-in. It MUST NOT fall back to any other stored or shared Google
  access. One person's Drive access MUST NOT be used for another person's run.

**Attribution**

- **FR-010**: Every run's log and summary MUST record the email address of the account that
  started it.
- **FR-011**: The system MUST record every refused sign-in attempt with the account (if known) and
  the time, where operators can review it.

**Preserved behavior**

- **FR-012**: After sign-in succeeds, every behavior of the baseline pipeline (spec 001) MUST be
  unchanged. That includes the Drive pre-check before anything local is touched, the
  one-run-at-a-time rule, and the audio summary.

**Getting the output** *(amendment A4)*

- **FR-013**: After a run that completes (with or without errors), the signed-in user MUST be able
  to download that language's package as a single .zip file from the web page.

### Key Entities

- **Signed-in User**: a person who completed Google sign-in. They have an email address and an
  organization. Their status is allowed or refused.
- **Allowed Organization**: `curiouslearning.org`, the only Google organization whose accounts may
  generate languages.
- **Session**: one user's signed-in period in one browser. It has a start time, last activity and
  the signed-in account. It ends on sign-out or inactivity.
- **Run** *(extended from spec 001)*: now also records the account that started it.
- **Refused Attempt**: a record of a sign-in that was not allowed, with the account (if known) and
  the time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of language runs are started by a signed-in account from an allowed
  organization. Zero runs start without sign-in.
- **SC-002**: 0 local folders and 0 Drive files are created or changed as a result of a refused,
  cancelled or failed sign-in.
- **SC-003**: An allowed content team member can go from opening the web address to a started
  run in under 1 minute, including sign-in.
- **SC-004**: A refused user understands why within one screen. The message names the
  requirement, a Curious Learning account, and offers to switch account.
- **SC-005**: For every run, an operator can identify the account that started it within
  30 seconds of looking at the run or its log.
- **SC-006**: In 100% of submissions, the authentication result (success or error) is shown
  before any automation step appears. A failed authentication never shows the step list.

## Assumptions

- Curious Learning staff have Google accounts managed by the organization (Google Workspace), so
  Google can confirm their organization membership.
- The generator will be reachable at a shared web address for the content team. How and where it
  is hosted is a planning decision and a dependency of this feature, not part of this spec.
- Sign-in is per person. The one-run-at-a-time rule still applies across all users.
- Every content team member who generates languages has a `curiouslearning.org` account with read
  access to the language sheets and audio folders. Developers on other domains use the command
  line or a Curious Learning account.
- The Google sign-in configuration lives in Curious Learning's Google Cloud project. Changes to
  it, such as restricting it to the organization, are made by whoever manages that project for
  Curious Learning.
- An 8-hour inactivity timeout suits a working day and is the default unless changed.
- Command-line use of the pipeline on a developer's own machine is out of scope and stays as it is
  (it relies on that developer's own Google sign-in).
- Refused-attempt records are kept for operational review only, using standard retention. They
  contain only the email address and the time.
