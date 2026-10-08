---
description: "Task list for 003 – AI Language Check of Sheet Content"
---

# Tasks: AI Language Check of Sheet Content

> **Revision 2026-10-05 (user, during implement)**: one API call per check, no retries, a result
> cache for unchanged content, fewer tokens, and Gemini by default (spec FR-019–FR-023, research
> R2-rev). That changes some tasks:
> - **T006**: the config has no `batch_size` or `seconds_between_requests`, and `claude.effort`
>   defaults to `low`.
> - **T009 and T010**: no retries (`max_retries=0`, no 429 retry). Any failure raises
>   `Unavailable(reason)`.
> - **T011**: one request with all items, plus the `.ai_cache/` lookup and save. There's no
>   `partial` status.
> - **T013**: V7 checks "unavailable, no retry" instead of "partial".
> - **T002**: also gitignore `language_automation/.ai_cache/`.

**Input**: Design documents from `specs/003-ai-language-check/`. These are plan.md, spec.md,
research.md (R1–R9), data-model.md, contracts/ai-output.schema.json,
contracts/ai-check-cli-and-ui.md and quickstart.md.

**Tests**: The spec doesn't ask for automated tests, and the repo has no suite (constitution).
Each story ends with a **manual verification** task from [quickstart.md](quickstart.md). The
offline parts (items, consistency checks, config, grouping) are checked against the local
`lang/indianenglish/ftm_indianenglish.json` without any API key.

**Paths**: everything is in `language_automation/` and runs from that folder. The pipeline
scripts (`generate_language.py`, the `fetch_*` scripts and the `check_*` scripts) are **not**
modified.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 [P] Add `anthropic` and `google-genai` to `requirements.txt`, pinned to the versions
  `python -m pip install anthropic google-genai` resolves. Add a comment that only the provider
  selected in `ai_config.toml` is imported. Install them.
- [X] T002 [P] Add `language_automation/ai_config.toml` to `.gitignore`, under the "Secrets"
  block.
- [X] T003 [P] Create `language_automation/ai_config.example.toml` exactly as the TOML block in
  [contracts/ai-check-cli-and-ui.md](contracts/ai-check-cli-and-ui.md) → Configuration, with
  empty `api_key` values.
- [X] T004 [P] Copy [contracts/ai-output.schema.json](contracts/ai-output.schema.json) to
  `language_automation/ai_output_schema.json`. This is the runtime copy that both providers
  receive.

---

## Phase 2: Foundational (blocking prerequisites)

**⚠️ No user story can start until this phase is complete.**

- [X] T005 Create `language_automation/ai_language_check.py` with `build_items(lang)`:
  - Load `lang_paths.json_path(lang)`. If the file is missing, raise `FileNotFoundError` with a
    clear message.
  - Produce Content Items per [data-model.md](data-model.md):
    - `id` is `"i1"`, `"i2"`, …;
    - `kind` is one of `LetterOnly | LetterInWord | Word | Feedback`;
    - `text` is NFC-normalized;
    - `letters` comes from `targetstones[].StoneText`;
    - `recording` is the basename of `PromptAudio`;
    - `locations` is a list of `"level L puzzle P"` (`LevelMeta.LevelNumber`, `SegmentNumber`),
      or `"feedback n"` for `FeedbackTexts`.
  - De-duplicate on the key `(kind, text, letters, recording)`, merging locations.
  - Add `format_item_line(item)`, which returns `"<id> | <kind> | <text> | <letters joined by +> |
    <recording>"`.
- [X] T006 [P] Create `language_automation/ai_providers.py` with `load_config()`:
  - Read `ai_config.toml` with `tomllib`. If the file is missing, use the defaults.
  - Apply the defaults in [data-model.md](data-model.md) → AI Configuration: `provider` defaults
    to `"gemini"`, `batch_size` to 80 (clamped to 10–200), `gemini.model` to
    `"gemini-flash-latest"`, `gemini.seconds_between_requests` to 5 (0–60), `claude.model` to
    `"claude-opus-5-5"`, and `claude.effort` to `"high"` (one of `low|medium|high|xhigh|max`).
  - Environment variables `GEMINI_API_KEY` and `ANTHROPIC_API_KEY` override the file's keys.
  - Return `(config, unavailable_reason_or_None)`, using the exact messages from the contract's
    "Situation" table:
    - no key: `"no API key configured for <provider>"`;
    - unknown provider: `"unknown provider '<x>' in ai_config.toml"`.
  - Never print a key.
