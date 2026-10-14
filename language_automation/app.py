import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime

import streamlit as st
from streamlit.runtime import Runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx

import ai_providers
import lang_paths
import web_signin

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(APP_DIR, "generate_language.py")
AI_CHECK = os.path.join(APP_DIR, "ai_language_check.py")
AI_REPORT = "🤖 AI report: "

# -------------------------------------------
# Markers printed by generate_language.py → step shown in the UI
# (marker, label, optional: only listed once the pipeline reaches it)
# -------------------------------------------
STEPS = [
    ("🔎 Checking Google Drive for", "Step 1/7 · Find the language on Google Drive", False),
    ("🧽 Preparing a clean language folder", "Step 2/7 · Prepare a clean language folder", False),
    ("📁 Created folder structure", "Step 3/7 · Create folders", False),
    ("🚀 Fetching language sheet", "Step 4/7 · Fetch the language sheet and game JSON", False),
    ("🎵 Fetching audio files", "Step 5/7 · Download audio files from Drive", False),
    ("🔗 Downloading audios linked from Drive", "Step 5b/7 · Download audios the JSON links to on Drive", True),
    ("🧹 Checking unused audios", "Step 6/7 · Remove unused audio files", False),
    ("🔍 Checking for missing audios", "Step 7/7 · Check for missing audio files", False),
]
# The pipeline prints this once it has checked this run's Google sign-in (web_signin.py);
# steps are only shown after it
AUTH_DONE = "✅ Authenticated as "
MISSING_HEADER = "❌ Missing audio files:"
DONE_MARKER = "🚀 All steps completed successfully"

# Exactly one of these is printed per audio file by download_convert_to_mp3
# ("⬇ Downloaded" is not one: it is followed by "📄 Saved MP3" or "🎵 Converted")
AUDIO_FILE_DONE = re.compile(
    r"^(?:⏩ Skipped \(already exists\): |📄 Saved MP3: |🎵 Converted to MP3: |❌ FFmpeg conversion error: |❌ Failed after retries|❌ Skipped unsafe file name: )(.*)$"
)
AUDIO_TOTAL = re.compile(r"^(?:🎵 Total audio files found: |🔗 Found )(\d+)")
REFRESH_SECONDS = 0.2
# A Google sign-in nobody completes (tab closed) would otherwise block the run forever
SIGNIN_TIMEOUT_SECONDS = web_signin.SIGNIN_TIMEOUT_SECONDS
SIGNIN_PROMPT = "Please visit this URL to authorize"
# STEPS index of "Prepare a clean language folder": before it, nothing on disk was touched
WIPE_STEP = 1


def session_is_open():
    """False once the browser tab that started this run has been closed."""
    ctx = get_script_run_ctx()
    if ctx is None or not Runtime.exists():
        return True
    return Runtime.instance().is_active_session(ctx.session_id)


def session_alive(session_id):
    """True while the browser tab of that Streamlit session is still connected."""
    return Runtime.exists() and Runtime.instance().is_active_session(session_id)


@st.cache_resource
def pipeline_lock():
    # One run at a time: every run wipes lang/<language>/.
    return threading.Lock()


