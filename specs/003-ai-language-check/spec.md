# Feature Specification: AI Language Check of Sheet Content

**Feature Branch**: `003-ai-language-check` (spec folder only; no branch created)

**Created**: 2026-10-05

**Status**: Draft

**Input**: User description: "I want to implement gemini AI or claude ai api integration where I want AI to check the language entered and verify the excel and check if the given letters or words are proper. Lets say if entered text is hindi so check all letters and sounds from the excel if they are proper with the help of AI and give proper warnings if anything not related or proper. eg: word is kya in hindi and if the word given is kay in hindi then AI checks and let the content team know that the word is wrong and should be kya in hindi. This is just an example for hindi. User can enter any language name so it should be dynamic and should be checked. Add a UI of toggle to on and off this feature so only when kept on the AI will check the excel and give suggestion on wrong letter/sounds/or sentence from the selected language."

## Overview

Each Feed the Monster language comes from a sheet written by the content team. Each sheet holds:
- the **letters** children learn;
- the **words** used in puzzles;
- for each word, the letters that spell it;
- short **feedback sentences** ("Great!", "Amazing!");
- the names of the **audio recordings** for each letter and word.

A typo in any of these goes straight into the game. For example, the Hindi word क्या ("kya") might be typed as कया ("kay"). Nobody notices until a child or reviewer hears or sees it.

This feature adds an optional **AI language check**. When it's switched on, an AI language
service reviews the selected language's sheet content and reports items that look wrong for that
language. Each report says what was found, why it looks wrong, and the suggested correction. It
works for whatever language name the user enters, so there is no per-language setup.

## Clarifications

### Session 2026-10-05

- Q: Should the AI listen to the audio recordings? → A: **No. Only the text and the recording
  names are checked.** Listening to the recordings is out of scope.
- Q: When does the check run? → A: **Alongside the normal generation, as an extra report.** The
  run always completes, and the AI warnings appear in the results with the audio check.
- Q: Which AI service? → A: **Both are supported, and a configuration setting picks which one is
  used**: Google Gemini with a free-tier key, or Anthropic Claude with a paid key. Only one is
  used per run.
- Q (during implementation): How should API use be limited? → A: **Call the AI only once per check,
  keep token use low, and use Gemini by default.**
  - Each check is **one request** for the whole language. There is no batching, and nothing is
    retried.
  - If the language's content hasn't changed since its last check, the earlier result is reused
    and **no call** is made.

### Session 2026-10-06 (changes after implementation, requested by the user)

- Keys are in `.env` and settings are in `config.json` (FR-017).
- When Gemini is busy or a model isn't available, the check falls back through a list of models
  (FR-020 exception, FR-025).
- `temperature` and `max_output_tokens` are supported (FR-024).
- The AI output has its own log, and appears right after the unused-audio result (FR-012).
- The page's general flow is in spec 004.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get AI warnings about wrong letters, words and sentences (Priority: P1)

A content team member switches **AI language check** on, enters "Hindi", and presses Generate.
Besides the usual results, they get a list of suspected problems in the Hindi sheet. Each one
shows:
- where it is (level and puzzle, or feedback sentence);
- what the sheet says;
- the suggested correction;
- a short reason, e.g. *Level 12, word "कया": likely misspelling of "क्या" (kya, "what"). The
  vowel sign and conjunct are wrong.*

**Why this priority**: This is the core value: spelling and language mistakes are caught before the
language ships.

**Independent Test**: Use a copy of a sheet with three deliberate mistakes: a misspelled word, a
letter that doesn't belong to the language, and a broken feedback sentence. With the check on,
confirm all three are reported, each with a correction and a reason.

**Acceptance Scenarios**:

1. **Given** the check is on and the sheet has a misspelled word, **When** the user generates the
   language, **Then** the results list that word, where it is, the suggested spelling and a short
   reason.
2. **Given** the check is on and the sheet has a letter or character that isn't used in that
   language's writing system, **When** the user generates, **Then** that letter is reported as
   not belonging to the language.
