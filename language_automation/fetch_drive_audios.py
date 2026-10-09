import os
import re
import sys
import io
import json
import subprocess
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import google_auth
import lang_paths

ROOT_FOLDER_ID = "1ObyoMA9MoTjgMbldRJWDun1wajJ78zRu"


# ------------------------------------------------------------
# AUTH (google_auth: this run's web sign-in, or token.json on the command line)
# ------------------------------------------------------------
def get_drive_service():
    return build("drive", "v3", credentials=google_auth.load_credentials())


# ------------------------------------------------------------
# LIST FOLDERS IN A PARENT
# ------------------------------------------------------------
def list_folders(service, parent_id):
    query = (
        f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    folders = []
    page_token = None

    while True:
        resp = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=200,
            )
            .execute()
        )
        folders.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return folders


def search_folder(service, parent_id, name, exact=False):
    """exact=True: whole name must match (any upper/lowercase). Otherwise a substring match."""
    folders = list_folders(service, parent_id)
    wanted = name.strip().casefold()
    for f in folders:
        folder_name = f["name"].strip().casefold()
        if (folder_name == wanted) if exact else (wanted in folder_name):
            return f["id"]

    if exact:
        similar = [f["name"] for f in folders if wanted in f["name"].casefold()]
        if similar:
            print(f"🔎 No folder named exactly '{name}'. Similar names were found but not used:")
            for s in similar:
                print(f" - {s}")
    return None


# ------------------------------------------------------------
# RECURSIVE FILE SCAN
# ------------------------------------------------------------
def list_all_files_recursive(service, folder_id):
    all_files = []
    queue = [folder_id]

    while queue:
        current = queue.pop(0)
        query = f"'{current}' in parents and trashed=false"
        page_token = None

        while True:
            resp = (
                service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageSize=200,
                )
                .execute()
            )

            for item in resp["files"]:
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    queue.append(item["id"])
                else:
                    all_files.append(item)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return all_files


# ------------------------------------------------------------
# OPTIMIZED DOWNLOAD + CONVERT
# ------------------------------------------------------------
def download_convert_to_mp3(service, file_obj, output_dir):
    file_id = file_obj["id"]
    original = file_obj["name"]
    # Drive names are untrusted: a name like "..\..\x.wav" or "C:\x.wav" must not escape output_dir
    name = os.path.basename(original.replace("\\", "/"))
    ext = os.path.splitext(name)[1].lower()
    base = INVALID_NAME_CHARS.sub("_", os.path.splitext(name)[0]).strip()
    if base in ("", ".", ".."):
        print(f"❌ Skipped unsafe file name: {original}")
        return False

    output_mp3 = os.path.join(output_dir, base + ".mp3")
    root = os.path.realpath(output_dir)
    if os.path.dirname(os.path.realpath(output_mp3)) != root:
        print(f"❌ Skipped unsafe file name: {original}")
        return False

    # --------------------------------------------------------
    # 1. SKIP IF MP3 ALREADY EXISTS
    # --------------------------------------------------------
    if os.path.exists(output_mp3):
        print(f"⏩ Skipped (already exists): {output_mp3}")
        return True

    # --------------------------------------------------------
    # 2. DOWNLOAD WITH RETRY (avoids 10054 connection resets)
    # --------------------------------------------------------
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()

    retries = 5
    for attempt in range(retries):
        try:
            downloader = MediaIoBaseDownload(
                buf,
                request,
                chunksize=1024 * 256  # 256 KB prevents resets
            )
            done = False
            while not done:
                _, done = downloader.next_chunk()
            break  # success → exit retry loop
        except Exception as e:
            print(f"⚠ Download error (attempt {attempt+1}/{retries}): {name}")
            print(str(e))
            if attempt == retries - 1:
                print("❌ Failed after retries. Skipping file.")
                return False
            continue

    print(f"⬇ Downloaded: {name} → buffer")

    # --------------------------------------------------------
    # 3. IF FILE IS ALREADY MP3, SAVE DIRECTLY
    # --------------------------------------------------------
    if ext == ".mp3":
        with open(output_mp3, "wb") as f:
            f.write(buf.getvalue())
        print(f"📄 Saved MP3: {output_mp3}")
        return True

    # --------------------------------------------------------
    # 4. SAVE TEMP FILE & RUN FFMPEG CONVERSION
    # --------------------------------------------------------
    temp_input = os.path.join(output_dir, base + ext)
    with open(temp_input, "wb") as f:
        f.write(buf.getvalue())

    cmd = [
        "ffmpeg", "-y",
        "-i", temp_input,
        "-vn",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "192k",
        output_mp3
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=False
    )
    

    os.remove(temp_input)

    if result.returncode != 0:
        print(f"❌ FFmpeg conversion error: {name}")
        print(result.stderr)
        return False

    print(f"🎵 Converted to MP3: {output_mp3}")
    return True


# ------------------------------------------------------------
# DRIVE LINKS INSIDE THE JSON
# (e.g. FeedbackAudios: "https://drive.google.com/file/d/<id>/view?usp=sharing")
# ------------------------------------------------------------
DRIVE_ID_RE = re.compile(r"(?:drive|docs)\.google\.com/.*?(?:/d/|[?&]id=)([A-Za-z0-9_-]{10,})")
INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def drive_file_id(value):
    """Return the Drive file id if value is a Drive link, else None."""
    if not isinstance(value, str):
        return None
    match = DRIVE_ID_RE.search(value)
    return match.group(1) if match else None


