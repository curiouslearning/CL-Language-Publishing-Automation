import os
import sys
import shutil

import lang_paths
from fetch_lang_sheet import fetch_language_sheet, get_services, find_language_sheet
from fetch_drive_audios import (
    run_audio_fetch, find_json_drive_links, download_json_drive_links,
    get_drive_service, find_language_audio_folder,
)
from check_unused_audio import clean_unused_audios
from check_missing_audios import check_missing_audios

ALLOWED_DOMAIN = "curiouslearning.org"


# -------------------------------------------
# 🔐 Google sign-in (credentials.json → token.json), before anything else.
#    app.py shows "Authentication in progress" until "✅ Authenticated as" is printed.
# -------------------------------------------
def authenticate():
    print("🔐 Authenticating with Google...")

    services = get_services()
    if not services:
        print("❌ Authentication failed: Google service init failed.")
        print("❌ Nothing was created or deleted.")
        sys.exit(1)
    drive_service, _ = services
    get_drive_service()  # audio download scope, same token.json

    email = drive_service.about().get(fields="user(emailAddress)").execute()["user"]["emailAddress"]
    if not email.lower().endswith("@" + ALLOWED_DOMAIN):
        # Forget this account so the next run asks for sign-in again
        if os.path.exists("token.json"):
            os.remove("token.json")
        print(f"❌ Only Curious Learning ({ALLOWED_DOMAIN}) accounts can generate languages. Signed in as {email}.")
        print("❌ Nothing was created or deleted.")
        sys.exit(1)

    print(f"✅ Authenticated as {email}\n")
    return drive_service


# -------------------------------------------
# 🔎 Make sure the language exists on Drive before touching lang/
# -------------------------------------------
def verify_language_on_drive(drive_service, lang_name):
    print(f"🔎 Checking Google Drive for: {lang_name}")

    def not_found(reason):
        print(f"❌ Language '{lang_name}' was not found on Google Drive ({reason}).")
        print("❌ Nothing was created or deleted. Check the spelling of the language name.")
        sys.exit(1)

    if not find_language_sheet(drive_service, lang_name):
        not_found("no language sheet")

    if not find_language_audio_folder(get_drive_service(), lang_name):
        not_found("no audio folder")

    print(f"✅ '{lang_name}' found on Google Drive (sheet and audio folder).\n")


# -------------------------------------------
# 🔥 UTILITY: Clean existing language folder before running
# -------------------------------------------
def clean_existing_folder(lang_name):
    lang_path = lang_paths.lang_dir(lang_name)

    if os.path.exists(lang_path):
        print(f"🧹 Cleaning old language folder: {lang_path}")
        try:
            shutil.rmtree(lang_path)
        except Exception as e:
            print("❌ Failed to clean old folder.")
            print(str(e))
            sys.exit(1)

    print("🧼 Clean state ready.\n")


# -------------------------------------------
# 📁 Create folder structure
# -------------------------------------------
def create_language_folder(lang_name):
    lang_path = lang_paths.lang_dir(lang_name)

    try:
        os.makedirs(lang_paths.audios_dir(lang_name))
        os.makedirs(lang_paths.images_dir(lang_name))

        print(f"📁 Created folder structure:")
        print(f"   - {lang_path}")
        print(f"   - {lang_paths.audios_dir(lang_name)}")
        print(f"   - {lang_paths.images_dir(lang_name)}")

        return lang_path

    except Exception as e:
        print("❌ ERROR: Failed creating folders.")
        print(str(e))
        sys.exit(1)


# -------------------------------------------
# 📝 Fetch Language Sheet
# -------------------------------------------
def run_fetch_lang_sheet_internal(lang_name):
    print(f"\n🚀 Fetching language sheet internally for: {lang_name}...\n")
    try:
        fetch_language_sheet(lang_name)
        print("✅ Language sheet fetched successfully.\n")
    except Exception as e:
        print("❌ ERROR while fetching language sheet.")
        print(str(e))
        sys.exit(1)  # STOP execution here


# =========================================================
# 🚀 MAIN SCRIPT
# =========================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ ERROR: Please provide a language name.")
        print("Usage: python generate_language.py <LanguageName>")
        sys.exit(1)

    try:
        lang_name = lang_paths.validate_language_name(sys.argv[1])
    except ValueError:
        print("❌ Invalid language name: use letters, digits, spaces, - or _.")
        sys.exit(1)

    print(f"🔧 Initializing language automation for: {lang_name}")

    # -------------------------------------------
    # 🔐 Sign in with Google (only Curious Learning accounts)
    # -------------------------------------------
    drive_service = authenticate()

    # -------------------------------------------
    # 🔎 Step 0: Language must exist on Drive (no folder is created/wiped otherwise)
    # -------------------------------------------
    verify_language_on_drive(drive_service, lang_name)

    # -------------------------------------------
    # 🧹 Step 0b: Clean environment
    # -------------------------------------------
    print("🧽 Preparing a clean language folder...")
    clean_existing_folder(lang_name)

    # -------------------------------------------
    # 📁 Step 1: Create folders fresh
    # -------------------------------------------
    lang_path = create_language_folder(lang_name)

    # -------------------------------------------
    # 📝 Step 2: Fetch language sheet
    # -------------------------------------------
    run_fetch_lang_sheet_internal(lang_name)

    # -------------------------------------------
    # 🔊 Step 3: Fetch audios
    # -------------------------------------------
    print("🎵 Fetching audio files from Drive...\n")
    success = run_audio_fetch(lang_name)

    if not success:
        print("❌ Audio fetch failed. Stopping script.")
        sys.exit(1)

    print("✅ Audio fetch completed successfully.\n")

    # -------------------------------------------
    # 🔗 Step 3b: Download audios the JSON links to directly on Drive
    #    (only runs if the JSON has Drive links instead of audio file names)
    # -------------------------------------------
    json_path = lang_paths.json_path(lang_name)
    if os.path.exists(json_path) and find_json_drive_links(json_path):
        print("🔗 Downloading audios linked from Drive in the JSON...\n")
        try:
            download_json_drive_links(lang_path, lang_name)
        except Exception as e:
            print("❌ Failed while downloading Drive links from the JSON.")
            print(str(e))
            sys.exit(1)
        print()

    # -------------------------------------------
    # 🧹 Step 4: Remove unused audios
    # -------------------------------------------
    try:
        clean_unused_audios(lang_path, lang_name)
    except Exception as e:
        print("❌ Failed while cleaning unused audios.")
        print(str(e))
        sys.exit(1)

    # -------------------------------------------
    # 🔍 Step 5: Check missing audios
    # -------------------------------------------
    try:
        print("\n🔍 Checking for missing audios...")
        check_missing_audios(lang_paths.LANG_ROOT, lang_name)
    except Exception as e:
        print("❌ Failed while checking missing audios.")
        print(str(e))
        sys.exit(1)

    print("\n🚀 All steps completed successfully! 🎉")