def wait_for_signin(auth_box):
    """
    Web Google sign-in for this page session (spec 005). Shows the sign-in button and waits for
    the sign-in tab's outcome. Returns ("success", None), ("error", reason) or ("cancelled", reason).
    On success the sign-in is kept in st.session_state.google_signin, never on disk.
    """
    session_id = get_script_run_ctx().session_id
    state, nonce, url = web_signin.start_signin(SIGNIN_CONFIG, session_id)
    secure = "; Secure" if SIGNIN_CONFIG["redirect_uri"].startswith("https://") else ""
    with auth_box.container():
        st.warning(
            "🔐 Authentication in progress: please sign in with your Curious Learning Google account. "
            "The sign-in opens in a new tab. "
            f"The run is cancelled if sign-in isn't completed within {SIGNIN_TIMEOUT_SECONDS // 60} minutes."
        )
        st.link_button("Sign in with Google", url, type="primary")
        # Ties the sign-in to this browser (fixed script; the nonce is URL-safe random text)
        st.html(f"<script>document.cookie = '{web_signin.COOKIE_NAME}={nonce}; Path=/; "
                f"SameSite=Lax; Max-Age=600{secure}';</script>", unsafe_allow_javascript=True)

    started = time.monotonic()
    try:
        while True:
            current = web_signin.get_status(state)
            if current in web_signin.FINAL:
                break
            if current == "expired" or time.monotonic() - started > SIGNIN_TIMEOUT_SECONDS:
                return "cancelled", "Google sign-in wasn't completed"
            if not session_is_open():
                return "cancelled", "The browser tab was closed"
            time.sleep(REFRESH_SECONDS)

        entry = web_signin.pop_result(state, session_id)
        if not entry:
            return "error", web_signin.REASON_FAILED
        if entry["status"] != "success":
            st.session_state.pop("google_signin", None)
            return "error", entry["reason"]
        st.session_state.google_signin = {
            "email": entry["email"],
            "info": entry["credentials_info"],
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return "success", None
    finally:
        web_signin.discard(state)  # no-op once popped; drops an abandoned request


def render_signin_callback():
    """The sign-in tab Google redirected to: finish the sign-in, say where to go next, draw nothing else."""
    st.title("🌍 Feed the Monster · Language Generator")
    if SIGNIN_CONFIG is None:
        st.error(f"Google sign-in isn't set up on this server: {SIGNIN_SETUP_ERROR}.")
    else:
        params = {key: st.query_params.get(key) for key in ("state", "code", "error")}
        kind, message = web_signin.handle_callback(
            SIGNIN_CONFIG, params, st.context.cookies.get(web_signin.COOKIE_NAME), session_alive)
        (st.success if kind == "success" else st.error)(message)
    st.query_params.clear()  # a reload must not replay the code
    st.stop()


def run_pipeline(lang, after=None):
    """
    Run generate_language.py for one language, streaming its output into the UI.
    after(result, status): optional extra step (the AI check) run before the summary is drawn.
    """
    result = {
        "lang": lang,
        "started": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "authenticated": False,
        "log": [],
        "errors": [],
        "missing": [],
        "deleted": [],
        "renamed": [],
        "unused_checked": False,
        "missing_checked": False,
        "state": "running",
    }

    status = st.status(f"**{lang}** · Authentication in progress…", expanded=True)
    with status:
        auth_box = st.empty()
        steps_box = st.empty()
        note = st.empty()
        errors_box = st.empty()
        log_view = st.container(height=320, autoscroll=True).empty()

    # UI state, updated per output line and drawn every REFRESH_SECONDS
    ui = {
        "step": None,           # index into STEPS
        "reached": set(),
        "details": {},          # step index → progress text ("165/165 files")
        "note": None,           # (kind, text) shown under the steps / during sign-in
        "auth": ("info", "🔐 Authentication in progress…"),
        "in_missing_list": False,
        "audio_total": None,
        "audio_done": 0,
        "signin_since": None,   # monotonic time the pipeline started waiting for Google sign-in
    }

    def render_steps(final_state=None):
        if not result["authenticated"]:
            return  # no steps on screen until Google sign-in succeeded
        lines = []
        for i, (_, label, optional) in enumerate(STEPS):
            if optional and i not in ui["reached"]:
                continue
            detail = f" · {ui['details'][i]}" if i in ui["details"] else ""
            if ui["step"] is not None and i < ui["step"] or (i == ui["step"] and final_state == "complete"):
                icon = "✅"
            elif i == ui["step"]:
                icon = "❌" if final_state == "error" else "⏳"
            else:
                icon = "⬜"
            lines.append(f"{icon} {label}{detail}")
        result["steps_md"] = "  \n".join(lines)  # kept so the finished run can be shown again
        steps_box.markdown(result["steps_md"])

    def render():
        kind, text = ui["auth"]
        getattr(auth_box, kind)(text)
        render_steps()
        if ui["note"]:
            kind, text = ui["note"]
            getattr(note, kind)(text)
        if result["authenticated"]:
            log_view.code("\n".join(result["log"]), language=None)

    def handle(line):
        result["log"].append(line)
        stripped = line.strip()

        # Step changes
        for i, (marker, label, _) in enumerate(STEPS):
            if stripped.startswith(marker):
                ui["step"] = i
                ui["reached"].add(i)
                ui["in_missing_list"] = False
                ui["audio_total"] = None
                ui["audio_done"] = 0
                ui["note"] = ("info", f"⏳ {label}")
                status.update(label=f"**{lang}** · {label}", expanded=True)

        # Desktop sign-in prompt of the command-line flow (google_auth, token.json). The page itself
        # signs in with web_signin before the pipeline starts, so this only appears if that changes.
        if ui["signin_since"] and not stripped.startswith(SIGNIN_PROMPT):
            ui["signin_since"] = None  # the pipeline moved on, so sign-in completed
        if stripped.startswith(SIGNIN_PROMPT):
            ui["signin_since"] = time.monotonic()
            auth_url = stripped.split(": ", 1)[-1]
            ui["auth"] = (
                "warning",
                "🔐 Authentication in progress: please sign in with your Curious Learning Google account. "
                f"A browser tab should have opened. If it didn't, [open the sign-in page]({auth_url}). "
                f"The run is cancelled if sign-in isn't completed within {SIGNIN_TIMEOUT_SECONDS // 60} minutes.",
            )

        # Signed in: from here on the steps and the log are shown
        if stripped.startswith(AUTH_DONE):
            result["authenticated"] = True
            ui["auth"] = ("success", f"✅ Authenticated as {stripped[len(AUTH_DONE):]}")
            status.update(label=f"**{lang}** · Authenticated", expanded=True)

        # Audio download progress (Step 5 and 5b), counted once per file
        total = AUDIO_TOTAL.match(stripped)
        done = AUDIO_FILE_DONE.match(stripped)
        if total and ui["step"] is not None:
            ui["audio_total"] = int(total.group(1))
            ui["details"][ui["step"]] = f"0/{ui['audio_total']} files"
            ui["note"] = ("info", f"⏳ Found {ui['audio_total']} audio file(s) on Drive, downloading…")
        elif done and ui["audio_total"]:
            ui["audio_done"] += 1
            name = os.path.basename(done.group(1).strip()) or "(failed file)"
            ui["details"][ui["step"]] = f"{ui['audio_done']}/{ui['audio_total']} files"
            ui["note"] = ("info", f"⏳ Downloading audio files… {ui['audio_done']}/{ui['audio_total']} · {name}")

        # Unused audio cleanup (Step 6)
        if stripped.startswith("🗑 Deleted: "):
            result["deleted"].append(stripped[len("🗑 Deleted: "):])
        elif stripped.startswith("🔤 Standard spelling: "):
            result.setdefault("standardized", []).append(stripped[len("🔤 Standard spelling: "):].split(" (", 1)[0])
        elif stripped.startswith("🔍 Look-alike: "):
            # Drive name ≈ sheet name: kept as is, never renamed automatically
            result.setdefault("lookalike_files", []).append(stripped[len("🔍 Look-alike: "):].split(" (", 1)[0])
        elif stripped.startswith("✔ Audio cleanup completed"):
            result["unused_checked"] = True
            parts = []
            if result["deleted"]:
                parts.append(f"{len(result['deleted'])} removed")
            if result.get("lookalike_files"):
                parts.append(f"{len(result['lookalike_files'])} look-alike name(s) to check")
            ui["details"][ui["step"]] = ", ".join(parts) or "none unused"
        elif stripped.startswith("✅ All audio files are available"):
            result["missing_checked"] = True
            ui["details"][ui["step"]] = "none missing"

        # Missing audios (reported, not fatal)
        if stripped.startswith(MISSING_HEADER):
            ui["in_missing_list"] = True
            result["missing_checked"] = True
        elif ui["in_missing_list"] and stripped.startswith("- "):
            result["missing"].append(stripped[2:])
            ui["details"][ui["step"]] = f"{len(result['missing'])} missing"
        elif stripped.startswith("❌"):
            ui["in_missing_list"] = False
            result["errors"].append(stripped)
            errors_box.error("\n\n".join(result["errors"]))

        if stripped.startswith(DONE_MARKER):
            ui["note"] = ("success", "✅ All steps completed.")

    def stop_before_run(outcome, reason):
        """Sign-in didn't succeed: the pipeline never starts, so nothing was created or deleted."""
        if outcome == "cancelled":
            result["state"] = "cancelled"
            text = f"⏹️ Authentication cancelled: {reason}. Nothing was created or deleted."
            ui["auth"] = ("warning", text)
            label = "Cancelled"
        else:
            result["state"] = "error"
            text = f"❌ Authentication failed: {reason}. Nothing was created or deleted."
            ui["auth"] = ("error", text)
            result["errors"].append(text)
            errors_box.error(text)
            label = "Authentication failed"
        result["log"].append(text)
        render()
        status.update(label=f"**{lang}** · {label}", state="error", expanded=True)
        with status:
            render_summary(result)
        return result

    # 🔐 Web Google sign-in (spec 005): once per page session, before anything else runs
    if not st.session_state.get("google_signin"):
        outcome, reason = wait_for_signin(auth_box)
        if outcome != "success":
            return stop_before_run(outcome, reason)
    signin = st.session_state.google_signin
    result["account"] = signin["email"]

    # This run's Google access goes to the pipeline only (never to the AI check, never to disk)
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
               FTM_GOOGLE_CREDENTIALS=json.dumps(signin["info"]))
    proc = subprocess.Popen(
        [sys.executable, "-u", PIPELINE, lang],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )

    # Read output on a thread so the UI keeps refreshing while a long download prints nothing
    lines = queue.Queue()

    def reader():
        for raw in proc.stdout:
            lines.put(raw.rstrip("\n"))
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    render()

    cancel_reason = None
    try:
        finished = False
        while not finished:
            changed = False
            try:
                line = lines.get(timeout=REFRESH_SECONDS)
                while True:
                    if line is None:
                        finished = True
                        break
                    handle(line)
                    changed = True
                    line = lines.get_nowait()
            except queue.Empty:
                pass

            # Stop instead of holding the one-run lock forever
            if not finished:
                if not session_is_open():
                    cancel_reason = "The browser tab was closed"
                elif ui["signin_since"] and time.monotonic() - ui["signin_since"] > SIGNIN_TIMEOUT_SECONDS:
                    cancel_reason = "Google sign-in wasn't completed"
                if cancel_reason:
                    proc.kill()
                    break

            if changed:
                render()
        proc.wait()
    finally:
        # Streamlit interrupts this script on rerun; don't leave an orphaned run behind.
        if proc.poll() is None:
            proc.kill()

    if cancel_reason:
        result["state"] = "cancelled"
        touched = ui["step"] is not None and ui["step"] >= WIPE_STEP
        detail = (
            f"lang/{lang} may be incomplete, so generate it again."
            if touched
            else "Nothing was created or deleted."
        )
        result["log"].append(f"⏹️ Run cancelled: {cancel_reason}. {detail}")
        if result["authenticated"]:
            ui["note"] = ("warning", f"⏹️ Run cancelled: {cancel_reason}. {detail}")
        else:
            ui["auth"] = ("warning", f"⏹️ Authentication cancelled: {cancel_reason}. {detail}")
        render()
        render_steps(final_state="error")
        status.update(label=f"**{lang}** · Cancelled", state="error", expanded=True)
    elif not result["authenticated"]:
        # The pipeline refused this sign-in (expired, revoked, or not a Curious Learning account):
        # it stopped before Step 1. Forget it so the next Generate asks Google again.
        st.session_state.pop("google_signin", None)
        result["state"] = "error"
        ui["auth"] = ("error", "❌ Authentication failed. Nothing was created or deleted.")
        if not result["errors"]:
            result["errors"].append("\n".join(result["log"][-15:]))
            errors_box.error("\n\n".join(result["errors"]))
        render()
        status.update(label=f"**{lang}** · Authentication failed", state="error", expanded=True)
    elif proc.returncode != 0:
        result["state"] = "error"
        if not result["errors"]:
            # Uncaught exception: show the traceback tail.
            result["errors"].append("\n".join(result["log"][-15:]))
            errors_box.error("\n\n".join(result["errors"]))
        ui["note"] = ("error", f"❌ The pipeline stopped with an error (exit code {proc.returncode}).")
        render()
        render_steps(final_state="error")
        status.update(label=f"**{lang}** · Failed", state="error", expanded=True)
    elif result["errors"]:
        result["state"] = "warning"
        ui["note"] = ("warning", "⚠️ The pipeline finished, but some steps reported errors. See above.")
        render()
        render_steps(final_state="complete")
        status.update(label=f"**{lang}** · Finished with errors", state="error", expanded=True)
    else:
        result["state"] = "complete"
        render()
        render_steps(final_state="complete")
        status.update(label=f"**{lang}** · Completed", state="complete", expanded=True)

    if after:
        after(result, status)

    with status:
        render_summary(result)

    return result