def iter_json_strings(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from iter_json_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_json_strings(v)
    elif isinstance(node, str):
        yield node


def replace_json_strings(node, mapping):
    if isinstance(node, dict):
        return {k: replace_json_strings(v, mapping) for k, v in node.items()}
    if isinstance(node, list):
        return [replace_json_strings(v, mapping) for v in node]
    if isinstance(node, str) and node in mapping:
        return mapping[node]
    return node


def find_json_drive_links(json_path):
    """Map every Drive link string in the JSON to its Drive file id."""
    with open(json_path, "r", encoding="utf8") as f:
        data = json.load(f)
    return {s: drive_file_id(s) for s in iter_json_strings(data) if drive_file_id(s)}


def audio_url_prefix(data):
    """Base URL the other audios use, e.g. https://feedthemonster.curiouscontent.org/lang/hausa/audios/"""
    for s in iter_json_strings(data):
        s = s.strip()
        if s.startswith("http") and s.lower().endswith(".mp3") and not drive_file_id(s):
            return s.rsplit("/", 1)[0] + "/"
    return ""


def download_json_drive_links(lang_path, language):
    """
    Download every Google Drive link referenced in ftm_<language>.json into
    <lang_path>/audios as mp3, then rewrite those links in the JSON to the
    downloaded file name so the unused / missing audio checks can match them.
    """
    json_path = lang_paths.json_path(language)
    audios_folder = lang_paths.audios_dir(language)

    with open(json_path, "r", encoding="utf8") as f:
        data = json.load(f)

    links = find_json_drive_links(json_path)
    print(f"🔗 Found {len(links)} Google Drive link(s) in the JSON.")

    service = get_drive_service()
    prefix = audio_url_prefix(data)
    os.makedirs(audios_folder, exist_ok=True)

    mapping = {}      # original string -> rewritten URL
    downloaded = {}   # drive file id -> mp3 name
    used_names = {}   # mp3 name -> drive file id
    failed = 0

    for original, file_id in links.items():
        if file_id in downloaded:
            mapping[original] = prefix + downloaded[file_id]
            continue

        try:
            meta = service.files().get(
                fileId=file_id, fields="id, name", supportsAllDrives=True
            ).execute()
        except Exception as e:
            print(f"❌ Cannot access Drive link (check sharing permissions): {original.strip()}")
            print(str(e))
            failed += 1
            continue

        base, ext = os.path.splitext(meta["name"].strip())
        base = INVALID_NAME_CHARS.sub("_", base).strip()
        # Two different links with the same Drive file name must not overwrite each other
        if base + ".mp3" in used_names:
            base = f"{base}_{file_id[:6]}"
        mp3_name = base + ".mp3"

        # The JSON explicitly points at this file, so it replaces a same-named audio from the folder fetch
        output_mp3 = os.path.join(audios_folder, mp3_name)
        if os.path.exists(output_mp3):
            print(f"♻ Replacing {mp3_name} with the file linked in the JSON")
            os.remove(output_mp3)

        print(f"🔗 {original.strip()} → {mp3_name}")
        if not download_convert_to_mp3(service, {"id": file_id, "name": base + ext}, audios_folder):
            print(f"❌ Failed to download Drive link: {original.strip()}")
            failed += 1
            continue

        downloaded[file_id] = mp3_name
        used_names[mp3_name] = file_id
        mapping[original] = prefix + mp3_name

    if mapping:
        data = replace_json_strings(data, mapping)
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=4, ensure_ascii=False))
        print(f"📝 Replaced {len(mapping)} Drive link(s) in {json_path}")

    if failed:
        print(f"❌ {failed} Drive link(s) could not be downloaded.")
        return False

    print("✅ Drive links downloaded.")
    return True


# ------------------------------------------------------------
# MAIN ENTRY
# ------------------------------------------------------------
def find_language_audio_folder(service, lang):
    """Drive id of <ROOT>/<lang>/Feed the Monster, or None if the language has no audio folder."""
    # Locate language folder
    lang_folder_id = search_folder(service, ROOT_FOLDER_ID, lang, exact=True)
    if not lang_folder_id:
        print(f"❌ Language folder not found: {lang}")
        return None

    # Locate "Feed the Monster"
    feed_folder_id = search_folder(service, lang_folder_id, "Feed the Monster")
    if not feed_folder_id:
        print("❌ 'Feed the Monster' folder not found.")
        return None

    return feed_folder_id


def main_wrapper(lang, silent=True):
    service = get_drive_service()
    if not service:
        return False

    feed_folder_id = find_language_audio_folder(service, lang)
    if not feed_folder_id:
        return False

    output_dir = lang_paths.audios_dir(lang)
    os.makedirs(output_dir, exist_ok=True)

    # Scan recursively
    all_files = list_all_files_recursive(service, feed_folder_id)
    audio_files = [
        f for f in all_files if f["name"].lower().endswith((".mp3", ".wav", ".ogg", ".m4a"))
    ]

    print(f"🎵 Total audio files found: {len(audio_files)}")

    # PROCESS FILES
    for file_obj in audio_files:
        download_convert_to_mp3(service, file_obj, output_dir)

    print("✅ Audio fetch complete.")
    return True


def run_audio_fetch(lang):
    return main_wrapper(lang, silent=False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_drive_audios.py <LanguageName>")
        sys.exit(1)
    main_wrapper(sys.argv[1], silent=False)
