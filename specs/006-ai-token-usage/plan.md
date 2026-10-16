# Implementation Plan: AI Token Usage and Model per Check

**Branch**: `006-ai-token-usage` (spec folder only) | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-ai-token-usage/spec.md`

## Summary

Turn each provider's usage object into one dict. Carry it, and the model that answered, through
the AI report and the cache. Print one token line. Show it on the page under a new "Show tokens
used" toggle that sits under the AI check toggle.

## Technical Context

**Language/Version**: Python 3 (same as the rest of `language_automation/`)

**Primary Dependencies**: existing only: `anthropic`, `google-genai`, `streamlit`. No new dependency.

**Storage**: the existing `.ai_cache/<sha>.json` entries gain a `usage` key. Older entries without it stay valid.

**Testing**: no suite (constitution). Offline checks with fake usage objects and reviewers, and Streamlit `AppTest` for the toggle; manual run against a real language (tasks T012).

**Target Platform**: local Streamlit and Cloud Run (unchanged)

**Project Type**: standalone scripts + Streamlit page

**Constraints**: the token line keeps the `🤖 AI check:` prefix; nothing extra is sent to the AI; the toggle never triggers a request.

**Scale/Scope**: 3 code files + docs.

## Constitution Check

| Principle | Status |
|---|---|
| I. Verify before touching disk | Not affected: the AI check never writes to `lang/`. |
| II. Exact matching | Not affected. |
| III. JSON source of truth | Not affected. |
| IV. Stable log contract | Pass: new line uses the existing `🤖 AI check:` prefix; `app.py` needs no parser change (it's a log line). The `🤖 AI report:` JSON gains a field, read by `app.py` in the same change. |
| V. No secrets | Pass: usage counts and model names only. |
| Workflow: `CLAUDE.md` updated in the same change | Pass. |

## Design

### `ai_providers.py`

- `claude_usage(u)`: `input_tokens` = `input_tokens` + `cache_creation_input_tokens` + `cache_read_input_tokens`; `output_tokens` as reported (thinking included); `thinking_tokens` = null.
- `gemini_usage(u)`: `input_tokens` = `prompt_token_count`; `output_tokens` = `candidates_token_count` + `thoughts_token_count`; `thinking_tokens` = `thoughts_token_count`; `cache_read_tokens` = `cached_content_token_count`.
- Both reviewers set `self.usage` from these, **before** the refusal / max-tokens checks, so a billed but unusable answer keeps its usage.
- `ClaudeReviewer.model_used` = `resp.model` when it isn't a dated id of the configured alias (server-side fallback), else the configured model. Gemini already set `model_used` per fallback.

### `ai_language_check.py`

- `result["usage"]` (null by default). After an answer: `raw["usage"] = reviewer.usage`, saved in the cache.
- `token_line(model, usage)` → `🤖 AI check: <model>, tokens: input N, output N[ (incl. N thinking)], total N`.
- Cached: `🤖 AI check: tokens used this run: 0 (cached). <model>, the earlier request used: …`.
- On `Unavailable` / unreadable answer: if the reviewer has usage, report it and print the token line.

### `app.py`

- `st.session_state.show_tokens` (default false). When `ai_check` is on, an indented `st.toggle("🔢 Show tokens used", key="show_tokens_toggle", value=show_tokens, disabled=busy)` writes back to `show_tokens`. A separate key is used because Streamlit drops a widget's state when it isn't drawn (AI check off).
- `render_ai_usage(ai)` draws the model/tokens line, plus a caption for cached results. `render_ai_section` calls it only when `show_tokens` is on. It's read at render time, so it applies to earlier runs on the page too.

## Project Structure

### Documentation (this feature)

```text
specs/006-ai-token-usage/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/requirements.md
```

Spec 003's `data-model.md` and `contracts/ai-check-cli-and-ui.md` get the new `usage` field, the token line and the toggle.

### Source Code

```text
language_automation/
├── ai_providers.py        # claude_usage, gemini_usage, model_used
├── ai_language_check.py   # usage in report + cache, token_line
└── app.py                 # Show tokens used toggle, render_ai_usage
```

**Structure Decision**: same single-folder layout; no new module.

## Complexity Tracking

None.