def run_ai_check(lang, result, status):
    """
    Run ai_language_check.py after the pipeline (spec 003). Advisory only: it never changes the
    run's state. One AI request at most; the checker reuses cached results for unchanged content.
    """
    final_label = {"complete": ("Completed", "complete"), "warning": ("Finished with errors", "error")}.get(
        result["state"], ("Failed", "error"))
    # Only the run's title shows progress: AI lines stay out of the steps and the pipeline log
    status.update(label=f"**{lang}** · 🤖 AI language check in progress…", state="running", expanded=True)
    ai_log = result.setdefault("ai_log", [])

    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-u", AI_CHECK, lang],
        cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
    )
    lines = queue.Queue()

    def reader():
        for raw in proc.stdout:
            lines.put(raw.rstrip("\n"))
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    report, tail = None, []
    try:
        while True:
            try:
                line = lines.get(timeout=REFRESH_SECONDS)
            except queue.Empty:
                if not session_is_open():
                    proc.kill()
                    report = {"status": "unavailable", "reason": "the browser tab was closed"}
                    break
                continue
            if line is None:
                break
            if line.startswith(AI_REPORT):
                report = json.loads(line[len(AI_REPORT):])
                continue
            ai_log.append(line)
            tail.append(line)
        proc.wait()
    except json.JSONDecodeError:
        report = None
    finally:
        if proc.poll() is None:
            proc.kill()

    if report is None:
        report = {"status": "unavailable", "reason": "the AI check stopped unexpectedly: " + " / ".join(tail[-3:])}
    report.setdefault("warnings", [])
    for w in report["warnings"]:
        ai_log.append(
            f"AI {w.get('confidence')} {w.get('category')}: {w.get('text')} → {w.get('suggestion') or '-'} "
            f"({w.get('reason')}) at {', '.join(w.get('locations', []))}")
    result["ai"] = report
    status.update(label=f"**{lang}** · {final_label[0]}", state=final_label[1], expanded=True)


