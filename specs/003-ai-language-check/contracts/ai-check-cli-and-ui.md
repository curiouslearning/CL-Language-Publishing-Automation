# Contract: `ai_language_check.py` output, configuration and UI

## Command line

```bash
cd language_automation
python ai_language_check.py <Language>          # uses config.json (service, model) + .env (API keys)
```

- **Exit code 0** when a report was produced, even if partial or unavailable. The report says what
  happened.
- **Exit code 1** only for an invalid language name or a missing game JSON.
- It never writes to `lang/<language>/` and never edits the sheet (FR-013).

## Stdout lines (stable prefixes, which `app.py` parses; constitution IV)

| Prefix | Meaning |
|---|---|
| `🤖 AI check: using <provider> (<model>)` | Start. The service used is named (FR-018). |
| `🤖 AI check: <n> items to check (~<t> tokens, 1 request)` | Size, with an approximate token count (characters ÷ 4) |
| `🤖 AI check: content unchanged since <date>, reusing earlier result (no API call)` | A cache hit (FR-021) |
| `🤖 AI check: done (<w> warnings)` | The single request finished |
| `⚠ AI check: <message>` | Non-fatal problem, e.g. a rate limit, refusal or truncated batch |
| `🤖 AI report: <json>` | **Last line.** The full AI Check Result ([data-model.md](../data-model.md)) as one line of JSON |

The `❌` prefix is **not** used for AI warnings. Otherwise `app.py` would count them as pipeline
errors and mark the run "Finished with errors". AI findings are advisory (FR-013, FR-014).

## Configuration (revised 2026-10-05: `config.json` for settings, `.env` for keys)

`language_automation/config.json` is **tracked** and holds no secrets. It says which service and
model to use:

```json
{
  "provider": "gemini",
  "gemini": { "model": "gemini-flash-latest" },
  "claude": { "model": "claude-opus-5-5", "effort": "low", "fallbacks": true }
}
```

`language_automation/.env` is **gitignored**; the template `.env.example` is tracked. It holds the
API keys:

```dotenv
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
```

- Real environment variables win over `.env`.
- An `api_key` placed in `config.json` is ignored.

| Situation | Result status / message |
|---|---|
| No key for the chosen provider in the environment or `.env` | `unavailable`: "AI check unavailable: no API key configured for <provider>: add <ENV_VAR>=... to language_automation/.env" |
| `provider` isn't `gemini` or `claude` | `unavailable`: "AI check unavailable: unknown provider '<x>' in config.json (use "gemini" or "claude")" |
| `config.json` isn't valid JSON | `unavailable`: "AI check unavailable: config.json could not be read (<error>)" |
| Package for the provider isn't installed | `unavailable`: "AI check unavailable: install <package> (pip install -r requirements.txt)" |

## UI (`app.py`)

- **Toggle**: an `st.toggle("🤖 AI language check", key="ai_check")` next to Generate.
  - **Off by default.** It keeps its value for the session, and is `disabled` while busy, like
    Generate.
  - Its caption shows the configured provider, or "not configured".
- **During a run with the toggle on**: after the pipeline's steps, the run's box shows
  "🤖 AI language check in progress…". On a cache hit it shows "From earlier check on <date>:
  content unchanged".
- **Results**: a section, "🤖 AI language check (<service>, language: <assumed>)":
  - `completed` with no warnings: `st.success("No issues found")`.
  - Warnings: sorted high → medium → low, one row each. A row shows the confidence badge, the
    category, **text → suggestion**, the reason, and "Where: level 12 puzzle 3, level 40 puzzle 1 …".
    The two code-based consistency checks are labelled "Consistency check".
  - `unavailable` or `failed`: `st.warning("AI check unavailable: <reason>")`. It never says "no
    issues".
  - `cannot_judge`: `st.info("<service> could not reliably review <language>: <note>")`.
- **Log**: the warnings are added to the run's downloadable log as plain text lines (FR-012).
