# Research: AI Language Check of Sheet Content

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-10-05

Sources:
- the bundled Claude API reference (models, pricing, structured outputs, errors; cached 2026-09-25);
- the `google-genai` SDK README (github.com/googleapis/python-genai) and the Gemini docs
  (ai.google.dev);
- measurements on the local `ftm_indianenglish.json`.

---

## R1. What gets sent: one compact, de-duplicated item list per language

- **Measured**: Indian English has 750 puzzles. That collapses to **252 unique items**, keyed on
  level type, prompt text, target letters and recording name. Each item line lists every
  `level.puzzle` where it appears, and the whole list is about 10.4 K characters (≈ 2.6 K tokens).
  The full game JSON is about 289 K characters, roughly 28 times more.
- **Decision**: build one line per unique item:
  `id | level type | text | letters | recording name`. Add the feedback sentences as their own
  items. Send only these lines, never the raw JSON. Code maps item `id`s back to every location,
  so the model never has to reproduce level numbers. That makes FR-009 and FR-010 grouping
  reliable.
- **Why**: about 28 times less input, so less cost and fewer free-tier tokens. Grouping repeated
  items is also exactly what FR-010 asks for.
- **Alternatives**: sending the raw JSON (rejected: size, and the model would have to report
  locations), or reading the Excel sheet directly (rejected: the game JSON is the
  constitution's source of truth, and it already has recording names rewritten by step 3b).

## R2-rev. **Revised by the user, 2026-10-05: one call, cache, fewer tokens (replaces R2, and the retry in R6)**

- **One request per check** (FR-020): every item goes in a single request.
  - Indian English is about 2.6 K tokens of items, and other scripts are several times that.
    That's still far under any context limit.
  - There is no batching, and **no retries**: Anthropic `max_retries=0`, and no Gemini 429 retry.
    A failure becomes `unavailable` with the reason (FR-019).
- **Result cache** (FR-021): `language_automation/.ai_cache/<sha256>.json`, gitignored.
  - The key is the SHA-256 of `provider | model | language.lower() | item lines`.
  - If the file exists, return it with `cached=true` and its `checked_at`. **No call is made.**
  - Only `completed` and `cannot_judge` results are cached. Failures are never cached.
- **Fewer tokens** (FR-022):
  - Recording names are only sent when the normalized basename (without `.mp3`) differs from the
    item's text, or, for letter puzzles, from the target letter. Matching names can't be
    mismatches, so leaving them out doesn't hide anything.
  - The instruction prompt is short.
  - The schema asks for one short-sentence `reason`.
  - Claude's default effort is `low`. Gemini uses the model's default.
- **Default provider is `gemini`** (FR-023).

## R2. Batching and size *(superseded by R2-rev)*

- **Decision**: send items in batches of `batch_size` (default **80**, configurable), one request
  per batch, one after another.
  - English: 252 items, 4 requests.
  - Devanagari and other non-Latin scripts take several times more tokens per character, but 80
    items still stay far under any context limit.
- **Why**:
  - It gives partial progress, so FR-019 can say "checked N of M".
  - It keeps each output small.
  - If the model stops early (`max_tokens`) or gets cut off by a rate limit, only one batch is
    lost.

## R3. Same output schema for both services

- **Decision**: one JSON Schema, used by both providers:
  - **Claude**: `output_config={"format": {"type": "json_schema", "schema": SCHEMA}}`. This
    guarantees that the first `text` block is valid JSON. (Pattern from the Claude API reference,
    *Structured Outputs → Raw Schema*.)
  - **Gemini**: `client.models.generate_content(model=…, contents=…, config={"response_mime_type":
    "application/json", "response_json_schema": SCHEMA})` (from the `google-genai` README).
- The schema is in [contracts/ai-output.schema.json](contracts/ai-output.schema.json). The model
  returns `item_ids`, `category`, `text`, `suggestion`, `reason`, `confidence`, plus
  `assumed_language` and `can_judge` (spec edge case: a language the AI knows little about).
- **Why**: one parser, one set of validation rules, and one UI renderer for both providers.
- **Alternatives**: Pydantic `messages.parse` on Claude only (rejected: no gain over a schema both
  providers share), or free-text output (rejected: unreliable to parse).

## R4. Which checks the AI does and which code does

| Category (spec FR-006) | Done by | Why |
|---|---|---|
| (a) misspelled words | AI | Needs knowledge of the language |
| (b) letters not in the writing system | AI | Needs knowledge of the language |
| (c) bad feedback sentences | AI | Needs knowledge of the language |
| (d) letters don't spell the word | **Code**: joined target letters ≠ word, after NFC | Exact, free, and no false alarms |
| (e) letter not in the word | **Code**: letter not found in the word, after NFC | Exact, free, and no false alarms |
| (f) recording name doesn't match | AI | Names are often romanized ("kya.mp3") while the text is in its own script, so it needs transliteration judgment |

The code-based (d) and (e) findings use confidence `high`, and the report labels them "consistency
check", so they're kept apart from AI opinions. They run whenever the toggle is on, even if the AI
service is unavailable.

The rule for which recording belongs to what comes from the level type: `LetterOnly` and
`LetterInWord` puzzles play the target **letter's** recording, while `Word` puzzles play the
**word's** (seen in the data: the LetterInWord "cat" puzzle uses `c.mp3`). The prompt tells the
model this rule, so it doesn't flag correct pairings.

## R5. Claude: model, effort, fallbacks, errors

- **Model**: `claude-opus-5-5`, the current default ($4 per million input tokens, $20 per million
  output). It's a config value (`claude.model`), so the team can move to `claude-sonnet-5-5`
  ($2 / $10) if they decide cost matters more. The plan doesn't pick a cheaper model on their
  behalf.
- **Thinking and effort**: thinking is always on for Opus 5.5 (never send `{"type":"disabled"}`).
  Set `output_config.effort` explicitly. The default is `"high"` because judging a language well,
  including less-known ones, is reasoning-heavy; it's configurable as `claude.effort`. (Opus 5.5's
  own default would be `medium`.)
