"""
The generator's web server (spec 012): serves the React page (web/dist) and its API.

Nothing here keeps a connection open while a page is merely open: a run is one streaming request
(NDJSON events, contracts/http-api.md) that lasts exactly as long as the run, so Cloud Run can scale
to zero between runs. If that request's connection closes (tab closed or reloaded), the run is
stopped and the one-run lock released.

    python server.py            # http://localhost:8080  (PORT / HOST override)
"""
import asyncio
import contextlib
import json
import os
import queue
import subprocess
import sys
import threading
import time

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse

import ai_providers
import google_auth
import lang_paths
import run_store

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(APP_DIR, "generate_language.py")
AI_CHECK = os.path.join(APP_DIR, "ai_language_check.py")
DIST_DIR = os.path.join(APP_DIR, "web", "dist")

AI_REPORT = "🤖 AI report: "
AUTH_DONE = "✅ Authenticated as "
# "Prepare a clean language folder" (web/src/runParser.ts STEPS[1]): from here on lang/<lang>/ was touched
WIPE_MARKER = "🧽 Preparing a clean language folder"
PING_SECONDS = 5      # keep-alive while a step prints nothing; also how soon a closed tab is noticed
POLL_SECONDS = 0.1

ALLOWED_DOMAIN = "curiouslearning.org"
DEFAULT_CLIENT_FILE = os.path.join(APP_DIR, "client_secret_web.json")
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REQUIRED_SCOPES = ("https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets.readonly")

# Reasons shown after "Authentication failed:" on the page
REASON_REFUSED = "only Curious Learning (curiouslearning.org) accounts can add languages (signed in as {email})"
REASON_EXPIRED = "your Google sign-in has expired or is invalid. Please sign in again"
REASON_WRONG_CLIENT = "this Google sign-in wasn't made for this page"
REASON_SCOPES = "Google Drive and Sheets access weren't both allowed. Please sign in again and allow them"
REASON_FAILED = "sign-in failed"
BUSY = "Another language is being generated right now. Please try again when it finishes."


class SetupError(Exception):
    """The web sign-in isn't configured. The message is shown on the page."""


def load_client_id():
    """The Web application OAuth client's id (public; the secret isn't used). SetupError if missing."""
    path = os.environ.get("FTM_OAUTH_CLIENT_FILE") or DEFAULT_CLIENT_FILE
    name = os.path.basename(path)
    if not os.path.isfile(path):
        raise SetupError(f"{name} is missing")
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError):
        raise SetupError(f"{name} can't be read") from None
    web = config.get("web") if isinstance(config, dict) else None
    if not web or not web.get("client_id"):
        raise SetupError(f"{name} isn't a Web application OAuth client (no web.client_id)")
    return web["client_id"]


def signin_settings():
    try:
        return load_client_id(), None
    except SetupError as e:
        return None, str(e)


# -------------------------------------------
# Google sign-in check (research R4): every run's token, before anything is claimed or started
# -------------------------------------------
def admit(claims):
    """(admitted, email): a verified email, managed by curiouslearning.org, with that domain."""
    email = (claims.get("email") or "").strip()
    admitted = (
        claims.get("email_verified") is True
        and claims.get("hd") == ALLOWED_DOMAIN
        and email.lower().endswith("@" + ALLOWED_DOMAIN)
    )
    return admitted, email or None