def render_summary(result):
    # Runs recorded before these fields existed
    for key in ("deleted", "renamed", "lookalike_files"):
        result.setdefault(key, [])
    for key in ("unused_checked", "missing_checked"):
        result.setdefault(key, False)

    stamp = result["started"].replace(":", "-").replace(" ", "_")
    log_button = dict(
        label="Download log",
        data="\n".join(result["log"]),
        file_name=f"{result['lang']}_{stamp}.log",
        key=f"dl_{result['lang']}_{result['started']}",
        on_click="ignore",  # a rerun would interrupt (and kill) a run in progress
    )

    # Sign-in never completed: no audio check ran, so there is nothing else to summarize
    if not result.get("authenticated", True):
        st.download_button(**log_button)
        return

    st.markdown("#### 🎧 Audio check")

    # Sheet name → look-alike Drive file (kept as is, not renamed)
    lookalike_for = {}
    for pair in result["lookalike_files"]:
        drive_name, _, json_name = pair.partition(" ≈ ")
        lookalike_for[json_name] = drive_name

    # Missing audios
    if result["missing"]:
        st.warning(
            f"**Missing audios:** {len(result['missing'])} audio file(s) are referenced in the JSON "
            "but were not found on Drive:\n\n"
            + "\n".join(f"- {m}" + (f"  (Drive has a look-alike: {lookalike_for[m]}, see below)" if m in lookalike_for else "")
                        for m in sorted(result["missing"]))
        )
    elif result["missing_checked"]:
        st.success("**Missing audios:** none. Every audio referenced in the JSON is available.")
    else:
        st.caption("Missing-audio check did not run (the pipeline stopped earlier).")

    # Drive name differs from the sheet name only in upper/lowercase: kept as is, never renamed
    if result["lookalike_files"]:
        st.warning("**Name differs only in upper/lowercase** (Drive file ≈ name in the sheet). "
                   "Rename one so they match:\n\n" + "\n".join(f"- {p}" for p in result["lookalike_files"]))

    # ा + े / ा + ै written as the standard ो / ौ: done automatically, just noted
    if result.get("standardized"):
        st.caption("🔤 Look-alike vowel signs written in the standard form: " + ", ".join(result["standardized"]))

    # Runs recorded before look-alikes were reported instead of renamed
    if result["renamed"]:
        st.warning(
            f"**Spelling differs between Drive and the sheet:** {len(result['renamed'])} audio file(s) "
            "were renamed to the spelling used in the JSON (older run). Please correct the spelling in the sheet:\n\n"
            + "\n".join(f"- {r}" for r in result["renamed"])
        )

    # Unused audios
    if result["deleted"]:
        with st.expander(
            f"🗑 **Unused audios removed:** {len(result['deleted'])} file(s) from Drive are not used in the JSON"
        ):
            st.markdown("\n".join(f"- {d}" for d in sorted(result["deleted"])))
    elif result["unused_checked"]:
        st.success("**Unused audios:** none. Every downloaded audio is used in the JSON.")
    else:
        st.caption("Unused-audio check did not run (the pipeline stopped earlier).")

    # AI language check: right after the unused-audio result, with its own log
    if result.get("ai"):
        render_ai_section(result["ai"], result["lang"])
        render_ai_log(result, stamp)

    audios_dir = lang_paths.audios_dir(result["lang"])
    if os.path.isdir(audios_dir):
        count = len([f for f in os.listdir(audios_dir) if f.lower().endswith(".mp3")])
        st.caption(f"📂 {count} mp3 file(s) in `lang/{result['lang'].lower()}/audios`")

    st.download_button(**log_button)