- [X] T007 Offline check: `python -c "import ai_language_check as a; it=a.build_items('IndianEnglish'); print(len(it))"`
  should print **252** (research R1). Also print three item lines, and check that every location
  of `a` from the R1 sample (`0.0,0.2,2.2,3.3,49.0`) is present. (Depends on T005.)

**Checkpoint**: items and config are working without any API key.

---

## Phase 3: User Story 1 – AI warnings about wrong letters, words and sentences (P1) 🎯 MVP

**Goal**: `python ai_language_check.py <Language>` prints progress and a final `🤖 AI report:`
with grouped, located warnings from the configured service.

**Independent Test**: quickstart V3, V5, V6, V7 and V8 from the command line.

- [X] T008 [US1] In `language_automation/ai_providers.py`, add the fixed system prompt
  `REVIEW_PROMPT` (research R9). It must cover:
  - categories `misspelled_word`, `foreign_letter`, `bad_sentence` and `recording_mismatch`, each
    with a one-line definition;
  - "letter sounds and syllables used as phonics items are intentional, so don't flag them as
    misspellings" (FR-007);
  - the recording rule: "LetterOnly and LetterInWord puzzles play the target letter's recording;
    Word puzzles play the word's recording";
  - the confidence rubric;
  - "if you cannot judge this language reliably, set can_judge=false and explain in note; do not
    guess";
  - "report only problems; an empty warnings list is valid";
  - "use only item ids from the input".
- [X] T009 [US1] Add `ClaudeReviewer(config)` to `language_automation/ai_providers.py`, with
  `.review(language, item_lines) -> dict`:
  - `import anthropic` lazily inside `__init__`. On `ImportError`, become unavailable with "install
    anthropic (pip install -r requirements.txt)".
  - Create `anthropic.Anthropic(api_key=...)`.
  - Call `client.beta.messages.create(model=cfg.model, max_tokens=16000, system=REVIEW_PROMPT,
    messages=[{"role":"user","content": f"Language entered: {language}\n" + item_lines}],
    output_config={"effort": cfg.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
    betas=["server-side-fallback-2026-07-01"], fallbacks="default")`.
  - Check `stop_reason` before reading the content:
    - `"refusal"`: raise `BatchFailed("declined by Claude")`;
    - `"max_tokens"`: raise `BatchFailed("response too long")`;
    - otherwise `json.loads` the first `text` block.
  - Errors: `anthropic.RateLimitError` → `RateLimited`; `AuthenticationError` → `Unavailable("API
    key rejected")`; `APIConnectionError` → `BatchFailed("Claude unreachable")`; other
    `APIStatusError` → `BatchFailed`.
  - **Verify** that `output_config.format` works together with `fallbacks`. If the API rejects the
    combination (400), remove `betas` and `fallbacks`, and note it in research.md R5.
- [X] T010 [US1] Add `GeminiReviewer(config)` to `language_automation/ai_providers.py`, with the
  same `.review` signature:
  - `from google import genai` lazily, with the same unavailable message for `google-genai`.
  - Create `genai.Client(api_key=...)`.
  - Call `client.models.generate_content(model=cfg.model, contents=f"Language entered:
    {language}\n" + item_lines, config={"system_instruction": REVIEW_PROMPT, "response_mime_type":
    "application/json", "response_json_schema": SCHEMA})`, then `json.loads(response.text)`.
  - On `google.genai.errors.APIError` with `.code == 429`: sleep 30 s, retry once, then raise
    `RateLimited`. A 401 or 403 raises `Unavailable("API key rejected")`. Anything else raises
    `BatchFailed`.
