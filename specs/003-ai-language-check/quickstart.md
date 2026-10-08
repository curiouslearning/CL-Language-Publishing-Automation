# Quickstart & Validation: AI Language Check

Reference documents: [plan.md](plan.md), [contracts/ai-check-cli-and-ui.md](contracts/ai-check-cli-and-ui.md),
[contracts/ai-output.schema.json](contracts/ai-output.schema.json) and [data-model.md](data-model.md).

## Setup

```powershell
python -m pip install -r requirements.txt      # adds anthropic and google-genai
cd language_automation
copy .env.example .env                         # paste GEMINI_API_KEY=... (and/or ANTHROPIC_API_KEY=...)
# choose the service/model in config.json ("provider": "gemini" or "claude")
```

## Run

```powershell
python ai_language_check.py IndianEnglish      # command line: progress lines, then "🤖 AI report: {...}"
python -m streamlit run app.py                 # web page: switch on "🤖 AI language check", then Generate
```

## Validation scenarios

| # | Scenario | Steps | Expected |
|---|---|---|---|
| V1 | Toggle off (US2, SC-004) | Generate a language with the toggle off | Results identical to today. No AI section, no network call to any AI service, and no `🤖` lines in the log. |
| V2 | Toggle on, clean language (US1/AC4) | Toggle on, generate a language a native speaker has reviewed | An AI section names the service and assumed language and says "No issues found", or shows only low-confidence items. |
| V3 | Planted mistakes (US1, SC-001) | Copy a generated `ftm_<lang>.json` to a test name, edit in 1 misspelled word, 1 foreign letter, 1 broken feedback sentence and 1 wrong recording name, then run `python ai_language_check.py <test>` | All 4 are reported with a suggestion, reason and the correct `level.puzzle`. |
| V4 | Consistency checks (US3) | In the test copy, remove one target letter from a Word puzzle, and change a LetterInWord target to a letter not in the word | Both are reported as "Consistency check", even with `provider` set to an empty key (V6). |
| V5 | Grouping (FR-010) | A misspelled word that appears in several levels | One warning listing every location |
| V6 | No key (FR-018) | Set `provider="claude"` with no Claude key, while a Gemini key exists | "AI check unavailable: no API key configured for claude". Gemini is **not** used. The run still completes. |
| V7 | Rate limit (FR-019) | Simulate a 429, e.g. by running checks back to back on the free tier | Status `unavailable`: "Gemini rate limit reached…". Exactly one attempt, nothing cached, and the content isn't reported as clean. |
| V8 | Each provider and the cost (SC-003, SC-006) | Run Hindi, Marathi, Hausa and IndianEnglish once with each provider | Each finishes in ≤ 5 minutes. Record the Claude cost from `usage` per language in research.md R5. |
| V9 | Locked during the run (FR-003) | Start a run with the toggle on | The toggle is disabled until the run finishes, like Generate. |
| V10 | Secrets (FR-017) | `git status` | `.env` doesn't show (it's ignored). `.env.example` and `config.json` are tracked and contain no keys. |
