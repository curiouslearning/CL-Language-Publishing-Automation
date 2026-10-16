<!--
Sync Impact Report
- Version change: 1.0.1 → 2.0.0 (MAJOR: principle III redefined at the user's request, 2026-10-06)
- Modified principles:
  - III. The Game JSON Is the Source of Truth for Audio: near-matches are now **warned about, never
    renamed**. A new rule says the pipeline never auto-corrects names it only thinks are the same.
  - IV. Stable Log Contract: the `🔤 Renamed:` prefix is replaced by `🔍 Look-alike:`, with
    `app.py` updated in the same change.
- Previous (1.0.1): reflected the removal of the legacy Cloud Functions.
- Removed sections: none
- Templates requiring updates: none (plan/spec/tasks templates read this file at runtime)
- Deferred TODOs: none
-->

# FTM Language Publishing Automation Constitution

## Core Principles

### I. Verify Before You Touch Disk

The pipeline MUST confirm that every remote input it depends on exists (the language sheet and
the language audio folder on Google Drive) before it creates, wipes, or overwrites anything under
`lang/<Language>/`. A run that fails verification MUST exit non-zero and leave local data exactly
as it was.

Rationale: `generate_language.py` wipes the language folder with `shutil.rmtree`. A typo or a
missing Drive folder must never destroy a previously good local build.

### II. Exact Matching for Language Identity

A language name MUST be matched exactly against Drive file and folder names, ignoring only case
and known file extensions (`.xlsx`/`.xls`). Substring or fuzzy matching MUST NOT be used to
choose a language's sheet or audio folder. Drive's `name contains` query may only narrow the
candidate list.

Rationale: substring matching once caused `English` to resolve to `EnglishWestAfrican`, which
publishes the wrong language's content.

### III. The Game JSON Is the Source of Truth for Audio

The generated `ftm_<lang>.json` defines the audio files the game needs. The pipeline MUST:

- keep every audio file referenced by `PromptAudio`, `FeedbackAudios`, and `OtherAudios`, plus
  the fixed exceptions (`great.mp3`, `amazing.mp3`);
- write the look-alike Devanagari vowel sequences ा + े and ा + ै as the single standard signs
  ो and ौ, in every JSON string and in every downloaded audio file name (`spelling.py`), so both
  sides match. This is the one deliberate exception to the rule below (user decision, 2026-10-14):
  these sequences render identically, so the team cannot see the difference to fix it;
- keep any other near-match (by `normalize_audio_name`, e.g. upper/lowercase only) **as is**,
  neither renamed nor deleted, and report it as a look-alike for the team to check;
- rewrite Drive share links in the JSON to the standard audio URL prefix so that every reference
  is matched by basename;
- report missing audio without failing the run.

Apart from the vowel-sign standardization above, the pipeline MUST NOT rename, re-spell or
otherwise "correct" content or file names on the basis of similarity. When names only look alike, it warns and leaves the fix to the content team.

Rationale: the game requests audio by exact filename. Content teams fix gaps after the run, so a
report helps them more than a hard stop. A guessed correction can hide a real mistake, while a
clear warning gets it fixed in the sheet or on Drive.

### IV. Stable, Human-Readable Log Contract

Pipeline scripts communicate with the Streamlit UI (`app.py`) through stdout lines with emoji
prefixes. The prefixes `🗑 Deleted:`, `🔍 Look-alike:`, `❌ Missing audio files:`, and
`✔ Audio cleanup completed` are a public contract. Changing or removing one MUST include a
matching change to `app.py` in the same change. New user-facing steps SHOULD use the same style
so the UI can show them.

Rationale: the content team relies on the UI and does not read raw logs. A silently changed
prefix breaks their audio summary without any visible error.

### V. No Secrets in the Repository

Credentials MUST NOT be committed or hardcoded. This covers OAuth `credentials.json`,
`token.json`, service-account keys, email addresses with app passwords, and API keys. Secrets
MUST come from local untracked files, environment variables, or Secret Manager. Generated data
(`lang/`) and environments (`.venv/`) MUST also stay out of version control.

Rationale: the now-removed legacy Cloud Functions hardcoded a Gmail app password. New code MUST
NOT repeat that pattern.

## Technical Constraints

- **Stack**: standalone Python 3 scripts. Only `google-api-python-client`,
  `google-auth-oauthlib`, `requests`, `streamlit`, and `ffmpeg` on PATH are required. Adding a
  dependency MUST be justified in the feature's `plan.md`.
- **Execution**: pipeline scripts run from inside `language_automation/` and use CWD-relative
  paths. New scripts MUST follow the same convention or resolve paths from `__file__`
  consistently.
- **Path casing**: new code MUST build `lang/` paths with one consistent casing rule. The
  existing mix of as-typed and lowercased names works only on case-insensitive filesystems and
  MUST NOT be extended.
- **Audio format**: audio delivered to the game is mp3, 44.1 kHz stereo, 192 kbps.
- **Drive IDs**: hardcoded Drive folder and shared-drive IDs are allowed. New ones MUST be
  defined once as named module-level constants, not inline literals.
- All capability lives in `language_automation/`. The legacy Cloud Functions were removed from
  the repo on 2026-10-05 and MUST NOT be reintroduced as separate code paths.

## Development Workflow

- Every non-trivial change follows Spec Kit: `/speckit-specify` → (`/speckit-clarify`) →
  `/speckit-plan` → `/speckit-tasks` → (`/speckit-analyze`) → `/speckit-implement`. Artifacts
  live in `specs/<NNN-feature>/`.
- There is no automated test suite. Each feature's `tasks.md` MUST include a manual verification
  task. That task runs the pipeline against at least one real language (e.g. `Hausa`) and
  confirms the `check_missing_audios` output and the Streamlit summary.
- When a pipeline step, ordering, or log prefix changes, `CLAUDE.md` MUST be updated in the same
  change.
- Small fixes (typos, a one-line bug) MAY skip Spec Kit. They still MUST respect every principle
  above.

## Governance

This constitution overrides informal conventions for this repository. Every plan produced by
`/speckit-plan` MUST pass its Constitution Check against these principles. Any violation MUST be
recorded in the plan's Complexity Tracking table with a justification.

Amendments are made with `/speckit-constitution`, recorded in the Sync Impact Report, and
versioned semantically. MAJOR means a principle is removed or redefined. MINOR means a principle
or section is added or materially expanded. PATCH means clarifications only. `CLAUDE.md` remains
the runtime guidance for how the code works. This file governs how changes are made.

**Version**: 2.0.0 | **Ratified**: 2026-10-05 | **Last Amended**: 2026-10-06