def render_ai_log(result, stamp):
    """The AI check's own log, kept apart from the pipeline log."""
    ai_log = result.get("ai_log") or []
    if not ai_log:
        return
    with st.expander("🤖 AI check log"):
        st.code("\n".join(ai_log), language=None)
    st.download_button(
        "Download AI log",
        data="\n".join(ai_log),
        file_name=f"{result['lang']}_{stamp}_ai.log",
        key=f"dl_ai_{result['lang']}_{result['started']}",
        on_click="ignore",
    )


AI_CATEGORY_LABELS = {
    "misspelled_word": "Misspelled word",
    "foreign_letter": "Letter not used in this language",
    "bad_sentence": "Feedback sentence",
    "recording_mismatch": "Recording name",
    "letters_dont_spell_word": "Letters don't spell the word",
    "letter_not_in_word": "Letter not in the word",
}
AI_BADGES = {"high": "🔴 high", "medium": "🟠 medium", "low": "🟡 low"}


def render_ai_warning(w):
    locations = w.get("locations", [])
    where = ", ".join(locations[:8]) + (f" and {len(locations) - 8} more" if len(locations) > 8 else "")
    change = f"`{w.get('text')}` → `{w['suggestion']}`" if w.get("suggestion") else f"`{w.get('text')}`"
    st.markdown(
        f"{AI_BADGES.get(w.get('confidence'), w.get('confidence'))} · **{AI_CATEGORY_LABELS.get(w.get('category'), w.get('category'))}** · "
        f"{change}  \n{w.get('reason', '')}  \n*Where:* {where}"
    )


