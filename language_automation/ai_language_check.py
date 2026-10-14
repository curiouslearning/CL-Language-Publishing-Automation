import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

import lang_paths
import ai_providers

# -------------------------------------------
# AI language check (spec 003): reads lang/<lang>/ftm_<lang>.json and reports suspected
# spelling/letter/sentence/recording problems. Advisory only: never writes lang/ or the sheet.
# One AI request per check; unchanged content reuses the cached result (no request).
# -------------------------------------------
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ai_cache")
REPORT_PREFIX = "🤖 AI report: "
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
KIND_CODES = {"LetterOnly": "L", "LetterInWord": "LW", "Word": "W", "Feedback": "F"}


def nfc(text):
    return unicodedata.normalize("NFC", (text or "").strip())


def build_items(lang):
    """Unique content items with every place they appear (750 puzzles → ~250 items)."""
    path = lang_paths.json_path(lang)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No generated game JSON for {lang}: run generate_language.py first")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    items, index = [], {}

    def add(kind, text, letters, recording, location):
        key = (kind, text, letters, recording)
        if key not in index:
            index[key] = {"id": f"i{len(items) + 1}", "kind": kind, "text": text,
                          "letters": list(letters), "recording": recording, "locations": []}
            items.append(index[key])
        index[key]["locations"].append(location)

    for level in data.get("Levels", []):
        meta = level.get("LevelMeta", {})
        for puzzle in level.get("Puzzles", []):
            prompt = puzzle.get("prompt") or {}
            add(meta.get("LevelType", "?"),
                nfc(prompt.get("PromptText")),
                tuple(nfc(s.get("StoneText")) for s in puzzle.get("targetstones", [])),
                os.path.basename((prompt.get("PromptAudio") or "").strip()),
                f"level {meta.get('LevelNumber')} puzzle {puzzle.get('SegmentNumber')}")
    for n, text in enumerate(data.get("FeedbackTexts") or [], 1):
        add("Feedback", nfc(text), (), "", f"feedback {n}")
    return items


def recording_differs(item):
    """True when the recording name isn't simply the letter/word it should play (worth sending)."""
    if not item["recording"]:
        return False
    name = nfc(os.path.splitext(item["recording"])[0]).casefold()
    expected = item["text"] if item["kind"] == "Word" else "".join(item["letters"])
    return name != nfc(expected).casefold()


def format_item_line(item):
    """Compact line sent to the AI: only what its checks need (spec FR-022)."""
    parts = [item["id"], KIND_CODES.get(item["kind"], item["kind"]), item["text"]]
    if item["kind"] == "LetterInWord":
        parts.append("target=" + "+".join(item["letters"]))
    if recording_differs(item):
        parts.append("rec=" + item["recording"])
    return " | ".join(parts)


def consistency_warnings(items):
    """Exact checks done in code, no AI: letters must spell the word / be in the word."""
    warnings = []
    for item in items:
        text, letters = item["text"], item["letters"]
        if item["kind"] == "Word" and letters and "".join(letters).casefold() != text.casefold():
            warnings.append(_warning("letters_dont_spell_word", "consistency", text, "",
                                     f"The letters {'+'.join(letters)} spell '{''.join(letters)}', not '{text}'.",
                                     "high", item["locations"]))
        elif item["kind"] == "LetterInWord":
            missing = [l for l in letters if l and l.casefold() not in text.casefold()]
            if missing:
                warnings.append(_warning("letter_not_in_word", "consistency", text, "",
                                         f"The target letter '{'+'.join(missing)}' doesn't appear in '{text}'.",
                                         "high", item["locations"]))
    return warnings


def _warning(category, source, text, suggestion, reason, confidence, locations):
    return {"category": category, "source": source, "text": text, "suggestion": suggestion,
            "reason": reason, "confidence": confidence, "locations": list(locations)}


def _location_key(location):
    return [int(n) for n in re.findall(r"\d+", location)] or [10**9]


def group_and_sort(warnings):
    """Merge identical problems (one warning, all places), then high → low, then by first place."""
    grouped = {}
    for w in warnings:
        key = (w["source"], w["category"], w["text"], w["suggestion"])
        if key in grouped:
            seen = grouped[key]["locations"]
            seen.extend(l for l in w["locations"] if l not in seen)
        else:
            grouped[key] = dict(w, locations=list(w["locations"]))
    for w in grouped.values():
        w["locations"].sort(key=_location_key)
    return sorted(grouped.values(),
                  key=lambda w: (CONFIDENCE_ORDER.get(w["confidence"], 3), _location_key(w["locations"][0]) if w["locations"] else [10**9]))


def ai_warnings(raw, items, can_judge):
    """Turn the model's item ids into locations; ids it made up are dropped."""
    by_id = {i["id"]: i for i in items}
    out = []
    for w in raw.get("warnings", []):
        ids = [i for i in w.get("item_ids", []) if i in by_id]
        if not ids:
            continue
        locations = [loc for i in ids for loc in by_id[i]["locations"]]
        confidence = w.get("confidence", "low") if can_judge else "low"
        out.append(_warning(w.get("category", "misspelled_word"), "ai", w.get("text", ""),
                            w.get("suggestion", ""), w.get("reason", ""), confidence, locations))
    return out


