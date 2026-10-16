# Data Model: AI Language Check

No database. Everything exists for one run, except the config file.

## Content Item (built from `lang_paths.json_path(lang)`)

| Field | Source | Notes |
|---|---|---|
| `id` | assigned `i1, i2, …` | Unique within the run |
| `kind` | `LevelMeta.LevelType` (`LetterOnly`, `LetterInWord`, `Word`) or `Feedback` | |
| `text` | `prompt.PromptText`, or the feedback text | NFC-normalized |
| `letters` | `targetstones[].StoneText` | Empty for feedback |
| `recording` | basename of `prompt.PromptAudio` | Empty for feedback |
| `locations` | every `level.puzzle` (`LevelMeta.LevelNumber`.`SegmentNumber`) with the same (kind, text, letters, recording) | Feedback items use `feedback <n>` |

The uniqueness key is `(kind, text, letters, recording)`. Measured on Indian English: 750 puzzles
become 252 items.

## AI Warning

| Field | Type | Rule |
|---|---|---|
| `category` | `misspelled_word` \| `foreign_letter` \| `bad_sentence` \| `recording_mismatch` (from the AI) \| `letters_dont_spell_word` \| `letter_not_in_word` (from code) | FR-006 a–f |
| `source` | `ai` \| `consistency` | The UI labels `consistency` findings "Consistency check" |
| `text` | string | As written |
| `suggestion` | string | May be empty |
| `reason` | string | |
| `confidence` | `high` \| `medium` \| `low` | Always `high` for code checks |
| `locations` | list of `level.puzzle` / `feedback n` | Expanded from `item_ids`. Grouped: identical (category, text, suggestion) warnings across batches are merged and their locations combined (FR-010) |

Any `item_ids` the model returns that weren't in the batch are dropped, so a made-up ID can never
point at the wrong place.

## AI Check Result (the `🤖 AI report:` JSON)

| Field | Type | Notes |
|---|---|---|
| `provider` | `gemini` \| `claude` | FR-018 |
| `model` | string | The model that actually answered (a fallback model when one answered). Spec 006. |
| `assumed_language` | string | From the first successful batch |
| `status` | `completed` \| `unavailable` \| `cannot_judge` | See the transitions below. A failed call is `unavailable` with its reason (FR-019). |
| `reason` | string | Required unless `completed` |
| `items_total` | int | |
| `approx_tokens` | int | Characters of the request ÷ 4 (informational) |
| `cached` | bool | true means no API call was made (FR-021) |
| `usage` | Token Usage or null | *(spec 006)* Real counts from the API: `input_tokens`, `output_tokens` (thinking included), `thinking_tokens` (Gemini; null for Claude), `cache_read_tokens`, `cache_write_tokens`. Also stored in the cache entry; when `cached` is true these are the earlier request's counts and this run used 0. Null when no answer was received. |
| `checked_at` | ISO date-time | When the AI call was actually made. Kept when the result is reused from the cache. |
| `warnings` | list of AI Warning | Sorted high → medium → low, then by first location |

### Status transitions

```text
start ──config/key/package missing──► unavailable            (code checks d/e still reported; no call)
  ├─ same content checked before ───► cached completed/cannot_judge (no call)
  └─ one request
       ├─ ok ────────────────────────► completed            (saved to .ai_cache/)
       ├─ can_judge=false ───────────► cannot_judge         (saved; warnings marked low)
       └─ 429/refusal/max_tokens/network/error ─► unavailable (reason; not cached; not retried)
```

## AI Configuration (`config.json` for settings + `.env` for keys)

Keys are only ever read from the environment or `.env`. An `api_key` in `config.json` is ignored.

| Key | Default | Rule |
|---|---|---|
| `provider` | `"gemini"` | Must be `gemini` or `claude`. No silent switching to the other (FR-018) |
| `gemini.api_key` | "" | The `GEMINI_API_KEY` environment variable takes priority |
| `gemini.model` | `gemini-flash-latest` | |
| `claude.api_key` | "" | The `ANTHROPIC_API_KEY` environment variable takes priority |
| `claude.model` | `claude-opus-5-5` | |
| `claude.effort` | `low` | `low`, `medium`, `high`, `xhigh` or `max` (higher means more tokens) |
