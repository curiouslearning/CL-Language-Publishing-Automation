# AI-assisted Language Publishing Automation

Tooling for publishing new languages for Curious Learning's **Feed the Monster (FTM)** game. For one language, it pulls the content JSON and audio files from Google Drive into `language_automation/lang/<language>/`, cleans up unused audio, and reports missing audio. A Streamlit web page wraps the pipeline for the content team. An optional AI review checks the language content.

> For the full details (pipeline steps, the web page's behaviour, the AI check, gotchas), see [CLAUDE.md](CLAUDE.md). Feature specs are in [specs/](specs/) and project rules are in [.specify/memory/constitution.md](.specify/memory/constitution.md).

## Setup

1. Install Python dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Install **ffmpeg** and put it on your `PATH` (it converts non-mp3 audio to mp3).
3. Put the Google OAuth client files in `language_automation/`. Ask the team for them and **never commit them** (both are gitignored):
   - `client_secret_web.json`: the **Web application** client for the web page, from the Google Cloud project `ftm-language-generator`.
   - `credentials.json`: the **desktop** client, only needed for the command line.
4. Optional, only for the AI language check: copy `language_automation/.env.example` to `language_automation/.env` and add your key (`GEMINI_API_KEY` or `ANTHROPIC_API_KEY`). Choose the provider and model in `language_automation/config.json`.

## Usage

Run everything from inside `language_automation/`:

```bash
cd language_automation

python -m streamlit run app.py              # web page for the content team
python generate_language.py Hausa           # full pipeline from the command line
python ai_language_check.py Hausa           # optional AI review of a generated language
```

**Signing in:** only `@curiouslearning.org` accounts are accepted.
- **Web page:** the first Generate in a page visit shows a **Sign in with Google** button that opens Google in a new tab. Each run uses the access of the person who signed in. Nothing is saved to disk, so reloading the page asks again.
- **Command line:** the first run opens a browser to sign in, and the sign-in is cached in `token.json`. Delete that file to sign in again.

The individual steps (`fetch_lang_sheet.py`, `fetch_drive_audios.py`, `check_missing_audios.py`, `fetch_unity_json.py`) can be run on their own for debugging. See [CLAUDE.md](CLAUDE.md#running-the-pipeline).

## What a run does

1. Checks that both the language's sheet and its audio folder exist on Drive.
2. Reads the game-JSON URL from the language sheet and downloads `ftm_<language>.json`.
3. Downloads and converts the language's audio files.
4. Deletes audio the JSON doesn't use, and reports audio the JSON needs but that's missing. Look-alike spellings are flagged for the team to check and are never renamed.

## Repository layout

| Path | Contents |
| --- | --- |
| `language_automation/` | Pipeline scripts, Streamlit app (`app.py`), AI check, `config.json` |
| `specs/` | Spec-kit feature specs (001–004) |
| `.specify/`, `.claude/skills/` | Spec-kit templates, scripts and commands |
| `CLAUDE.md` | Detailed developer and maintainer notes |

## Secrets

`credentials.json`, `token.json`, `.env`, the AI cache and generated `lang/` data are gitignored. Keep it that way. Never hardcode credentials.
