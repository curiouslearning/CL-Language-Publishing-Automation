"""
Standard spelling for look-alike Devanagari vowel signs.

ा + े (काे) renders the same as ो (को), and ा + ै the same as ौ, but they are different
characters, so the game can't match a text or audio name typed one way with a file named
the other way. The pipeline writes everything in the single standard sign (user decision,
2026-10-14), so both sides match without anyone having to retype the sheet or the Drive files.
"""
import json

SPELLING_VARIANTS = [
    ("ाे", "ो"),
    ("ाै", "ौ"),
]


def standard_spelling(text):
    """The text with look-alike sequences (e.g. ा + े) replaced by the single standard sign (ो)."""
    for variant, standard in SPELLING_VARIANTS:
        text = text.replace(variant, standard)
    return text


def _standardize(node, changes):
    if isinstance(node, str):
        fixed = standard_spelling(node)
        if fixed != node:
            changes[node] = changes.get(node, 0) + 1
        return fixed
    if isinstance(node, list):
        return [_standardize(item, changes) for item in node]
    if isinstance(node, dict):
        return {key: _standardize(value, changes) for key, value in node.items()}
    return node


def standardize_json_file(json_path):
    """
    Rewrite every string value in the JSON in the standard spelling.
    Prints one '🔤 Standard spelling: <as typed> → <standard> (<n> places)' line per distinct text.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    changes = {}
    data = _standardize(data, changes)
    if not changes:
        return {}
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=4, ensure_ascii=False))
    for text, count in changes.items():
        print(f"🔤 Standard spelling: {text} → {standard_spelling(text)} ({count} place{'s' if count != 1 else ''})")
    return changes