3. **Given** the check is on and a feedback sentence is ungrammatical or isn't in the selected
   language, **When** the user generates, **Then** the sentence is reported with a suggested
   wording.
4. **Given** the check is on and the sheet has no problems, **When** the user generates,
   **Then** the results say the AI check found no issues.
5. **Given** any language name the user enters, e.g. "Hausa", "Marathi" or "IndianEnglish",
   **When** the check runs, **Then** it reviews the content against that language with no
   language-specific setup.

---

### User Story 2 - Switch the check on or off (Priority: P1)

The generator page has an **AI language check** toggle next to Generate. When it's off, Generate
behaves exactly as it does today: no content is sent anywhere, and no AI results appear. When it's
on, the check runs as part of that generation.

**Why this priority**: The user asked for it explicitly. It keeps cost, time and outside data
sharing under the team's control, and existing users see no change unless they opt in.

**Independent Test**: Generate the same language with the toggle off and then on. Confirm that the
off run is unchanged from today and contacts no AI service, and that the on run shows an AI check
section.

**Acceptance Scenarios**:

1. **Given** the toggle is off, **When** the user generates, **Then** no content is sent to any
   AI service, and the results look exactly as they do today.
2. **Given** the toggle is on, **When** the user generates, **Then** an "AI language check"
   section appears in the run's results.
3. **Given** the user switched the toggle on, **When** they generate again in the same session,
   **Then** it stays on until they switch it off.
4. **Given** a run is in progress, **When** the user looks at the toggle, **Then** it can't be
   changed until the run finishes, just like the Generate button.

---

### User Story 3 - Check that letters, words and recordings belong together (Priority: P2)

Besides spelling, the AI check reports items that don't fit together:
- a word whose letters don't actually spell it;
- a "letter in word" puzzle whose letter doesn't appear in the word;
- an audio recording whose name doesn't match the letter or word it's attached to, e.g. the word
  "kya" pointing at a recording named "kay".

**Why this priority**: These mistakes give the child the wrong sound or an impossible puzzle. It's
lower than US1 because it's about consistency, not language correctness.

**Independent Test**: Use a sheet where one word's letters are missing one letter, and one word
points at a recording with a different name. Confirm both are reported.

**Acceptance Scenarios**:

1. **Given** a word puzzle whose letters don't spell the word, **When** the check runs, **Then**
   it's reported with the word and the letters found.
2. **Given** a "letter in word" puzzle whose letter isn't in the word, **When** the check runs,
   **Then** it's reported.
3. **Given** a word whose recording name doesn't correspond to the word, **When** the check runs,
   **Then** it's reported, showing the word and the recording name.

---

### Edge Cases

- **The AI service can't be reached, isn't set up, or fails mid-check**: generation itself
  continues. The AI section says the check couldn't be completed and why, e.g. "AI check
  unavailable: no API key configured". The run is never silently reported as having no issues.
- **A language the AI knows little about** (a less widely used language or dialect): warnings are
  marked with the AI's confidence. If the AI can't judge the language reliably, it says so instead
  of guessing.
