# Feature Specification: Per-Person Web Google Sign-In for the Generator

**Feature Branch**: `005-web-google-signin` (spec folder only; no branch created)

**Created**: 2026-10-09

**Status**: Draft

**Input**: User description: "Option B from the authentication flow implement it make sure only curiouslearning.org email id has right to go ahead to add a language"

## Clarifications

### Session 2026-10-09

- Q: Should this feature also include hosting, or only the sign-in change? → A (first answer):
  include hosting. **Superseded the same day**: "I don't want the hosting implementation in this
  spec, I will handle it separately." This feature is **sign-in only**. Hosting (server setup,
  deployment instructions, package download for a temporary server) is out of scope; see
  [Out of Scope](#out-of-scope).
- Q: Who creates the web sign-in configuration, and in which Google Cloud project? → A: In a
  **separate, dedicated Google Cloud project** for the generator, not `ftm-b9d99` (the project
  that issued the existing command-line `credentials.json`). The Drive and Sheets APIs must be
  enabled in it.
- Q: Which account creates that project, and is it inside the curiouslearning.org Google
  Workspace organisation? → A: The developer creates it with their **own `curiouslearning.org`
  account**, so it sits inside the organisation, and grants themselves **Owner**. The sign-in
  configuration's audience is therefore **Internal** (curiouslearning.org accounts only).

> **Context.** "Option B" is the deployment discussion's choice for making Google sign-in work
> when the generator runs on a shared server rather than on the person's own computer. Today the
> sign-in works only on the machine running the page:
>
> - **Sign-in breaks on a server**: Google sends the person back to their own computer, where
>   nothing is waiting, so sign-in never finishes.
> - **One shared Google access**: everyone uses a single saved sign-in. After one person signs
>   in, the next person runs with the first person's Drive access, so the "Curious Learning only"
>   check no longer applies to them.
>
> Option B keeps the current experience: the Google sign-in starts when Generate is pressed, and
> there is no separate login page. What changes is that the sign-in works from any browser and
> belongs to each person's own page session. This makes the generator ready to be hosted. The
> hosting itself is handled separately.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Curious Learning person signs in and adds a language (Priority: P1)

A content team member opens the generator's web address, types a language and presses Generate.
The run's box shows "Authentication in progress" and a Google sign-in link. They sign in with
their `@curiouslearning.org` account. The box shows "Authenticated as <email>", and the run for
the language they typed continues on its own, exactly as it does today. Further languages started
from the same page don't ask them to sign in again.

**Why this priority**: Without it, the generator can't be used from a shared web address at all.

**Independent Test**: Run the generator locally. Generate "Hausa" and sign in with a Curious
Learning account. Confirm the run completes. Then generate a second language from the same page
and confirm no second sign-in is asked for.

**Acceptance Scenarios**:

1. **Given** a person whose page session isn't signed in, **When** they press Generate, **Then**
   the box shows only "Authentication in progress" and a sign-in link. No steps or log are shown.
2. **Given** the person completes Google sign-in with a `@curiouslearning.org` account, **When**
   they return to the generator page, **Then** it shows "Authenticated as <email>", and the run
   for the language they typed starts without retyping it.
3. **Given** a signed-in page session, **When** the person generates another language, **Then**
   the run starts without a new sign-in. The box still shows "Authenticated as <email>" before the
   steps.
4. **Given** the sign-in, **When** it completes, **Then** it finishes in the person's own browser
   and depends only on the generator's registered web address. Nothing waits for input on the
   machine running the generator.

---

### User Story 2 - Only curiouslearning.org accounts may add a language (Priority: P1)

Someone signs in with a personal Gmail account, another organization's account (including
`sutara.org`), or an account that has merely been given access to Curious Learning's Drive. The
box shows "Authentication failed" with a message that only Curious Learning
(`curiouslearning.org`) accounts can add languages. No step runs. Nothing is created, wiped,
downloaded or changed, locally or on Drive. They can try again with a different Google account.

**Why this priority**: This is the user's explicit requirement. Only Curious Learning staff may
publish languages.

**Independent Test**: Generate a language and sign in with a personal Gmail account. Confirm the
refusal message, confirm no steps appear, and confirm the local language folder and Drive are
unchanged. Repeat with a `sutara.org` account.

**Acceptance Scenarios**:

1. **Given** a person signs in with any account that isn't `@curiouslearning.org`, **When** sign-in
   completes, **Then** the box shows "Authentication failed", saying only Curious Learning
   accounts can add languages. No steps appear, and no run starts.