def render_ai_usage(ai):
    """Model and real input/output tokens of the AI request, to compare providers' costs."""
    model = ai.get("model") or "?"
    usage = ai.get("usage")
    if not usage:
        if ai.get("status") != "unavailable" or ai.get("model"):
            note = ("earlier check, token counts weren't recorded then" if ai.get("cached")
                    else "no tokens used" if ai.get("status") == "unavailable" else "not reported by the API")
            st.markdown(f"**Model:** `{model}` · **Tokens:** {note}")
        return
    inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    thinking = f" (incl. {usage['thinking_tokens']:,} thinking)" if usage.get("thinking_tokens") else ""
    st.markdown(f"**Model:** `{model}` · **Input tokens:** {inp:,} · **Output tokens:** {out:,}{thinking} · "
                f"**Total:** {inp + out:,}")
    if ai.get("cached"):
        st.caption("These are the counts of the earlier request. This run reused its result and used 0 tokens.")


def render_ai_section(ai, lang):
    """The "AI language check" report (contracts/ai-check-cli-and-ui.md). Advisory: warnings, never errors."""
    provider = ai.get("provider") or "AI"
    language = f", language: {ai['assumed_language']}" if ai.get("assumed_language") else ""
    st.markdown(f"#### 🤖 AI language check ({provider}{language})")
    if st.session_state.get("show_tokens"):
        render_ai_usage(ai)
    status = ai.get("status")
    found = ai.get("warnings", [])
    from_ai = [w for w in found if w.get("source") == "ai"]
    consistency = [w for w in found if w.get("source") == "consistency"]

    if ai.get("cached"):
        st.caption(f"From earlier check on {ai.get('checked_at')}: content unchanged, so no new AI request was made.")
    if status == "unavailable":
        st.warning(f"AI check unavailable: {ai.get('reason')}")
    elif status == "cannot_judge":
        st.info(f"{provider} could not reliably review {lang}: {ai.get('reason')}")
    elif not from_ai:
        st.success("No issues found" if not consistency else "No language issues found by the AI")
    else:
        st.markdown(f"**{len(from_ai)} possible issue(s)** (highest confidence first)")
    for w in from_ai:
        render_ai_warning(w)

    if consistency:
        st.markdown(f"**Consistency check (letters vs words):** {len(consistency)} issue(s)")
        for w in consistency:
            render_ai_warning(w)


# =========================================================
# UI
# =========================================================
STATE_ICONS = {"complete": "✅", "warning": "⚠️", "error": "❌", "running": "⏹️", "cancelled": "⏹️"}


