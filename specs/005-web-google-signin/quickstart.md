# Quickstart & Validation: Per-Person Web Google Sign-In for the Generator

Hosting is out of scope. Every scenario below runs locally at `http://localhost:8501/`.

## Prerequisites

- **Google Cloud setup** (one-time, done by the developer with their `curiouslearning.org` account, spec Clarifications 2026-10-09):
  - Create a **new project** inside the curiouslearning.org organisation (e.g. `ftm-language-generator`); you are its Owner. Don't reuse `ftm-b9d99`.
  - Enable the **Google Drive API** and **Google Sheets API** in it.
  - OAuth consent screen (Google Auth Platform → Branding / Audience) with audience **Internal**.
  - An OAuth client of type **Web application**, with `http://localhost:8501/` (trailing slash) as an authorized redirect URI. The hosted address is added later by the hosting work.
  - Download its JSON (must start with `{"web": …}`) and save it as `language_automation/client_secret_web.json` (gitignored by `client_secret*.json`).
- **Test accounts:**
  - two `@curiouslearning.org` accounts (A and B);
  - one personal Gmail account;
  - one `@sutara.org` account.
- **Local:** `python -m pip install -r requirements.txt`, ffmpeg on PATH.

## Run locally

```bash
cd language_automation
python -m streamlit run app.py        # http://localhost:8501/
```

## Validation scenarios

After each refused or failed case, check that `lang/` is unchanged and that no `_converted` sheet copy appeared on Drive (SC-003).

| # | Scenario | Expected |
|---|---|---|
| V1 | Account A: open the page, type `Hausa`, press Generate | Box shows "Authentication in progress" + **Sign in with Google**, with no steps. Sign in in the new tab → that tab says "Signed in as A". The generator tab shows "Authenticated as A", then the steps, and the run completes. |
| V2 | Same tab: generate a second language | No sign-in button. "Authenticated as A" appears before the steps (FR-010). |
| V3 | Personal Gmail | "Authentication failed", saying only curiouslearning.org accounts may add languages. No steps, `lang/` unchanged. |
| V4 | `@sutara.org` account, with Drive access to the folders | Refused, as in V3. |
| V5 | After V3, press Generate again in the same tab | Google shows the account chooser. Choosing account A succeeds (FR-007). |
| V6 | Press Generate, then close the sign-in tab without finishing | After 3 min: "Authentication cancelled … Nothing was created or deleted". Generate is enabled again. |
| V7 | Press Generate, then close the generator tab | Lock released. Another browser can generate right away. |
| V8 | Press Generate, copy the sign-in link, and open it in a **different browser** as account B | That tab says to sign in in the same browser. The original tab never becomes "Authenticated as B" (FR-003). |
| V9 | After V1, reload the callback URL (back button or refresh) | "This sign-in link has already been used or has expired". Nothing changes in the generator tab. |
| V10 | Account A signed in in browser 1. Open the page in browser 2 and press Generate | Browser 2 must sign in. Signing in as B shows "Authenticated as B", and B's log names B (SC-004). |
| V11 | Reload the generator tab after V1, then press Generate | A sign-in is asked for again (SC-006). |
| V12 | Rename `client_secret_web.json` away, then open the page | Setup error at the top, Generate disabled, no run (FR-011). |
| V13 | Full run of a real language (`Hausa`) as account A, AI check on | Steps 1–7 complete. The Audio check summary and the missing-audio list match a CLI run of the same language. The AI check runs as before (FR-013; constitution manual check). |

## Command line is unchanged (FR-014)

```bash
cd language_automation
python generate_language.py Hausa      # desktop sign-in / token.json as before; same domain check
```

Expected: identical behaviour to before this feature. With `FTM_HOSTED=1` set and no `FTM_GOOGLE_CREDENTIALS`, it exits 1 with "no Google sign-in was provided for this run" before Step 0.