2. **Given** an address that only looks like the organization's (e.g.
   `someone@curiouslearning.org.example.com`, or a Gmail address containing "curiouslearning"),
   **When** sign-in completes, **Then** it is refused.
3. **Given** a refused person, **When** they press Generate again, **Then** Google lets them
   choose a different account, without reloading the page.
4. **Given** any refused, cancelled or failed sign-in, **When** an operator checks afterwards,
   **Then** no language folder was created, wiped or changed, and no Drive file was created or
   changed.

---

### User Story 3 - Each person's run uses only their own Google access (Priority: P1)

Two content team members use the generator at different times, or from different browsers. Each
run reads Drive with the access of the person who started it. Nobody's sign-in is saved where
another person's run can pick it up.

**Why this priority**: Without this, the curiouslearning.org check could be bypassed by using
someone else's saved sign-in, which is the flaw this feature exists to remove.

**Independent Test**: Person A signs in and runs a language. In a different browser, person B
opens the page and presses Generate. Confirm B is asked to sign in, and that B's run shows B's
email, not A's.

**Acceptance Scenarios**:

1. **Given** person A signed in from their browser, **When** person B opens the generator in
   another browser and presses Generate, **Then** B is asked to sign in, and B's run never uses
   A's access.
2. **Given** a person closes or reloads their tab, **When** the page is opened again, **Then** the
   previous sign-in is not reused automatically. Pressing Generate asks Google again; Google may
   reduce this to a single click on an account it already knows.
3. **Given** the generator restarts, **When** anyone presses Generate, **Then** they sign in
   again. No earlier sign-in survives the restart.

---

### Edge Cases

- **Sign-in abandoned or the sign-in tab closed**: after 3 minutes without a completed sign-in,
  the request is cancelled and the generator is free again (same as today). Nothing is created.
- **Generator tab closed during sign-in or during a run**: the run is cancelled and the one-run
  lock released (same as today).
- **Two people press Generate at once**: the one-run-at-a-time rule still applies. The second
  person's form stays disabled until the first run ends. Each signs in for their own run.
- **Sign-in completes in a different browser from the one that pressed Generate** (e.g. the link
  is pasted elsewhere): the sign-in only counts for the page session that requested it, and only
  once. A copied or reused sign-in link is rejected.
- **Google access expires during a long run**: the run keeps working until it finishes, without
  asking the person to sign in again.
- **Curious Learning account without access to a language's Drive content**: sign-in succeeds.
  The run then stops at the existing Drive check ("language not found") before anything local is
  touched.
- **Sign-in settings missing**: the generator refuses to run anything and shows a setup error. It
  never falls back to a shared or saved sign-in ("fails closed").
- **Google's "unverified app" warning**: clicking through it doesn't help an outside account. The
  generator's own check still refuses it.
- **Command-line use**: `python generate_language.py <Language>` on a developer's own computer
  keeps its current sign-in, with the same curiouslearning.org check.

## Requirements *(mandatory)*

### Functional Requirements

**Sign-in from any browser**

- **FR-001**: Pressing Generate in a page session that isn't signed in MUST start a Google
  sign-in. That sign-in MUST complete in the person's own browser, wherever the generator runs.
- **FR-002**: The language typed before sign-in MUST be kept. After a successful sign-in, the run
  for that language MUST continue without retyping.
- **FR-003**: Each sign-in request MUST be tied to the page session that started it, and usable
  once only. A sign-in completed for one session MUST NOT grant access to any other session.

**Curious Learning only**

- **FR-004**: A run MUST proceed only when the signed-in account belongs to `curiouslearning.org`,
  as confirmed by Google. Google must confirm both the verified email address and the
  organization that manages the account. Every other account MUST be refused, including
  `sutara.org`, personal Gmail, and look-alike addresses.
- **FR-005**: The check MUST be made by the generator after every sign-in. It MUST NOT rely on
  Google's consent or "unverified app" screens.