- **Language name isn't a real language name** (e.g. "IndianEnglish", "EnglishWestAfrican"): the
  check uses the name as given and states which language it assumed (e.g. "English, as used in
  India").
- **Very large sheets** (hundreds of words): every item is still checked, in the single request.
  Repeated items are sent once, so 750 puzzles become about 250 items. The check doesn't hold up
  the rest of the run by more than the limit in SC-003.
- **Same content checked again** (e.g. the user regenerates a language without changing the
  sheet): the earlier result is shown, and no call is made.
- **The same mistake repeated across many levels**: it's reported once, listing every place it
  appears.
- **Intentional non-words** (letter sounds, syllables used as phonics practice): these aren't
  flagged as misspelled words just because they aren't dictionary words.
- **Sign-in fails or the language isn't found on Drive**: no AI check runs. There's nothing to
  check.
- **The user says "No" to regenerating an existing language**: no AI check runs for that
  language.

## Requirements *(mandatory)*

### Functional Requirements

**Toggle**

- **FR-001**: The generator page MUST offer an **AI language check** on/off toggle, **off by
  default**.
- **FR-002**: When the toggle is off, the system MUST NOT send any content to an AI service, and
  generation MUST behave exactly as it does today.
- **FR-003**: The toggle MUST keep its setting for the rest of the browser session, and MUST be
  locked while a run is in progress.

**What is checked**

- **FR-004**: When the toggle is on, the system MUST check the selected language's sheet content:
  every letter, every word, every feedback sentence, and the names of the audio recordings linked
  to letters and words.
- **FR-005**: The check MUST work for any language name the user enters, with no per-language
  configuration. It MUST state which language it assumed the content is in.
- **FR-006**: The check MUST report:
  - (a) misspelled or malformed words;
  - (b) letters or characters that don't belong to the language's writing system;
  - (c) feedback sentences that are ungrammatical or not in the selected language;
  - (d) words whose letters don't spell them;
  - (e) "letter in word" puzzles whose letter isn't in the word;
  - (f) recordings whose names don't correspond to their letter or word.
- **FR-007**: The check MUST NOT flag letter sounds and syllables that are used on purpose as
  phonics items just because they aren't dictionary words.
- **FR-008**: The audio recordings themselves MUST NOT be sent to or analysed by the AI service.
  Only text and recording names are checked.

**Reporting**

- **FR-009**: Each warning MUST include where the item is (level and puzzle number, or "feedback
  sentence"), the text as written, the suggested correction, a short reason, and a confidence
  level (high, medium or low).
- **FR-010**: Identical problems appearing in several places MUST be grouped into one warning
  that lists every place.
- **FR-011**: The results MUST show an "AI language check" section with the number of warnings,
  sorted by confidence (high first). If nothing was found, it MUST explicitly say "No issues
  found".
- **FR-012** *(revised 2026-10-06)*: The AI check's output and warnings MUST be kept in **their own
  log**, separate from the pipeline log, with their own "Download AI log" button, so they can be
  shared with whoever maintains the sheet. Nothing from the AI check appears among the pipeline
  steps. While it runs, only the run's title says "AI language check in progress". The AI section
  appears **right after the unused-audio result** in the run's summary.
- **FR-013**: The check MUST only report. It MUST NOT change the sheet, the generated content or
  any audio file.

**When it runs, and failures**

- **FR-014**: The check MUST run alongside the normal generation, once the language's content is
  available. It MUST NOT pause the run or ask the user anything, and MUST NOT stop the normal
  steps. Its results appear as an extra report next to the audio check.
- **FR-015**: If the AI check can't be completed (service unavailable, not configured, or an
  error), the run MUST still finish its normal steps. The AI section MUST say the check didn't
  complete, and why.
- **FR-016**: The system MUST support two AI services, Google Gemini (free-tier key) and Anthropic
  Claude (paid key). A configuration setting MUST choose which one is used. Only one is used per
  run.
- **FR-017** *(revised 2026-10-06)*: Settings and secrets MUST be kept apart.
  - A committed settings file (`config.json`) chooses the service, and each service's model and
    options.
  - API keys live only in an uncommitted keys file (`.env`), with a committed template that has no
    real keys (`.env.example`), or in real environment variables, which take priority.
  - A key placed in the settings file MUST be ignored.
- **FR-018**: The AI section of the results MUST name the service that was used. If the
  configured service has no key, the section MUST say "AI check unavailable: no API key
  configured for <service>". The other service MUST NOT be used silently in its place.
- **FR-019**: If the service refuses the request (usage or rate limits, expected on the free Gemini
  tier) or fails, the check MUST report that the AI part didn't run, and why, e.g. "AI check
  unavailable: Gemini rate limit reached". It MUST NOT report the content as having no issues, and
  MUST NOT retry automatically.
- **FR-020**: A check MUST make **at most one** request to the AI service. That request contains
  every item of the language.
  - *Exception (revised 2026-10-06):* if a model answers "busy" (server overload) or "not
    available for this key", then nothing was generated and no tokens were used. The check MAY then
    try the next model from an optional, user-configured list of fallback models, each at most
    once.
  - Any other failure (rate limit, invalid key) stops at once.
  - With an empty list, exactly one request is made.
  - The report MUST name the model that answered, and quote the service's own reason for each
    model that didn't.
- **FR-024** *(added 2026-10-06)*: The settings file MAY set the Gemini model's `temperature` and
  `max_output_tokens`, which are only sent when set. If the answer is cut off by
  `max_output_tokens`, the check MUST say so, and suggest raising it, rather than report an
  unreadable answer.
- **FR-025** *(added 2026-10-06)*: The check MUST offer a no-cost way to list the models the
  configured key can use (`--list-models`), to choose valid names for the settings file.
- **FR-021**: If the language's checkable content is identical to a previous successful check
  (same language, same items, same service and model), the system MUST reuse that result instead
  of calling the service. The results MUST say "From earlier check on <date>: content unchanged".
- **FR-022**: The request MUST send only what the check needs: each unique item once with its ID,
  recording names only where they differ from the item's text, and a short fixed instruction. Long
  explanations MUST NOT be requested; each reason is one short sentence.
- **FR-023**: The default service MUST be Gemini.

### Key Entities

- **Content Item**: one checkable piece of a language's content: a letter, a word (with its
  letters), a "letter in word" pair, a feedback sentence, or a recording name. It has a location:
  level number and puzzle number, or "feedback sentence N".
