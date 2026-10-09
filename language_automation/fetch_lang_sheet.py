from googleapiclient.discovery import build
import os
import sys

from fetch_unity_json import fetch_and_save_json
import google_auth
import lang_paths


def get_services():
    try:
        creds = google_auth.load_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)
        print("✅ Services initialized successfully")
        return drive_service, sheets_service
    except Exception as e:
        print("❌ Failed to initialize services:", e)
        return False

def is_exact_name(file_name, language):
    """Case-insensitive exact match; an Excel file's extension is ignored ('Hausa.xlsx' == 'hausa')."""
    name = file_name.strip()
    base, ext = os.path.splitext(name)
    if ext.lower() in (".xlsx", ".xls"):
        name = base
    return name.strip().casefold() == language.strip().casefold()


def find_language_sheet(drive_service, language):
    folder_id = "18SRLdZK-n2QismpXY1Cn-FFqrJutIU8I"
    safe_language = language.strip().replace("\\", "\\\\").replace("'", "\\'")
    # 'contains' narrows the listing (it is case-insensitive); the exact match is checked below
    query = (
        f"'{folder_id}' in parents and trashed=false "
        f"and (mimeType='application/vnd.google-apps.spreadsheet' "
        f"or mimeType='application/vnd.ms-excel' "
        f"or mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') "
        f"and name contains '{safe_language}'"
    )

    try:
        results = drive_service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=100
        ).execute()
    except Exception as e:
        print("❌ Drive files.list failed:", e)
        return False

    similar = results.get("files", [])
    files = [f for f in similar if is_exact_name(f["name"], language)]
    # debug: list files in the folder if nothing matched
    if not files:
        print(f"❌ No sheet named exactly '{language}' (any upper/lowercase) in folder {folder_id}.")
        if similar:
            print("🔎 Similar names were found but not used:")
            for f in similar:
                print(f" - {f.get('name')}")
        # try listing all files in folder for debugging
        try:
            debug_res = drive_service.files().list(
                q=f"'{folder_id}' in parents",
                fields="files(id, name, mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=200
            ).execute()
            debug_files = debug_res.get("files", [])
            print("🔎 Files in folder (for debugging):")
            for f in debug_files:
                print(f" - {f.get('name')} ({f.get('id')}) [{f.get('mimeType')}]")
        except Exception as e:
            print("❌ Failed to list folder contents for debug:", e)
        return False

    if len(files) > 1:
        print(f"⚠ {len(files)} sheets are named '{language}', using the first one:")
        for f in files:
            print(f" - {f.get('name')} ({f.get('id')}) [{f.get('mimeType')}]")

    file = files[0]
    print(f"✅ Found sheet: {file['name']} | ID: {file['id']} | MIME: {file['mimeType']}")
    return file

def convert_excel_to_google_sheet(drive_service, file_id, new_name):
    file_metadata = {
        'name': new_name,
        'mimeType': 'application/vnd.google-apps.spreadsheet'
    }
    converted_file = drive_service.files().copy(fileId=file_id, body=file_metadata).execute()
    print(f"✅ Converted Excel to Google Sheet | New ID: {converted_file['id']}")
    return converted_file['id']

# ---------------------------------------------------------
#  UNIFIED FUNCTION (called internally)
# ---------------------------------------------------------

def fetch_language_sheet(language):
    print(f"\n🔍 Processing language sheet for: {language}")

    services = get_services()
    if not services:
        raise Exception("Cannot continue — Google service init failed.")
    drive_service, sheets_service = services

    file = find_language_sheet(drive_service, language)

    if not file:
        # Stop the script immediately
        raise Exception(f"No sheet found for '{language}'. Cannot continue.")


    # Decide if conversion is needed
    if file['mimeType'] == "application/vnd.google-apps.spreadsheet":
        sheet_id = file["id"]
    else:
        sheet_id = convert_excel_to_google_sheet(
            drive_service,
            file["id"],
            f"{file['name']}_converted"
        )

    # Import unity check
    import run_unity_check
    unity_url = run_unity_check.read_unity_url_from_sheet(sheets_service, sheet_id)

    if not unity_url:
        print("❌ No Unity URL found in the sheet.")
        return False

    # Output path for json
    output_path = lang_paths.json_path(language)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"\n🌐 Fetching JSON from Unity URL...")
    fetch_and_save_json(unity_url, output_path)

    print(f"🎉 Completed: Sheet + Unity JSON fetched for {language}\n")

    return output_path


# ---------------------------------------------------------
#  COMMAND-LINE EXECUTION
# ---------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_lang_sheet.py <LanguageName>")
        sys.exit(1)

    fetch_language_sheet(sys.argv[1])