def token_line(model, usage):
    """One progress line with the model and its real token counts."""
    if not usage:
        return f"🤖 AI check: {model}, tokens: not reported by the API"
    thinking = f" (incl. {usage['thinking_tokens']:,} thinking)" if usage.get("thinking_tokens") else ""
    total = usage["input_tokens"] + usage["output_tokens"]
    return (f"🤖 AI check: {model}, tokens: input {usage['input_tokens']:,}, "
            f"output {usage['output_tokens']:,}{thinking}, total {total:,}")


def check_language(lang, progress=print):
    """The AI Check Result for one language (see specs/003-ai-language-check/data-model.md)."""
    items = build_items(lang)
    lines = "\n".join(format_item_line(i) for i in items)
    cfg, reason = ai_providers.load_config()
    provider = cfg["provider"]
    model = cfg.get(provider, {}).get("model", "") if provider in ai_providers.PROVIDERS else ""
    result = {
        "language": lang, "provider": provider, "model": model, "assumed_language": "",
        "status": "completed", "reason": "", "note": "", "items_total": len(items),
        "approx_tokens": (len(ai_providers.REVIEW_PROMPT) + len(lines)) // 4,
        "cached": False, "checked_at": "", "warnings": [],
        "usage": None,  # real token counts from the API (ai_providers.claude_usage / gemini_usage)
    }
    found = consistency_warnings(items)

    if reason:
        result.update(status="unavailable", reason=reason)
        result["warnings"] = group_and_sort(found)
        progress(f"⚠ AI check: unavailable: {reason}")
        return result

    progress(f"🤖 AI check: using {provider} ({model})")
    progress(f"🤖 AI check: {len(items)} items to check (~{result['approx_tokens']} tokens, 1 request)")

    cache_key = hashlib.sha256(f"{provider}|{model}|{lang.strip().lower()}|{lines}".encode("utf-8")).hexdigest()
    cache_file = os.path.join(CACHE_DIR, cache_key + ".json")
    raw = None
    if os.path.isfile(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as f:
                raw = json.load(f)
            result["cached"] = True
            progress(f"🤖 AI check: content unchanged since {raw.get('checked_at', 'an earlier check')}, "
                     "reusing earlier result (no API call)")
        except (OSError, json.JSONDecodeError):
            raw = None

    if raw is None:
        reviewer = None
        try:
            reviewer = ai_providers.make_reviewer(cfg)
            raw = reviewer.review(lang, lines)
            raw["answered_by"] = getattr(reviewer, "model_used", model)
            raw["usage"] = getattr(reviewer, "usage", None)
        except (ai_providers.Unavailable, json.JSONDecodeError, ValueError) as e:
            reason = str(e) if isinstance(e, ai_providers.Unavailable) else f"the AI's answer couldn't be read ({e})"
            result.update(status="unavailable", reason=reason)
            result["warnings"] = group_and_sort(found)
            progress(f"⚠ AI check: unavailable: {reason}")
            # An answer that came back but couldn't be used (cut off, refused, unreadable) was still billed
            if reviewer is not None and getattr(reviewer, "usage", None):
                result["model"] = getattr(reviewer, "model_used", model)
                result["usage"] = reviewer.usage
                progress(token_line(result["model"], reviewer.usage))
            return result
        raw["checked_at"] = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)

    can_judge = raw.get("can_judge", True) is not False
    if raw.get("answered_by") and raw["answered_by"] != model:
        result["model"] = raw["answered_by"]  # a fallback model answered (main model was busy)
        progress(f"⚠ AI check: {model} was busy, answered by fallback model {raw['answered_by']}")
    result["usage"] = raw.get("usage")
    if result["cached"]:
        progress("🤖 AI check: tokens used this run: 0 (cached). "
                 + (token_line(result["model"], result["usage"]).removeprefix("🤖 AI check: ")
                    .replace("tokens:", "the earlier request used:", 1) if result["usage"] else
                    "The earlier request's token counts weren't recorded."))
    else:
        progress(token_line(result["model"], result["usage"]))
    result.update(assumed_language=raw.get("assumed_language", ""), note=raw.get("note", ""),
                  checked_at=raw.get("checked_at", ""), status="completed" if can_judge else "cannot_judge")
    if not can_judge:
        result["reason"] = raw.get("note", "") or "the AI can't reliably judge this language"
    result["warnings"] = group_and_sort(found + ai_warnings(raw, items, can_judge))
    progress(f"🤖 AI check: done ({len(result['warnings'])} warnings)")
    return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print("Usage: python ai_language_check.py <LanguageName>   |   python ai_language_check.py --list-models")
        sys.exit(1)
    if sys.argv[1] == "--list-models":
        # Free lookup (no tokens): which Gemini models this key can use, to pick one for config.json
        cfg, reason = ai_providers.load_config()
        cfg["provider"] = "gemini"
        if not cfg["gemini"]["api_key"]:
            print("❌ No GEMINI_API_KEY in language_automation/.env")
            sys.exit(1)
        try:
            for name in ai_providers.GeminiReviewer(cfg["gemini"]).list_models():
                print(name)
        except ai_providers.Unavailable as e:
            print(f"❌ {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Couldn't list models: {e}")
            sys.exit(1)
        sys.exit(0)
    try:
        language = lang_paths.validate_language_name(sys.argv[1])
    except ValueError:
        print("❌ Invalid language name: use letters, digits, spaces, - or _.")
        sys.exit(1)
    try:
        report = check_language(language)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    print(REPORT_PREFIX + json.dumps(report, ensure_ascii=False), flush=True)