- **AI Warning**: a suspected problem. It has a category (FR-006 a–f), the text as written, a
  suggested correction, a reason, a confidence level, and one or more locations.
- **AI Check Result**: the outcome for one run. It records:
  - the AI service used and the language assumed;
  - the status: completed, partly completed with a reason, not completed with a reason, or
    turned off;
  - the number of items checked out of the total;
  - the list of AI Warnings.
- **AI Configuration**: which service to use (Gemini or Claude) and the API key for each. It's
  kept outside the repository.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a test sheet with known mistakes, at least 90% of the planted misspellings,
  foreign letters and broken sentences are reported, with the correct fix suggested.
- **SC-002**: On a sheet reviewed and confirmed correct by a native speaker, no more than 5% of
  items are flagged (false alarms).
- **SC-003**: With the check on, a language with about 150 levels gets its AI results within
  5 minutes of the content being available, and the check adds no more than 5 minutes to the
  whole run.
- **SC-004**: With the check off, run time and results are unchanged from today, and no content
  leaves the organization's systems for an AI service.
- **SC-005**: A content team member can find and act on every warning from the results page
  alone. Each warning shows where to look and what to change, with no need to open the log.
- **SC-006**: The check works without code changes for any language the team adds, including at
  least Hindi, Marathi, Hausa and an English variant in acceptance testing.

## Assumptions

- The sheet content checked is the same content the game uses: letters, words, word spellings,
  feedback sentences and recording names. The AI judges that content. It doesn't replace native
  speaker review; it highlights what to look at first.
- The check is advisory only. The content team fixes the sheet and regenerates.
- Sending the sheet's word lists and sentences to an outside AI service is acceptable. It's
  educational vocabulary with no personal data, and no audio is sent (FR-008). On a free tier the
  provider's terms may allow it to use the submitted content to improve its products. That is
  acceptable for this content, but it is why the paid option is offered.
- The free Gemini tier has usage limits. Because each check is one request and unchanged content
  is never re-sent, hitting them should be rare. When it happens, the check reports "unavailable"
  (FR-019), and the team can try again later or switch to the paid service.
- Curious Learning provides the API key(s): a free Gemini key, a paid Anthropic key, or both. The
  paid service's cost per language checked is estimated during planning.
- The toggle's default is off, so existing users see no change unless they switch it on.
- The generator keeps using the existing Google sign-in. This feature adds no separate login.