- [X] T011 [US1] In `language_automation/ai_language_check.py`, add `check_language(lang,
  progress=print) -> dict`, which returns the AI Check Result:
  1. `load_config()`. If it's unavailable, return `status="unavailable"` with the reason.
  2. Build the items and split them into batches of `batch_size`.
  3. For each batch, call the selected reviewer. Only the selected one: never the other provider
     (FR-018). For Gemini, sleep `seconds_between_requests` between batches.
  4. Drop any `item_ids` that aren't in the batch, and expand ids into `locations`.
  5. Merge identical `(category, text, suggestion)` warnings, combining their locations
     (FR-010).
  6. Sort by confidence (high, medium, low), then by first location.
  7. Set the status per the data-model transitions:
     - `completed`;
     - `partial`, with `items_checked < items_total` and a reason such as `"Gemini rate limit
       reached"`;
     - `failed`, when the first batch fails;
     - `cannot_judge`, when `can_judge` is false (keep its warnings, set to `low`).

  Take `assumed_language` from the first successful batch.
- [X] T012 [US1] Add a `__main__` entry point to `language_automation/ai_language_check.py`:
  - Validate the name with `lang_paths.validate_language_name`. If it's invalid, print `❌ Invalid
    language name…` and exit 1. If the JSON is missing, print `❌ No generated game JSON for
    <lang>: run generate_language.py first` and exit 1.
  - Print the contract's progress lines: `🤖 AI check: using <provider> (<model>)`, `🤖 AI check:
    <n> items to check (<m> batches)`, `🤖 AI check: batch i/m done (<w> warnings)`, and
    `⚠ AI check: <message>` for non-fatal problems.
  - The last line is `🤖 AI report: ` + `json.dumps(result, ensure_ascii=False)`.
  - Exit 0 whenever a report was produced.
  - **Never use the `❌` prefix for findings.**
- [ ] T013 [US1] Manual check: with a Gemini key (and a Claude key if one is available), run
  quickstart **V3** (a test copy with planted mistakes), **V5** (grouping), **V6** (`provider =
  "claude"` without a key: unavailable, and Gemini not used) and **V7** (a forced 429 or
  `batch_size=10` gives `partial`). Record what was observed under Notes at the end of this file.

**Checkpoint**: the check is usable and complete from the command line.

---

## Phase 4: User Story 2 – Switch the check on or off (P1)

**Goal**: an **🤖 AI language check** toggle in the page, off by default. When it's on, results
appear in the run.

**Independent Test**: quickstart V1 (off means no AI section, no `🤖` lines), V2 and V9.

- [X] T014 [US2] In `language_automation/app.py`, add `st.toggle("🤖 AI language check",
  key="ai_check", value=False, disabled=busy)` directly under the Generate form. Under it, add a
  caption from `ai_providers.load_config()`: "Uses <provider> (<model>)", or "Not configured:
  <reason>". Read the config without importing either SDK. Because `key="ai_check"`, the value
  persists for the session (FR-003).
- [X] T015 [US2] In `language_automation/app.py`, add `run_ai_check(lang, status)`. It runs
  `[sys.executable, "-u", "ai_language_check.py", lang]` as a subprocess (cwd `APP_DIR`, the same
  environment and encoding as `run_pipeline`), and reuses the reader-thread, `session_is_open()`
  cancel and render pattern:
  - update `status` with "🤖 AI language check · batch i/m" from the `batch i/m done` lines;
  - parse the `🤖 AI report:` line into a dict;
  - append every line to the run's log;
  - return the dict, or a `failed` result with the last 15 log lines if no report line arrived.
- [X] T016 [US2] In the run loop in `language_automation/app.py`, after `run_pipeline(lang)`, add
  the check. Only if `st.session_state.ai_check` is on, `res["authenticated"]` is true, the state
  isn't `cancelled`, and `os.path.isfile(lang_paths.json_path(lang))`:
  - call `res["ai"] = run_ai_check(lang, …)` while still holding the lock;
  - add the warnings to `res["log"]` as plain lines: `AI <confidence> <category>: <text> →
    <suggestion> (<reason>) at <locations>`.

  When the toggle is off, nothing is imported or called (FR-002).
- [X] T017 [US2] Add `render_ai_section(ai)` to `language_automation/app.py`, called from
  `render_summary` when `res.get("ai")`. It renders exactly the UI states in the contract:
  - the header "🤖 AI language check (<provider>, language: <assumed_language>)";
  - `completed` with no warnings: `st.success("No issues found")`;
  - warnings: one row each, with a confidence badge, category, **text → suggestion**, reason,
    and "Where: …";
  - `partial`: a warning with "Checked n of m items: <reason>", then the warnings so far;
  - `unavailable` or `failed`: `st.warning("AI check unavailable: <reason>")`;
  - `cannot_judge`: `st.info(...)`.
- [X] T018 [US2] Manual check: quickstart **V1** (toggle off: the results match today's and there
  are no `🤖` lines in the log), **V2** (toggle on: the section appears and names the service and
  language) and **V9** (the toggle is disabled during the run). Use a headless-browser run if no
  real key is available, with a fake `ai_language_check.py` that prints a canned report, as in
  earlier UI tests.

**Checkpoint**: US1 and US2 together deliver the user's request.

---

## Phase 5: User Story 3 – Letters, words and recordings belong together (P2)

**Goal**: the exact consistency findings, plus AI recording-name mismatches, shown as their own
group.

**Independent Test**: quickstart V4. The consistency findings appear even when the AI provider is
unavailable.

- [X] T019 [US3] Add `consistency_warnings(items)` to `language_automation/ai_language_check.py`:
  - For `Word` items where `"".join(letters)` (NFC) ≠ `text`: category `letters_dont_spell_word`,
    reason "The letters <a+b+c> spell '<joined>', not '<text>'".
  - For `LetterInWord` items where any target letter isn't in `text`: category
    `letter_not_in_word`.
  - Both use `source="consistency"` and `confidence="high"`.
  - Call it in `check_language` **before** the provider step, and always include its results,
    even when the status is `unavailable` or `failed`.
- [X] T020 [US3] In `render_ai_section` in `language_automation/app.py`, show `source ==
  "consistency"` warnings under the subheading "Consistency check (letters vs words)". Label
  `recording_mismatch` rows "Recording name". Also count the consistency warnings in the
  section's total.
- [X] T021 [US3] Manual check: quickstart **V4**. In the test copy, remove a letter from a Word
  puzzle and change a LetterInWord target. Confirm both are reported with `provider` set to a
  missing key.

---

## Phase 6: Polish & cross-cutting

- [X] T022 [P] Update `CLAUDE.md`:
  - a section on `ai_language_check.py` and `ai_providers.py`: what's checked, AI versus code
    checks, the config file and environment variables, no silent switch between providers, and
    the `🤖` / `⚠ AI check:` / `🤖 AI report:` prefixes (no `❌`);
  - the toggle in the Web UI section;
  - `ai_config.toml` under Secrets.
- [X] T023 [P] Mark US1/US2/US3 as built in `specs/001-baseline-language-pipeline/spec.md`
  Overview, with one line pointing to spec 003.
- [ ] T024 Run quickstart **V8**: Hindi, Marathi, Hausa and IndianEnglish with each available
  provider. Record each run's time and the Claude cost per language (`usage.input_tokens` and
  `output_tokens` × $4 / $20 per million tokens for Opus 5.5) in `specs/003-ai-language-check/research.md` R5.
- [ ] T025 Run quickstart **V10** (`git status` doesn't show `ai_config.toml`, and the example has
  no keys) and check `specs/003-ai-language-check/spec.md` SC-001–SC-006. Record the results in
  `specs/003-ai-language-check/checklists/requirements.md` → Notes.

---

## Dependencies & Execution Order

- **Setup (T001–T004)**: all `[P]`, no dependencies.
- **Foundational**: T005, and T006 in parallel with it. T007 needs T005.
- **US1**: T008 → T009 ‖ T010 (both in `ai_providers.py`, so in practice one after the other) →
  T011 → T012 → T013. Needs T005 and T006.
- **US2**: needs the T012 report line for real results. T014–T017 can be built against a canned
  report. T014 → T015 → T016 → T017 → T018 (all in `app.py`, so sequential).
- **US3**: T019 needs T005 and T011. T020 needs T017. T021 comes last.
- **Polish**: after the stories. T024 needs real keys.

### Parallel opportunities

```text
Setup:        T001 ‖ T002 ‖ T003 ‖ T004
Foundation:   T005 ‖ T006
After T011:   T019 (ai_language_check.py) can proceed while T014–T015 (app.py) are built
Polish:       T022 ‖ T023
```

## Implementation Strategy

1. **MVP = Phases 1–3 (US1 from the command line)**. Prove the AI finds the planted mistakes
   (V3) before touching the UI.
2. **Then US2**: the toggle and section in the page. At that point the user's request is met.
3. **Then US3**: the exact consistency checks.
4. **Polish**: CLAUDE.md, a real cost measurement, and the success-criteria review.

Commit after each phase checkpoint.

## Notes

- AI findings are advisory: never `❌`, never a failed run, never edits to `lang/` or the sheet.
- Toggle off means zero AI imports or calls (FR-002). Check this in V1 by confirming no `🤖` lines
  appear.
- Never print or log API keys.

## Implementation results (2026-10-05)

- **Done and verified without an API key:**
  - T007: 255 items (252 puzzle items plus 3 feedback sentences), and the locations of "a" are
    correct.
  - Fake-reviewer tests of the real checker, all passing:
    - exactly **1 request** per check;
    - the second check of the same content made **no request** (cache);
    - changed content made one new request;
    - the planted misspelling, sentence and recording mismatch were reported;
    - both consistency checks fired;
    - an invented item ID was dropped;
    - results are sorted with high confidence first;
    - Claude without a key gave "unavailable", Gemini wasn't used, and the consistency checks were
      kept;
    - a rate limit gave "unavailable" after 1 attempt, and nothing was cached.
  - Recording names are sent only for the 2 changed items, and the request for Indian English is
    about 1.2 K tokens.
  - Headless Edge UI test, 10/10: toggle off means no AI section or lines; toggle on shows the
    service and language, the warnings with locations, the consistency group and the log lines;
    the toggle is disabled during a run and stays on afterwards; "unavailable" never says "No
    issues".
  - Command line without a key: unavailable report and exit 0. A bad name or missing JSON gives
    exit 1.
  - V10: the AI config and `.ai_cache/` are gitignored, and the example has no keys.
- **Config changed by the user (2026-10-05, after implementation):** `ai_config.toml` was replaced
  by two files.
  - **`config.json`** (tracked, no secrets) holds `provider` and the models.
  - **`.env`** (gitignored, template `.env.example`) holds `GEMINI_API_KEY` and
    `ANTHROPIC_API_KEY`.

  The tasks above that mention `ai_config.toml` now refer to these two files.
- **Open, needs a real key:**
  - **T013**: a real Gemini (and optionally Claude) call for V3/V6/V7. This also confirms that
    both providers accept the shared schema, and that Claude accepts `output_config.format`
    together with `fallbacks`.
  - **T024**: timing and cost per language.
  - **T025**: SC-001, SC-002, SC-003 and SC-006 need real results. V10 has already passed.

## Changes after implementation (2026-10-06, user requests; all built and verified)

- **AFC warning silenced, clearer "busy" message.** Gemini's automatic function calling is off
  (`automatic_function_calling: {"disable": true}`). 5xx answers report "busy right now… nothing
  was retried".
- **`fallback_models`** (config.json): tried in order only after a busy (5xx) or not-usable (404)
  answer, both of which use no tokens. Google's message is kept for each model. A 429 or bad key
  stops at once. Verified with a fake client: 7/7 checks, plus 2/2 for 404 fall-through.
- **`--list-models`**: a no-cost listing of the models the key can use (spec FR-025).
- **`temperature` and `max_output_tokens`** are passed when set. A `MAX_TOKENS` cut-off is reported
  clearly (spec FR-024).
- **Separate AI log**: `result["ai_log"]`, an "AI check log" expander and a "Download AI log"
  button, right after the unused-audio result. Nothing goes under the steps (spec FR-012).
  Headless browser: 13/13.