def existing_audio_count(lang):
    """Number of mp3s if lang/<lang>/ already has its game JSON and audios (a finished earlier run), else 0."""
    audios = lang_paths.audios_dir(lang)
    if not os.path.isfile(lang_paths.json_path(lang)) or not os.path.isdir(audios):
        return 0
    return len([f for f in os.listdir(audios) if f.lower().endswith(".mp3")])


def on_generate():
    """Generate clicked: validate, clear the input, then queue the run (or ask first if it already exists)."""
    state = st.session_state
    langs = [l.strip() for l in state.lang_input.split(",") if l.strip()]
    invalid = []
    for l in langs:
        try:
            lang_paths.validate_language_name(l)
        except ValueError:
            invalid.append(l)
    if not langs:
        state.form_error = "Please type a language name."
        return
    if invalid:
        state.form_error = f"Invalid language name: {', '.join(invalid)}. Use letters, digits, spaces, - or _."
        return

    existing = {l: n for l in langs if (n := existing_audio_count(l))}
    if existing:
        state.confirm = {"langs": langs, "existing": existing}
    else:
        state.queue = langs


def answer_regenerate(regenerate):
    """Yes: run everything. No (or dialog closed): run only the languages that don't exist yet."""
    confirm = st.session_state.pop("confirm", None)
    if not confirm:
        return
    langs = confirm["langs"] if regenerate else [l for l in confirm["langs"] if l not in confirm["existing"]]
    st.session_state.queue = langs or None
    if not regenerate:
        st.session_state.skipped = list(confirm["existing"])


@st.dialog("Language already generated", on_dismiss=lambda: answer_regenerate(False))
def confirm_regenerate(confirm):
    for lang, count in confirm["existing"].items():
        st.markdown(f"**{lang}** already has its game JSON and **{count}** audio file(s) in "
                    f"`lang/{lang.lower()}/`.")
    st.write("Do you need to regenerate this language?" if len(confirm["existing"]) == 1
             else "Do you need to regenerate these languages?")
    st.caption("Regenerating deletes the current folder and downloads everything again from Google Drive.")
    yes, no = st.columns(2)
    if yes.button("Yes, regenerate", type="primary", width="stretch"):
        answer_regenerate(True)
        st.rerun()
    if no.button("No", width="stretch"):
        answer_regenerate(False)
        st.rerun()


def show_run(res, expanded):
    with st.expander(f"{STATE_ICONS.get(res['state'], '')} {res['lang']} · {res['started']}", expanded=expanded):
        if res.get("steps_md"):
            st.markdown(res["steps_md"])
        if res["errors"]:
            st.error("\n\n".join(res["errors"]))
        st.code("\n".join(res["log"]), language=None)
        render_summary(res)


st.set_page_config(page_title="FTM Language Generator", page_icon="🌍")

# Web Google sign-in settings (spec 005). Missing or invalid: nothing can be generated (fail closed).
try:
    SIGNIN_CONFIG, SIGNIN_SETUP_ERROR = web_signin.load_client_config(), None
except web_signin.SetupError as e:
    SIGNIN_CONFIG, SIGNIN_SETUP_ERROR = None, str(e)

# This tab is Google returning from a sign-in: finish it here and draw nothing else
if "code" in st.query_params or "error" in st.query_params:
    render_signin_callback()

st.title("🌍 Feed the Monster · Language Generator")
st.caption(
    "Fetches the language sheet, game JSON and audio files from Google Drive into "
    "`lang/<language>/`, then checks for unused and missing audios. "
    "When you press Generate, you'll be asked to sign in with your Curious Learning Google account "
    "in a new tab (once per page visit)."
)
if SIGNIN_CONFIG is None:
    st.error(f"Google sign-in isn't set up on this server: {SIGNIN_SETUP_ERROR}. No language can be generated.")

for key, default in (("history", []), ("lang_input", ""), ("last_batch", 0)):
    st.session_state.setdefault(key, default)

pending_langs = st.session_state.get("queue")
other_run = pipeline_lock().locked() and not pending_langs  # someone else (another tab/user) is generating
busy = bool(pending_langs) or other_run or SIGNIN_CONFIG is None

with st.form("generate", clear_on_submit=True):  # empty the input after every Generate
    st.text_input(
        "Language name",
        key="lang_input",
        placeholder="e.g. Hausa  (or several: Hausa, IndianEnglish)",
        help="The same name you would type after `python generate_language.py`. Separate several with commas.",
        disabled=busy,
    )
    st.form_submit_button("Generate", type="primary", on_click=on_generate, disabled=busy)