- **Fallbacks**: `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"],
  fallbacks="default")`. If the model declines (`stop_reason: "refusal"`), the API retries on a
  fallback model in the same call. This is on by default, as the Claude API reference recommends
  for this model. Check the final `stop_reason` before reading content.
  **Verify in implementation** that `output_config.format` combines with `fallbacks` on the beta
  endpoint. If not, drop `fallbacks` and treat a refusal as a failed batch.
- **Limits**: `max_tokens=16000`, non-streaming. Each batch's output is small. If `stop_reason ==
  "max_tokens"`, that batch is reported unchecked (FR-019).
- **Errors**: the SDK already retries 429 and 5xx twice. After that, catch `anthropic.RateLimitError`
  and stop with a partial result. `AuthenticationError` means "invalid API key";
  `APIConnectionError` means "AI service unreachable".
- **Cost estimate**: about 3–15 K input tokens per language, plus output and thinking of roughly
  10–30 K tokens. On Opus 5.5 that's about $0.05 for input plus $0.20–0.60 for output, so **under
  about $1 per language**. Measure this in quickstart V8 and record it.

## R6. Gemini: package, model, free-tier limits, errors

- **Package**: `google-genai`. The client is `genai.Client(api_key=…)`; it also reads
  `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Use `client.models.generate_content` (the documented,
  stable call).
- **Model**: the `gemini-flash-latest` alias (configurable as `gemini.model`). It's a fast flash
  model suited to the free tier. The newer `client.interactions.create` API also exists, but its
  structured-output parameters aren't documented in the README, so it isn't used.
- **Free-tier limits aren't published in the docs**. They're only visible in AI Studio
  (`aistudio.google.com/rate-limit`). Exceeding them returns HTTP **429 `RESOURCE_EXHAUSTED`**.
  - **Decision**: wait `gemini.seconds_between_requests` (default 5 s) between batches.
  - On `google.genai.errors.APIError` with `.code == 429`, wait 30 s and retry once, then stop
    with a partial result ("stopped: Gemini rate limit reached") as FR-019 requires.
- **Data use**: on the free tier, Google's terms may allow submitted content to be used to improve
  its products. The spec accepts this for vocabulary lists, and that's why the paid Claude option
  exists.

## R7-rev. Configuration and secrets (revised by the user, 2026-10-05; replaces R7)

- **`language_automation/config.json`** (tracked, no secrets) holds `provider` plus each provider's
  `model`, and Claude's `effort` and `fallbacks`. It's read with the standard library `json`.
- **`language_automation/.env`** (gitignored, template `.env.example`) holds `GEMINI_API_KEY` and
  `ANTHROPIC_API_KEY`.
  - A ~15-line reader (`read_env_file`) handles `KEY=VALUE`, `#` comments and quotes, so there's
    no `python-dotenv` dependency.
  - Real environment variables win over `.env`.
- **Why**: the team can see and change the model in a committed file, while keys stay in the
  conventional, ignored `.env`.

## R7. Configuration and secrets *(superseded by R7-rev)*

- **Decision**: a TOML file at `language_automation/ai_config.toml` (gitignored), read with the
  standard library's `tomllib` (Python ≥ 3.11, so no new dependency), plus a tracked
  `ai_config.example.toml`.
  - Keys can also come from environment variables (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`), which
    take priority over the file.
  - `provider` must be `"gemini"` or `"claude"`. There's no silent fallback to the other provider
    (FR-018).
- **Why TOML**: comments for the team, and the standard library reads it. The same pattern as
  `credentials.json`: the secret file is local and the example is tracked.

## R8. Where the check runs

- **Decision**: a new standalone script, `language_automation/ai_language_check.py <Language>`, in
  keeping with the repo's other scripts.
  - It reads `lang_paths.json_path(lang)`, builds the items (R1), runs the code checks (R4), calls
    the configured provider in batches, and prints emoji-prefixed progress lines.
  - Its last line is `🤖 AI report: <json>`, the result in machine-readable form.
- **In the web page**: after the pipeline subprocess finishes, if the toggle is on, the game JSON
  exists, and the run got past authentication, `app.py` runs `ai_language_check.py` as a second
  subprocess under the same lock. It uses the same tab-close cancellation, and shows a "🤖 AI
  language check" section in the run.
  - The JSON exists only if this run fetched it, because step 2 wipes the folder.
  - Running after the pipeline means the recording names are final (after step 3b).
- **Why not inside `generate_language.py`**: FR-014 says the check must never affect the pipeline
  or its exit code. Keeping it separate also leaves the command-line pipeline unchanged.
- **Command line**: `python ai_language_check.py Hindi` works on its own, for the team or for
  debugging.
- **The report** is not written into `lang/<language>/`, which is the game package. It goes into
  the run log and the UI (FR-012).

## R9. Prompt design

- **System prompt** (fixed, so it can be cached):
  - the role: a reviewer of early-literacy phonics content;
  - categories a–c and f, with definitions;
  - the phonics exception (FR-007);
  - the recording rule by level type (R4);
  - the confidence rubric;
  - "if you cannot judge this language reliably, set `can_judge=false` and explain in `note`;
    do not guess";
  - "report only problems; an empty `warnings` list is a valid answer".
- **User content**: the language name as entered, plus the batch's item lines.
- **Assumed language**: the model returns `assumed_language`, e.g. "English (India)" for
  "IndianEnglish". The first batch's value is shown.
