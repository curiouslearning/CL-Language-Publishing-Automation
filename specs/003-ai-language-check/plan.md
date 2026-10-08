# Implementation Plan: AI Language Check of Sheet Content

**Branch**: `003-ai-language-check` (spec folder only) | **Date**: 2026-10-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-ai-language-check/spec.md`

## Summary

A new script, `ai_language_check.py <Language>`, does the work:
1. It reads the generated game JSON and collapses it into a compact list of unique content items
   (measured on Indian English: 750 puzzles become 252 items).
2. It runs two exact consistency checks in code: whether the letters spell the word, and whether
   the letter is in the word.
3. It sends the items in batches to **one** configured AI service, Gemini (free key) or Claude (paid
   key). Both are asked for **the same JSON Schema**, which reports misspellings, letters foreign
   to the language, bad sentences and mismatched recording names.
4. It prints progress lines and a final machine-readable report.

In `app.py`, an **AI language check** toggle (off by default) runs that script after the pipeline
finishes, under the same lock and with the same tab-close cancellation, and shows a grouped,
sorted warnings section. The run itself is never blocked or failed by it. Keys live in a
gitignored `ai_config.toml`, or in environment variables.

> **Revisions (user, 2026-10-05):**
> - One request per check, with a result cache, fewer tokens and Gemini by default (research
>   R2-rev).
> - The configuration is `config.json` (tracked: provider and models) plus `.env` (gitignored: API
>   keys) instead of `ai_config.toml` (research R7-rev).
>
> Mentions of `ai_config.toml`, `tomllib` and batching below are superseded by these.

## Technical Context

**Language/Version**: Python 3.11+ (uses the standard library's `tomllib`; 3.13 locally)

**Primary Dependencies**:
- existing: `streamlit`, `requests`, Google API client;
- **new: `anthropic`** (Claude SDK), using `client.beta.messages.create` with
  `output_config.format` and `fallbacks`;
- **new: `google-genai`** (Gemini SDK), using `client.models.generate_content` with
  `response_json_schema`.

Both are imported only when that provider is selected.

**Storage**: none. The config is a TOML file, and results go only to the UI and log.

**Testing**: no automated suite (constitution). Validation is quickstart V1–V10, using a test copy
of a game JSON with planted mistakes.

**Target Platform**: the same machine that runs the pipeline and `app.py` today (Windows).

**Project Type**: an addition to the command-line pipeline, plus a Streamlit UI extension

**Performance Goals**: ≤ 5 minutes per language with the check on (SC-003). That's about 4–10
batches.

**Constraints**:
- advisory only (FR-013, FR-014);
- no `❌` prefix for AI findings (constitution IV, and so they don't turn the run into "finished
  with errors");
- the toggle off means zero network calls to any AI service (FR-002);
- no silent switch between providers (FR-018).

**Scale/Scope**: about 250–600 unique items per language, and one check at a time (the existing
lock).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Assessment | Status |
|---|---|---|
| **I. Verify before you touch disk** | The check is read-only. It runs after the pipeline, never deletes or writes to `lang/`, and never edits the sheet. | ✅ |
| **II. Exact matching for language identity** | No change to how the language is looked up on Drive. The AI only receives the name as typed. | ✅ |
| **III. The game JSON is the source of truth for audio** | The check reads the final JSON (after step 3b's link rewrite). Recording-name checks follow its basenames. | ✅ |
| **IV. Stable log contract** | New `🤖 AI check:`, `⚠ AI check:` and `🤖 AI report:` prefixes. Existing prefixes are untouched, and `❌` is deliberately not used. | ✅ |
| **V. No secrets in the repository** | `ai_config.toml` is gitignored, only the example is tracked, environment variables are supported, and keys are never printed or logged. | ✅ |
| Constraint: dependencies justified | `anthropic` and `google-genai`. See Complexity Tracking. | ✅ Justified |
| Constraint: consistent path casing | Uses `lang_paths.json_path()` | ✅ |
| Workflow: manual verification and CLAUDE.md update | Quickstart V1–V10 become tasks, and updating CLAUDE.md is a task. | ✅ |

**Gate: PASS.**

**Post-design re-check**: still PASS. The contracts keep the AI path read-only and advisory, and
the config contract keeps keys out of git. Neither changes the pipeline's exit code nor its
existing log lines.

## Project Structure

### Documentation (this feature)

```text
specs/003-ai-language-check/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
├── contracts/
│   ├── ai-output.schema.json        # the one schema both providers must return
│   └── ai-check-cli-and-ui.md       # stdout prefixes, config file, UI states
├── checklists/requirements.md
└── tasks.md                         # /speckit-tasks
```

### Source Code

```text
requirements.txt                          # + anthropic, google-genai (pinned at install time)
.gitignore                                # + language_automation/ai_config.toml
language_automation/
├── ai_language_check.py                  # NEW: CLI + check_language(lang, config, progress) → AI Check Result
├── ai_providers.py                       # NEW: load_config(); ClaudeReviewer / GeminiReviewer.review(batch) → dict per schema
├── ai_output_schema.json                 # NEW: copy of contracts/ai-output.schema.json (runtime file)
├── ai_config.example.toml                # NEW: tracked template, no keys
└── app.py                                # CHANGED: toggle; run ai_language_check.py after the pipeline; render AI section; add to log
```

**Structure Decision**: two new flat modules in `language_automation/`, which matches the
existing standalone-script style. Provider code is kept separate so the item-building and
consistency logic can be tested without any API key. `generate_language.py` and the other
pipeline scripts are **unchanged**.

## Implementation phases (for /speckit-tasks)

1. **Setup**: dependencies, `.gitignore`, the example config, the schema file.
2. **Foundation**:
   - item building and the code consistency checks (d, e) in `ai_language_check.py`;
   - `load_config()` with environment-variable priority and the "unavailable" reasons.
   These can be checked offline against the Indian English JSON.
3. **US1**:
   - the providers (Claude and Gemini) with the shared schema;
   - batching, grouping and partial status;
   - the CLI report (V3, V5, V6, V7, V8).
4. **US2**: the toggle and UI section in `app.py`: off means no call; locked while busy; added to
   the log (V1, V2, V9).
5. **US3**: show the code consistency results and the recording-mismatch category in the UI (V4).
6. **Polish**: CLAUDE.md, the cost measurement in research R5, and V10.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New dependency `anthropic` | The Claude option (FR-016). The SDK gives typed errors, retries, structured outputs and server-side fallbacks. | Raw HTTP: the Claude reference requires the official SDK in Python projects, and we'd have to reimplement retries and error types. |
| New dependency `google-genai` | The Gemini option (FR-016), with `response_json_schema` structured output. | Raw REST calls: more code, and no typed `APIError`. Only one is imported per run (lazy import). |
