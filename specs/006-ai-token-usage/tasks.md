---
description: "Task list for 006 – AI Token Usage and Model per Check"
---

# Tasks: AI Token Usage and Model per Check

**Input**: `specs/006-ai-token-usage/` (spec.md, plan.md)

**Tests**: no automated suite (constitution). Offline checks with fake usage objects / reviewers and Streamlit `AppTest`, plus a manual run (T012).

**Paths**: everything is in `language_automation/`. The pipeline scripts are **not** modified.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Foundational

- [X] T001 [P] Add `claude_usage` and `gemini_usage` (one usage shape, thinking counted as output) in `language_automation/ai_providers.py`
- [X] T002 Set `ClaudeReviewer.usage` / `GeminiReviewer.usage` from them before the refusal and max-tokens checks; set `ClaudeReviewer.model_used` from `resp.model` when another model answered, in `language_automation/ai_providers.py`

## Phase 2: User Story 1 - See the real tokens and model (P1)

- [X] T003 [US1] Add `usage` to the AI Check Result and to the cache entry in `language_automation/ai_language_check.py`
- [X] T004 [US1] Report usage and model for billed-but-unusable answers (`Unavailable`, unreadable JSON) in `language_automation/ai_language_check.py`
- [X] T005 [US1] Add `render_ai_usage` (model, input, output incl. thinking, total; cached caption; "not recorded" / "no tokens used" cases) in `language_automation/app.py`
- [X] T006 [US1] Offline check: fake Gemini/Claude usage objects give the expected dicts; fresh, cached and failed checks carry `usage`

## Phase 3: User Story 2 - Show tokens used toggle (P2)

- [X] T007 [US2] Add `st.session_state.show_tokens` and the indented "🔢 Show tokens used" toggle under the AI check toggle (off by default, disabled while busy, kept when the AI check is switched off/on) in `language_automation/app.py`
- [X] T008 [US2] Call `render_ai_usage` from `render_ai_section` only when `show_tokens` is on
- [X] T009 [US2] `AppTest` check: toggle hidden when AI check off, shown when on, state kept after off/on; section shows the line only with the toggle on

## Phase 4: User Story 3 - AI log record (P3)

- [X] T010 [US3] Add `token_line` and print it after every answer / cache reuse (`🤖 AI check:` prefix) in `language_automation/ai_language_check.py`

## Phase 5: Polish

- [X] T011 [P] Update `CLAUDE.md` (specs list, Web UI toggle, token usage) and spec 003 `data-model.md` + `contracts/ai-check-cli-and-ui.md`
- [ ] T012 Manual verification: on the page, generate one real language (e.g. `Hausa`) with the AI check and "Show tokens used" on, once with Gemini and once with Claude. Confirm model, input and output tokens appear and match each provider's usage console; generate again unchanged and confirm "0 tokens this run"; confirm the `check_missing_audios` output and audio summary are unchanged.

## Dependencies

T001 → T002 → T003/T004/T010 → T005 → T007/T008 → T011 → T012
