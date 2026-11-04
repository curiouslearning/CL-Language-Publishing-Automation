"""
Server-side state for the web page (spec 012; packages from spec 008): the one-run lock and which run
produced each lang/<language>/ folder.

The page fetches a run's package (zip) into the browser tab right after the run, using the run's
package_id (random, unguessable). On the hosted server (FTM_HOSTED=1) the folder is then deleted;
a package nobody fetches is deleted UNFETCHED_TTL seconds after its run. Locally nothing is deleted.
All state is in-process: the server runs as one process (Cloud Run --max-instances=1).
"""
import io
import os
import shutil
import threading
import time
import uuid
import zipfile

import google_auth
import lang_paths

UNFETCHED_TTL = 600  # hosted: an unfetched package is deleted 10 minutes after its run

# One run at a time across all tabs and users: every run wipes lang/<language>/
run_lock = threading.Lock()


class Unavailable(Exception):
    """The package isn't the one this run produced any more. The message is shown on the page."""


# lang key → {"package_id", "lang", "active", "ok", "finished_at", "previous"}
_entries = {}
# Every language a run in THIS process has claimed. Cleanup only ever deletes these: a folder that was
# already there when the process started (a developer's lang/ with FTM_HOSTED=1 set) is never touched.
_claimed = set()
_lock = threading.Lock()
_janitor_started = False


def _key(lang):
    return lang.strip().lower()


def claim(lang):
    """A run is about to (re)build lang/<lang>/. Returns the new package_id."""
    package_id = uuid.uuid4().hex
    with _lock:
        key = _key(lang)
        previous = _entries.get(key)
        _claimed.add(key)
        _entries[key] = {"package_id": package_id, "lang": lang.strip(), "active": True, "ok": False,
                         "finished_at": None, "previous": previous}
    return package_id


def finish(lang, package_id, touched, ok):
    """
    The run has ended (any outcome). touched=False: it stopped before the folder was wiped, so the
    earlier run keeps it. ok: the pipeline finished and the game JSON exists (a package to offer).
    """
    with _lock:
        key = _key(lang)
        entry = _entries.get(key)
        if not entry or entry["package_id"] != package_id:
            return
        previous = entry.pop("previous", None)
        if touched:
            entry.update(active=False, ok=ok and os.path.isfile(lang_paths.json_path(lang)),
                         finished_at=time.monotonic())
        elif previous:
            _entries[key] = previous
        else:
            del _entries[key]  # a folder no run owns: the hosted janitor removes it


def _find(package_id):
    for key, entry in _entries.items():
        if entry["package_id"] == package_id:
            return key, entry
    return None, None


def build_zip(package_id):
    """
    (lang, zip bytes) for that run's package: <lang>/ftm_<lang>.json, <lang>/audios/…, <lang>/images/
    (mp3s aren't recompressed). Raises Unavailable. Hosted: the folder is deleted once zipped.
    """
    with _lock:
        key, entry = _find(package_id)
        if not entry:
            raise Unavailable("This package is no longer on the server. Generate the language again to get it.")
        if entry["active"]:
            raise Unavailable("This language is being generated again right now.")
        if not entry["ok"] or not os.path.isfile(lang_paths.json_path(entry["lang"])):
            raise Unavailable("This package is no longer on the server. Generate the language again to get it.")
        lang = entry["lang"]
        # Zip under the lock: a new run of this language can't wipe the folder halfway (it waits on claim)
        root = lang_paths.lang_dir(lang)
        top = os.path.basename(root)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr(f"{top}/", b"")
            zf.writestr(f"{top}/images/", b"")  # kept even when empty, like a local build
            for folder, _, files in os.walk(root, followlinks=False):
                for name in sorted(files):
                    path = os.path.join(folder, name)
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    rel = os.path.relpath(path, root).replace(os.sep, "/")
                    zf.write(path, f"{top}/{rel}")
        if google_auth.is_hosted() and _remove(key, "downloaded"):
            del _entries[key]
            _claimed.discard(key)
    return lang, buffer.getvalue()


def existing_audio_count(lang):
    """Local only: number of mp3s if lang/<lang>/ has its game JSON and audios, else 0."""
    audios = lang_paths.audios_dir(lang)
    if not os.path.isfile(lang_paths.json_path(lang)) or not os.path.isdir(audios):
        return 0
    return len([f for f in os.listdir(audios) if f.lower().endswith(".mp3")])


def _log(text):
    """Server log line (Cloud Logging). Never lets a console that can't print emoji stop a cleanup."""
    try:
        print(text, flush=True)
    except (UnicodeEncodeError, OSError):
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def _remove(name, why):
    try:
        shutil.rmtree(os.path.join(lang_paths.LANG_ROOT, name))
        _log(f"🧹 Cleaned up lang/{name} ({why})")
        return True
    except FileNotFoundError:
        return True
    except OSError as e:
        _log(f"⚠ Cleanup failed for lang/{name}: {e}")
        return False


def sweep(now, ttl=UNFETCHED_TTL):
    """One hosted cleanup pass: packages nobody fetched within ttl seconds, and folders no run owns."""
    removed = []
    with _lock:
        for key, entry in list(_entries.items()):
            if entry["active"] or now - entry["finished_at"] < ttl:
                continue  # never under a running pipeline
            if _remove(key, "not downloaded"):
                del _entries[key]
                _claimed.discard(key)
                removed.append(key)
        if not run_lock.locked():  # a folder claimed by a running pipeline is in _entries; be safe anyway
            for name in sorted(_claimed - set(_entries)):
                if not os.path.isdir(os.path.join(lang_paths.LANG_ROOT, name)):
                    _claimed.discard(name)
                elif _remove(name, "no owner"):
                    _claimed.discard(name)
                    removed.append(name)
    return removed


def start_janitor(interval=30, ttl=UNFETCHED_TTL):
    """Hosted only: run sweep() every `interval` seconds on a daemon thread. Only the first call starts it."""
    global _janitor_started
    with _lock:
        if _janitor_started:
            return
        _janitor_started = True

    def loop():
        while True:
            time.sleep(interval)
            try:
                sweep(time.monotonic(), ttl)
            except Exception as e:  # keep cleaning up after an unexpected error
                _log(f"⚠ Cleanup pass failed: {type(e).__name__}: {e}")

    threading.Thread(target=loop, name="package-janitor", daemon=True).start()