- **FR-006**: A refused, cancelled or failed sign-in MUST stop the request before Step 0. Nothing
  may be created, wiped, downloaded or changed locally or on Drive. The box MUST show
  "Authentication failed" with the reason ("only Curious Learning (curiouslearning.org) accounts
  can add languages", "sign-in was cancelled or didn't complete", or "sign-in failed").
- **FR-007**: After a refusal, the next Generate MUST let the person choose a different Google
  account.

**Per-person access**

- **FR-008**: Each run MUST read Drive and Sheets with the Google access of the person who
  started it, and with no other stored or shared Google access.
- **FR-009**: The generator MUST NOT write a person's sign-in anywhere another person's session
  could use it. A sign-in lasts only for the page session that made it, ending when the tab is
  closed or reloaded, or when the generator restarts.
- **FR-010**: Within a signed-in page session, further runs MUST NOT ask for sign-in again. Each
  run MUST still show "Authenticated as <email>" before its steps.
- **FR-011**: If the generator's sign-in settings are missing or invalid, it MUST refuse every run
  with a setup error. It MUST NOT fall back to any saved or shared sign-in.

**Preserved behaviour**

- **FR-012**: The page flow of spec 004 MUST be unchanged:
  - "Authentication in progress" first, with the sign-in link.
  - Steps and log only after "Authenticated as".
  - "Authentication failed" with no steps.
  - One click per run.
  - The cancel-on-tab-close and 3-minute sign-in timeout.
  - The regenerate prompt and "Add another language".
- **FR-013**: Every behaviour of the pipeline (spec 001), including the Drive check before
  anything local is touched, and of the optional AI check (spec 003) MUST be unchanged after
  sign-in.
- **FR-014**: Command-line use on a developer's own computer MUST keep working with its current
  sign-in and the same curiouslearning.org check.
- **FR-015**: Every run's log MUST record the email of the account that started it, as the
  "Authenticated as <email>" line does today.
- **FR-016**: The web sign-in configuration (its client secret) MUST come from a local untracked
  file or the environment, never from the repository.

### Key Entities

- **Page session**: one browser tab's visit to the generator. It holds that person's sign-in, if
  any, and its runs. It ends when the tab closes or reloads, or when the generator restarts.
- **Sign-in request**: started by Generate in one page session. It is single-use and expires
  after 3 minutes. It ends as success, refused, cancelled or failed.
- **Signed-in person**: email address, verified status, and managing organization as reported by
  Google. Allowed only for `curiouslearning.org`.
- **Run** *(from specs 001/004)*: also records the email of the person who started it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A Curious Learning team member can go from pressing Generate to a started run in
  under 1 minute, including sign-in.
- **SC-002**: 100% of runs are started by an `@curiouslearning.org` account. 0 runs start for any
  other account, in tests covering personal Gmail, `sutara.org` and look-alike addresses.
- **SC-003**: 0 local folders and 0 Drive files are created or changed by a refused, cancelled or
  failed sign-in.
- **SC-004**: In a two-person test, 0 runs use the other person's Google access, and each run's
  log names the person who started it.
- **SC-005**: A refused person understands why, and how to retry with another account, from the
  single message shown.
- **SC-006**: No sign-in survives a closed tab or a restart of the generator. The next Generate
  always asks Google.

## Out of Scope

Handled separately by the user. This feature makes no change for any of these:

- **Hosting**: server or container setup, scale-to-zero settings, secret storage on a cloud
  host, and deployment or update instructions.
- **Getting output off a temporary server**: for example a .zip download of the language package.
  Today the files stay in `lang/<language>/` on the machine running the generator.
- **Registering the hosted address**: adding a hosted web address to the sign-in configuration.
  This feature only requires that the address the generator runs at is registered.

## Assumptions

- Curious Learning staff have Google Workspace accounts managed by `curiouslearning.org`, so
  Google can confirm the managing organization.
- A web-type Google sign-in configuration is set up in a **dedicated Google Cloud project for
  the generator** (separate from `ftm-b9d99`, which keeps the command-line desktop client). The
  developer creates that project with their `curiouslearning.org` account, so it belongs to the
  curiouslearning.org organisation, and is its Owner. The Drive and Sheets APIs are enabled in
  it. It lists the generator's web address (`localhost` for local use, and later the hosted
  address) as allowed return addresses. Its secret is kept outside the repository.
- That sign-in configuration's audience is set to **Internal** (curiouslearning.org accounts
  only). This is an extra layer on Google's side; the generator's own check (FR-004) is required
  whatever that setting is. Because the app is Internal, Google doesn't review the Drive
  permission, and sign-ins aren't limited to a tester list or a 7-day expiry.
- The developer's own `curiouslearning.org` account is one of the allowed test accounts
  (quickstart "account A").
- Each person's sign-in asks for the same Drive and Sheets access the pipeline uses today.
- Signing in once per page session is acceptable. Google's own "remember this account" makes
  repeat sign-ins a single click.
- The one-run-at-a-time rule, one shared generator instance and all existing log prefixes stay
  as they are.
- Developers outside `curiouslearning.org` (e.g. `sutara.org`) are refused by the web
  generator. They use a Curious Learning account to test it, or the command line.
