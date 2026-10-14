import os
import json
import unicodedata

import lang_paths
from spelling import standard_spelling

ALWAYS_KEEP = ["great.mp3", "amazing.mp3"]



def normalize_audio_name(name):
    """Compare key for audio names that look identical but are typed differently."""
    return standard_spelling(unicodedata.normalize("NFC", name.strip())).casefold()


# Extract all audio names used inside the JSON
def find_used_audios(json_path):
    try:
        with open(json_path, "r", encoding="utf8") as f:
            data = json.load(f)

        used = []

        # Puzzle prompt audios
        for level in data.get("Levels", []):
            for puzzle in level.get("Puzzles", []):
                prompt = puzzle.get("prompt", {})
                if prompt.get("PromptAudio"):
                    used.append(os.path.basename(prompt["PromptAudio"].strip()))

        # Feedback audios
        for fb in data.get("FeedbackAudios", []):
            used.append(os.path.basename(fb.strip()))

        # Other audios ("Select your player", "Watch me grow", ...)
        for other in data.get("OtherAudios", {}).values():
            if other:
                used.append(os.path.basename(other.strip()))

        return list(set(used))  # unique
    except Exception as e:
        print("❌ Error reading JSON:", e)
        return []


# List actual audio files in the folder
def find_audio_files(audios_folder):
    try:
        return [
            f for f in os.listdir(audios_folder)
            if os.path.isfile(os.path.join(audios_folder, f))
        ]
    except:
        print("❌ Cannot read audios folder:", audios_folder)
        return []


# Delete unused audio files
def clean_unused_audios(lang_path, language):
    print(f"\n🧹 Checking unused audios for: {language}")

    json_path = lang_paths.json_path(language)
    audios_folder = lang_paths.audios_dir(language)

    if not os.path.exists(json_path):
        print("❌ JSON file missing:", json_path)
        return

    if not os.path.exists(audios_folder):
        print("❌ Audios folder missing:", audios_folder)
        return

    used = find_used_audios(json_path)
    existing = find_audio_files(audios_folder)

    # Required names with no exact file, keyed by their normalized spelling
    missing_by_key = {
        normalize_audio_name(u): u for u in used if u not in existing
    }

    for audio in existing:
        if audio in used or audio in ALWAYS_KEEP:
            continue

        file_path = os.path.join(audios_folder, audio)
        json_name = missing_by_key.pop(normalize_audio_name(audio), None)

        if json_name:
            # Looks like the same audio but the name is typed differently in Drive and in the sheet.
            # Never rename (or delete) it automatically: keep the file and warn so the team can check.
            print(f"🔍 Look-alike: {audio} ≈ {json_name} (kept as is, not renamed: please check the spelling)")
        else:
            os.remove(file_path)
            print(f"🗑 Deleted: {audio}")

    print("✔ Audio cleanup completed.\n")