def verify_token(token, client_id):
    """("ok", email) | ("refused", reason) | ("failed", reason). Never logs the token."""
    try:
        r = requests.get(TOKENINFO_URL, params={"access_token": token}, timeout=15)
        if r.status_code != 200:
            return "failed", REASON_EXPIRED
        info = r.json()
        if client_id not in (info.get("aud"), info.get("azp")):
            return "failed", REASON_WRONG_CLIENT
        if int(info.get("expires_in", 0)) < 60:
            return "failed", REASON_EXPIRED
        granted = set(info.get("scope", "").split())
        if not all(s in granted for s in REQUIRED_SCOPES):
            return "failed", REASON_SCOPES
        u = requests.get(USERINFO_URL, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if u.status_code != 200:
            return "failed", REASON_EXPIRED
        admitted, email = admit(u.json())
    except (requests.RequestException, ValueError) as e:
        print(f"server: sign-in check failed ({type(e).__name__})", file=sys.stderr, flush=True)
        return "failed", REASON_FAILED
    if not admitted:
        return "refused", REASON_REFUSED.format(email=email or "an unknown account")
    return "ok", email


# -------------------------------------------
# Subprocess output → async lines
# -------------------------------------------
def start_script(args, env):
    proc = subprocess.Popen(
        [sys.executable, "-u", *args], cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env)
    lines = queue.Queue()

    def reader():
        for raw in proc.stdout:
            lines.put(raw.rstrip("\n"))
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    return proc, lines


async def script_lines(lines):
    """Yields each output line, or None as a keep-alive after PING_SECONDS of silence. Ends at EOF."""
    last = time.monotonic()
    while True:
        try:
            line = lines.get_nowait()
        except queue.Empty:
            if time.monotonic() - last >= PING_SECONDS:
                last = time.monotonic()
                yield None
            await asyncio.sleep(POLL_SECONDS)
            continue
        if line is None:
            return
        last = time.monotonic()
        yield line


def kill(proc):
    if proc is not None and proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def event(kind, **fields):
    return (json.dumps({"type": kind, **fields}, ensure_ascii=False) + "\n").encode("utf-8")


def mp3_count(lang):
    audios = lang_paths.audios_dir(lang)
    if not os.path.isdir(audios):
        return None
    return len([f for f in os.listdir(audios) if f.lower().endswith(".mp3")])


async def run_events(lang, token, ai_check, client_id):
    """One language: sign-in check, pipeline, optional AI check. Cleanup always runs (also on disconnect)."""
    if not run_store.run_lock.acquire(blocking=False):
        yield event("busy", reason=BUSY)
        return
    pipeline = ai = None
    package_id, touched, authenticated, ok = None, False, False, False
    try:
        status, detail = await asyncio.to_thread(verify_token, token, client_id)
        if status != "ok":
            yield event("auth", status=status, reason=detail)
            yield event("end")
            return
        yield event("auth", status="ok", email=detail)
        print(f"server: run {lang} by {detail}", flush=True)

        # Spec 008: from here on lang/<lang>/ belongs to this run
        package_id = run_store.claim(lang)
        # This run's Google access goes to the pipeline only (never to the AI check, never to disk)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                   FTM_GOOGLE_CREDENTIALS=json.dumps({"token": token}))
        pipeline, lines = start_script([PIPELINE, lang], env)
        async for line in script_lines(lines):
            if line is None:
                yield event("ping")
                continue
            stripped = line.strip()
            if stripped.startswith(AUTH_DONE):
                authenticated = True
            elif stripped.startswith(WIPE_MARKER):
                touched = True
            yield event("line", text=line)
        returncode = await asyncio.to_thread(pipeline.wait)
        yield event("pipeline_end", returncode=returncode)
        ok = authenticated and returncode == 0

        # AI language check (spec 003): signed in and the game JSON exists (even after step errors)
        if ai_check and authenticated and os.path.isfile(lang_paths.json_path(lang)):
            yield event("ai_start")
            env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
            env.pop(google_auth.CREDENTIALS_ENV, None)
            ai, lines = start_script([AI_CHECK, lang], env)
            report, tail = None, []
            async for line in script_lines(lines):
                if line is None:
                    yield event("ping")
                elif line.startswith(AI_REPORT):
                    try:
                        report = json.loads(line[len(AI_REPORT):])
                    except ValueError:
                        report = None
                else:
                    tail.append(line)
                    yield event("ai_line", text=line)
            await asyncio.to_thread(ai.wait)
            if report is None:
                report = {"status": "unavailable",
                          "reason": "the AI check stopped unexpectedly: " + " / ".join(tail[-3:])}
            yield event("ai_report", report=report)

        run_store.finish(lang, package_id, touched=touched, ok=ok)
        finished_id, package_id = package_id, None
        yield event("end", package_id=finished_id if ok else None, mp3_count=mp3_count(lang) if authenticated else None)
    finally:
        cancelled = pipeline is not None and pipeline.poll() is None or ai is not None and ai.poll() is None
        kill(pipeline)
        kill(ai)
        if package_id:  # stopped before the end (tab closed): the folder may be incomplete
            run_store.finish(lang, package_id, touched=touched, ok=False)
        if cancelled:
            print(f"server: run {lang} cancelled (the page closed the connection)", flush=True)
        run_store.run_lock.release()


class RunResponse(StreamingResponse):
    """Closes the event generator however the response ends, so its cleanup (kill, unlock) always runs."""

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await self.body_iterator.aclose()
            except (RuntimeError, AttributeError):
                pass


# -------------------------------------------
# App
# -------------------------------------------
@contextlib.asynccontextmanager
async def lifespan(_app):
    if google_auth.is_hosted():
        run_store.start_janitor()  # hosted: delete packages nobody downloaded (spec 008/012)
    yield


app = FastAPI(title="FTM Language Generator", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


def error(status, detail):
    return JSONResponse({"detail": detail}, status_code=status)


@app.get("/api/config")
def config():
    client_id, setup_error = signin_settings()
    cfg, reason = ai_providers.load_config()
    provider = cfg.get("provider") if isinstance(cfg, dict) else None
    model = (cfg.get(provider) or {}).get("model") if provider and isinstance(cfg.get(provider), dict) else None
    return {
        "hosted": google_auth.is_hosted(),
        "signin": {"client_id": client_id, "hd": ALLOWED_DOMAIN} if client_id else None,
        "signin_error": setup_error,
        "ai": {"provider": provider, "model": model, "reason": reason},
        "busy": run_store.run_lock.locked(),
    }


@app.post("/api/existing")
async def existing(request: Request):
    body = await request.json()
    langs = body.get("langs") if isinstance(body, dict) else None
    if not isinstance(langs, list):
        return error(400, "langs must be a list")
    if google_auth.is_hosted():
        return {"existing": {}}  # hosted: the page knows which packages it holds (spec 012, R5)
    found = {}
    for lang in langs:
        try:
            name = lang_paths.validate_language_name(str(lang))
        except ValueError:
            continue
        if n := run_store.existing_audio_count(name):
            found[name] = n
    return {"existing": found}


@app.post("/api/runs")
async def runs(request: Request):
    try:
        body = await request.json()
        lang = lang_paths.validate_language_name(str(body.get("lang", "")))
    except (ValueError, AttributeError):
        return error(400, "Invalid language name. Use letters, digits, spaces, - or _.")
    client_id, setup_error = signin_settings()
    if not client_id:
        return error(503, f"Google sign-in isn't set up on this server: {setup_error}.")
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or not auth[7:].strip():
        return error(401, "No Google sign-in was sent with this run.")
    if run_store.run_lock.locked():
        return error(409, BUSY)
    return RunResponse(run_events(lang, auth[7:].strip(), bool(body.get("ai_check")), client_id),
                       media_type="application/x-ndjson",
                       headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/packages/{package_id}")
def package(package_id: str):
    if not package_id.isalnum() or len(package_id) != 32:
        return error(404, "Unknown package.")
    try:
        lang, data = run_store.build_zip(package_id)
    except run_store.Unavailable as e:
        return error(410, str(e))
    name = lang.strip().lower()
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.zip"', "Cache-Control": "no-store"})


@app.get("/{path:path}")
def page(path: str):
    """The built React page. Unknown paths get index.html (one-page app)."""
    if path == "api" or path.startswith("api/"):
        return error(404, "Unknown API path.")
    index = os.path.join(DIST_DIR, "index.html")
    if not os.path.isfile(index):
        return HTMLResponse(
            "<h1>The page isn't built yet</h1><p>Run <code>npm ci &amp;&amp; npm run build</code> in "
            "<code>language_automation/web</code>, then reload.</p>", status_code=503)
    target = os.path.realpath(os.path.join(DIST_DIR, path))
    if path and target.startswith(os.path.realpath(DIST_DIR) + os.sep) and os.path.isfile(target):
        cache = "public, max-age=31536000, immutable" if "/assets/" in target.replace(os.sep, "/") else "no-cache"
        return FileResponse(target, headers={"Cache-Control": cache})
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST") or ("0.0.0.0" if google_auth.is_hosted() else "127.0.0.1")
    uvicorn.run(app, host=host, port=int(os.environ.get("PORT", "8080")), log_level="info")
