# Feature Specification: AI Token Usage and Model per Check

**Feature Branch**: `006-ai-token-usage` (spec folder only; no branch created)

**Created**: 2026-10-14

**Status**: Implemented (manual verification against a real language pending, see tasks.md T012)

**Input**: User description: "Update my code so that every language generation can show me the input token and output token generated. Right now, I think we have the output token. If not, add both input and output tokens. After a language generation is completed, I should see the input and output tokens and also the model name used. Accordingly, I can compare both for the costing." Follow-up: "Give a toggle to show token used under AI check toggle."

## Overview

The AI language check (spec 003) sends one request per language to Gemini or Claude. The team
hasn't decided which provider to use yet. To compare their cost, they need the **real** token counts of
each request and the **model that actually answered**.

Before this feature the page showed only an estimate made before the call (`~N tokens`: characters
÷ 4). The API's real usage was read and then thrown away, and no input/output split was shown.

This feature records the real input and output tokens and the model of every AI check. It shows
them after the run when a new **🔢 Show tokens used** toggle, placed under the AI language check
toggle, is on.

## Clarifications

### Session 2026-10-14

- Q: Where do the AI tokens come from in a generation? → A: **Only the AI language check calls
  an AI.** The pipeline itself (sheet, JSON, audio) uses none. Tokens therefore exist only for runs
  with the AI check on.
- Q: How is thinking counted? → A: **As output.** Both providers bill thinking at the output rate.
  Gemini reports it separately, so it's also shown as "incl. N thinking". Claude includes it in
  `output_tokens` without a split.
- Q: Which model is shown? → A: **The model that answered**, not just the configured one. A
  Gemini `fallback_models` entry or a Claude server-side fallback may answer instead. A dated id
  of the configured alias (e.g. `claude-x-YYYYMMDD`) counts as the configured model.
- Q: What about cached checks (unchanged content, no API call)? → A: **This run used 0 tokens.**
  The page shows the counts of the earlier request that produced the cached result. Cache entries
  written before this feature have no counts and say so.
- Q: Toggle default? → A: **Off.** It only controls what the page shows. Counts are always
  recorded in the report and the AI log.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the real tokens and model of an AI check (Priority: P1)

A team member switches on **🤖 AI language check** and **🔢 Show tokens used**, enters "Hindi" and
presses Generate. When the run finishes, the AI language check section shows one line under its
heading, for example:

> **Model:** `gemini-2.5-flash-lite` · **Input tokens:** 1,500 · **Output tokens:** 700 (incl. 300 thinking) · **Total:** 2,200

**Why this priority**: This is the whole point: the team can price one check per provider and model.

**Independent Test**: Run one language with Gemini, then switch `config.json` to Claude and run it
again. Both runs show model, input and output tokens. The numbers match the providers' own usage
consoles.

**Acceptance Scenarios**:

1. **Given** both toggles are on and the AI answered, **When** the run completes, **Then** the
   section shows the answering model, input tokens, output tokens and total.
2. **Given** Gemini answered with thinking, **When** the section is shown, **Then** output tokens
   include thinking and the line says "incl. N thinking".
3. **Given** a fallback model answered, **When** the section is shown, **Then** the line names the
   fallback model.
4. **Given** the AI answered but the answer couldn't be used (cut off, refused or unreadable),
   **When** the check reports "unavailable", **Then** the tokens that were billed are still shown.

### User Story 2 - Choose whether tokens are shown (Priority: P2)

The token line is useful for the person comparing costs, but it's noise for content reviewers. A
toggle under the AI check switches it on or off.

**Independent Test**: With the AI check on, switch "Show tokens used" on and off. The line appears
and disappears for the latest run and earlier runs on the page, without a new AI request.

**Acceptance Scenarios**:

1. **Given** the AI check toggle is off, **Then** "Show tokens used" isn't shown.
2. **Given** the AI check toggle is on, **Then** "Show tokens used" appears directly under it,
   indented, and is off the first time.
3. **Given** "Show tokens used" was switched on, **When** the AI check is switched off and on
   again, **Then** "Show tokens used" is still on.
4. **Given** a run is in progress, **Then** the toggle is disabled, like the AI check toggle.

### User Story 3 - Keep a record in the AI log (Priority: P3)

Every AI check writes `🤖 AI check: <model>, tokens: input N, output N, total N` to its AI log,
whatever the toggle says. The downloaded AI log is a cost record. The command line prints the same.

### Edge Cases

- **Cached result:** "tokens used this run: 0 (cached)" plus the earlier request's counts. If the
  cache entry predates this feature: "token counts weren't recorded then".
- **No API call at all** (not configured, bad key, 429, all Gemini models busy/404): no token line
  in the log. If shown, the page says "no tokens used".
- **API returns no usage:** "not reported by the API".
- **Claude prompt caching:** cache reads and writes are counted in input tokens (and kept apart in
  the report) so input tokens are never under-counted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every AI check that got an answer from the AI MUST record the real `input_tokens`
  and `output_tokens` reported by the API, in the same shape for Gemini and Claude.
- **FR-002**: `output_tokens` MUST include thinking tokens. When the provider reports thinking
  separately, `thinking_tokens` MUST also be recorded.
- **FR-003**: The check MUST record the model that actually answered (FR-025 of spec 003 fallbacks
  and Claude server-side fallbacks included).
- **FR-004**: The usage MUST be stored with the cached result so a cached check can show the
  earlier request's counts, while stating that the run used 0 tokens.
- **FR-005**: An answer that was billed but not usable MUST still report its usage.
- **FR-006**: The check MUST write one token line to its progress output (and so to the AI log and
  the command line) after each AI answer or cache reuse.
- **FR-007**: The page MUST offer a **🔢 Show tokens used** toggle, shown only under the AI
  language check toggle when it is on, off by default, disabled while busy. Its choice MUST
  survive switching the AI check off and on within the page session.
- **FR-008**: When the toggle is on, every AI language check section on the page MUST show model,
  input tokens, output tokens (with thinking when known) and total. When it's off, none is shown.
- **FR-009**: The toggle MUST NOT cause any AI request and MUST NOT change what is recorded.
- **FR-010**: Existing output contracts stay as they are: the token line uses the `🤖 AI check:`
  prefix and never `❌` (constitution IV, spec 003 contract).

### Key Entities

- **Token Usage** (`result["usage"]` in the AI report and `usage` in the cache entry):
  `input_tokens`, `output_tokens`, `thinking_tokens` (int or null), `cache_read_tokens`,
  `cache_write_tokens`. Null when no answer was received.
- **AI Check Result** (spec 003): gains `usage`. `model` is the answering model.
- **Page session state**: `show_tokens` (bool, default false), mirrored from the toggle
  `show_tokens_toggle`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For 100% of AI checks that received an answer, the AI log contains the model and
  real input/output tokens.
- **SC-002**: With the toggle on, the counts are visible on the page within the run's results, with
  no extra click.
- **SC-003**: The shown counts equal the usage the provider reports for the same request.
- **SC-004**: Switching the toggle makes no AI request (0 extra tokens).

## Assumptions

- Cost is computed by the user from the counts and each provider's current price list. Prices
  aren't built in because they change.
- Only the AI language check uses tokens. If another AI step is added later, it should report
  usage the same way.
