import os
import sys

import lang_paths
from check_unused_audio import find_used_audios


def get_required_audio_names(json_path):
    """All audio filenames referenced inside the JSON (same rules as the unused-audio cleanup)."""
    return set(find_used_audios(json_path))


def check_missing_audios(lang_root, language):
    """Check which required audio files are missing in /audios."""
    # lang_root is kept for existing callers; paths always follow lang_paths' casing rule
    json_path = lang_paths.json_path(language)
    audio_folder = lang_paths.audios_dir(language)

    print(f"\n📄 Using JSON: {json_path}")
    print(f"🎧 Checking audios in: {audio_folder}\n")

    required = get_required_audio_names(json_path)

    missing = []
    for audio in required:
        audio_path = os.path.join(audio_folder, audio)
        if not os.path.exists(audio_path):
            missing.append(audio)

    # Output
    if missing:
        print("❌ Missing audio files:")
        for m in missing:
            print(" -", m)
    else:
        print("✅ All audio files are available!")

    return missing


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)

    language = sys.argv[1]
    check_missing_audios(lang_paths.LANG_ROOT, language)