# AI language check (spec 003): off by default; when off, no AI service is called
ai_cfg, ai_reason = ai_providers.load_config()
st.session_state.setdefault("show_tokens", False)
st.toggle("🤖 AI language check", key="ai_check", value=False, disabled=busy,
          help="After generating, an AI reviews the language's letters, words and feedback sentences "
               "and suggests corrections. One request per language; unchanged content isn't sent again.")
if st.session_state.ai_check:
    st.caption(f"Not configured: {ai_reason}. See `.env.example`." if ai_reason
               else f"Uses {ai_cfg['provider']} ({ai_cfg[ai_cfg['provider']]['model']}).")
    # Show tokens used (spec 006): only under the AI check, off by default. The choice is kept in
    # show_tokens, so it survives the AI toggle being switched off and on (Streamlit drops the
    # state of a widget that isn't drawn). It only changes what the page shows; the counts are
    # always recorded in the report and the AI log.
    _, indented = st.columns([0.04, 0.96])
    with indented:
        st.session_state.show_tokens = st.toggle(
            "🔢 Show tokens used", key="show_tokens_toggle", value=st.session_state.show_tokens,
            disabled=busy,
            help="Shows the model and the real input and output tokens of each AI check, "
                 "to compare the cost of models and providers.")

if error := st.session_state.pop("form_error", None):
    st.error(error)
if skipped := st.session_state.pop("skipped", None):
    st.info(f"Not regenerated: {', '.join(skipped)} (kept as it is).")
if other_run:
    st.warning("⏳ Another language is being generated right now. Refresh this page when it finishes.")

if st.session_state.get("confirm") and not busy:
    confirm_regenerate(st.session_state.confirm)

new_runs = 0
if pending_langs and SIGNIN_CONFIG is None:
    st.session_state.queue = None  # never start a run without the sign-in settings (FR-011)
elif pending_langs:
    lock = pipeline_lock()
    if not lock.acquire(blocking=False):
        st.warning("⏳ Another language is being generated right now. Please try again when it finishes.")
        st.session_state.queue = None
    else:
        try:
            st.info("⚠️ Keep this page open until the run finishes. Generate is disabled until then.")
            def ai_step(result, status):
                # Only when switched on, signed in, not cancelled, and this run produced the game JSON
                if (st.session_state.get("ai_check") and result["authenticated"]
                        and result["state"] != "cancelled" and os.path.isfile(lang_paths.json_path(result["lang"]))):
                    run_ai_check(result["lang"], result, status)

            for lang in pending_langs:
                res = run_pipeline(lang, after=ai_step)
                st.session_state.history.insert(0, res)
                new_runs += 1
                if res["state"] in ("cancelled", "error") and not res["authenticated"]:
                    break  # sign-in failed or the tab closed: don't start the remaining languages
        finally:
            lock.release()
            st.session_state.queue = None
        st.session_state.last_batch = new_runs
        st.rerun()  # re-enable the Generate button; the finished run is shown below as "Latest run"

def start_new_language():
    """'Add another language': the finished run moves to Previous runs; the form is ready again."""
    st.session_state.last_batch = 0
    st.session_state.lang_input = ""
    st.session_state.focus_form = True


# Bring the user back to an empty, focused language box (fixed script, no user content)
if st.session_state.pop("focus_form", False):
    st.html("""<script>
      window.scrollTo({top: 0, behavior: "smooth"});
      setTimeout(() => { const i = document.querySelector('input[type="text"]'); if (i) i.focus(); }, 300);
    </script>""", unsafe_allow_javascript=True)

history = st.session_state.history
latest, earlier = history[:st.session_state.last_batch], history[st.session_state.last_batch:]
# Every language in the last batch went through all its steps: offer to start the next one
all_done = bool(latest) and not busy and all(r["state"] in ("complete", "warning") for r in latest)
if latest:
    if all_done:
        names = ", ".join(r["lang"] for r in latest)
        done, again = st.columns([3, 1], vertical_alignment="center")
        done.success(f"✅ {names} generated. You can add another language now.")
        again.button("➕ Add another language", key="add_lang_top", type="primary",
                     on_click=start_new_language, width="stretch")
    st.subheader("Latest run")
    for res in latest:
        show_run(res, expanded=True)
    if all_done:
        st.button("➕ Add another language", key="add_lang_bottom", type="primary", on_click=start_new_language)
if earlier:
    st.divider()
    st.subheader("Previous runs")
    for res in earlier:
        show_run(res, expanded=False)
