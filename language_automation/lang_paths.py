import os
import re

# One casing rule for every language path: lang/<lang.lower()>/ftm_<lang.lower()>.json.
# (Mixing as-typed and lowercased names only worked on case-insensitive Windows.)
LANG_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")

VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")


def validate_language_name(name):
    """Return the stripped name, or raise ValueError if it could escape lang/ or isn't a plain name."""
    name = (name or "").strip()
    if not VALID_NAME.match(name):
        raise ValueError(f"Invalid language name: {name!r}")
    return name


def lang_dir(lang):
    return os.path.join(LANG_ROOT, lang.strip().lower())


def json_path(lang):
    return os.path.join(lang_dir(lang), f"ftm_{lang.strip().lower()}.json")


def audios_dir(lang):
    return os.path.join(lang_dir(lang), "audios")


def images_dir(lang):
    return os.path.join(lang_dir(lang), "images")
