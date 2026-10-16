"""
Read-only access check for the language pipeline. Creates, changes and deletes nothing on Drive or in lang/.

    cd language_automation
    python check_access.py Hausa            # Google sign-in + Drive + Sheets for one language, and the Gemini key
    python check_access.py Hausa --ping     # also sends one tiny Gemini request (a few tokens) to the configured model

It uses the pipeline's own lookups (google_auth, find_language_sheet, read_unity_url_from_sheet,
find_language_audio_folder) so a pass here means generate_language.py can reach the same things.
"""
import sys

from googleapiclient.discovery import build

import ai_providers
import google_auth
import lang_paths
from fetch_drive_audios import ROOT_FOLDER_ID, find_language_audio_folder, list_all_files_recursive
from fetch_lang_sheet import find_language_sheet
from run_unity_check import read_unity_url_from_sheet

SHEET_FOLDER_ID = "18SRLdZK-n2QismpXY1Cn-FFqrJutIU8I"
ALLOWED_DOMAIN = "curiouslearning.org"
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".m4a")
GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"

results = []


def report(ok, name, detail=""):
    results.append(ok)
    print(f"{'✅' if ok else '❌'} {name}" + (f": {detail}" if detail else ""))


def http_reason(e):
    """Turn a googleapiclient HttpError into the usual fix."""
    text = str(e)
    if "has not been used in project" in text or "SERVICE_DISABLED" in text or "accessNotConfigured" in text:
        return "API not enabled in the OAuth client's Google Cloud project. " + text.split("Enable it by visiting")[0][-200:]
    if "insufficientPermissions" in text or "insufficient authentication scopes" in text.lower():
        return "token is missing a scope: delete token.json and sign in again"
    if "404" in text or "notFound" in text:
        return "not found, or this account can't see it (shared drive membership?)"
    if "403" in text:
        return "permission denied for this account"
    return text[:300]


def check_google(language):
    print("\n── Google sign-in ──")
    try:
        creds = google_auth.load_credentials()
    except Exception as e:
        report(False, "Sign-in", e)
        return
    drive = build("drive", "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)
    print(f"   scopes: {', '.join(sorted(creds.scopes or []))}")

    try:
        email = drive.about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]
    except Exception as e:
        report(False, "Drive API (about.get)", http_reason(e))
        return
    report(email.lower().endswith("@" + ALLOWED_DOMAIN), "Account", email +
           ("" if email.lower().endswith("@" + ALLOWED_DOMAIN) else f" (pipeline only accepts @{ALLOWED_DOMAIN})"))

    print("\n── Drive folders ──")
    for label, fid in (("Sheets folder", SHEET_FOLDER_ID), ("Audio root folder", ROOT_FOLDER_ID)):
        try:
            f = drive.files().get(fileId=fid, fields="name, driveId", supportsAllDrives=True).execute()
            report(True, label, f"'{f['name']}'" + (f" (shared drive {f['driveId']})" if f.get("driveId") else ""))
        except Exception as e:
            report(False, label, http_reason(e))

    print(f"\n── Language sheet: {language} ──")
    sheet = find_language_sheet(drive, language)
    if not sheet:
        report(False, "Language sheet", f"no sheet named exactly '{language}'")
    elif sheet["mimeType"] != GOOGLE_SHEET:
        report(True, "Language sheet", "Excel file: the pipeline copies it to a Google Sheet first "
               "(needs Drive write). Not read here, to keep this check read-only")
    else:
        try:
            url = read_unity_url_from_sheet(sheets, sheet["id"])
            report(bool(url), "Sheets API, metadata!D1 hyperlink", url or "no hyperlink in metadata!D1")
            if url and not str(url).startswith("https://"):
                report(False, "Unity URL", "must start with https:// (fetch_unity_json refuses anything else)")
        except Exception as e:
            report(False, "Sheets API (metadata!D1)", http_reason(e))

    print(f"\n── Audio folder: {language} ──")
    try:
        folder = find_language_audio_folder(drive, language)
    except Exception as e:
        report(False, "Audio folder", http_reason(e))
        return
    if not folder:
        report(False, "Audio folder", f"no '{language}' folder with a 'Feed the Monster' subfolder")
        return
    try:
        files = list_all_files_recursive(drive, folder)
        audio = [f for f in files if f.get("name", "").lower().endswith(AUDIO_EXT)]
        report(bool(audio), "Audio files listed", f"{len(audio)} audio files (not downloaded)")
    except Exception as e:
        report(False, "Audio file listing", http_reason(e))


def check_gemini(ping):
    print("\n── Gemini API key ──")
    cfg, reason = ai_providers.load_config()
    print(f"   provider in config.json: {cfg['provider']}")
    g = cfg["gemini"]
    if not g["api_key"]:
        report(False, "GEMINI_API_KEY", "not set in language_automation/.env")
        return
    try:
        reviewer = ai_providers.GeminiReviewer(g)
        models = reviewer.list_models()
    except Exception as e:
        msg = str(e)
        if "API_KEY_INVALID" in msg or "API key not valid" in msg:
            msg = "key rejected (wrong, deleted, or restricted to other APIs/IPs)"
        elif "SERVICE_DISABLED" in msg or "has not been used" in msg:
            msg = "Generative Language API is disabled in the key's Google Cloud project"
        report(False, "Gemini key (list models, free)", msg[:300])
        return
    report(True, "Gemini key (list models, free)", f"{len(models)} models available")
    for m in [g["model"]] + list(g.get("fallback_models") or []):
        report(m in models, f"   model '{m}'", "available" if m in models else "NOT available to this key")

    if ping:
        try:
            resp = reviewer.client.models.generate_content(
                model=g["model"], contents="Reply with the single word OK.",
                config={"max_output_tokens": 50, "automatic_function_calling": {"disable": True}})
            u = resp.usage_metadata
            report(True, "Gemini request", f"{g['model']} answered '{(resp.text or '').strip()[:20]}' "
                   f"(tokens in {u.prompt_token_count}, out {u.candidates_token_count})")
        except Exception as e:
            report(False, "Gemini request", str(e)[:300])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("Usage: python check_access.py <LanguageName> [--ping]")
        sys.exit(2)
    language = args[0]
    try:
        lang_paths.validate_language_name(language)
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(2)

    check_google(language)
    check_gemini("--ping" in sys.argv)

    failed = results.count(False)
    print(f"\n{'✅ All checks passed' if not failed else f'❌ {failed} check(s) failed'}")
    sys.exit(1 if failed else 0)
