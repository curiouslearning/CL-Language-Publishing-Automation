"""
Web Google sign-in for the generator page (spec 005, contracts/web-signin.md).

Generate starts a sign-in in a new tab. Google sends that tab back to the app with ?state&code.
The callback tab checks the account and leaves the outcome in a process-wide pending store; the
generator tab that started the sign-in picks it up once (pop_result) and starts the run.

A sign-in request is tied to the session that started it (session_id), to its browser (the
ftm_signin cookie), is single use, and expires after SIGNIN_TIMEOUT_SECONDS.
Only verified Google accounts managed by curiouslearning.org are admitted.
"""
import json
import os
import secrets
import sys
import threading
import time

import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

import google_auth

ALLOWED_DOMAIN = "curiouslearning.org"
SIGNIN_TIMEOUT_SECONDS = 180
COOKIE_NAME = "ftm_signin"
DEFAULT_CLIENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secret_web.json")
DEFAULT_PUBLIC_URL = "http://localhost:8501/"

# Messages shown in the sign-in tab (contracts/web-signin.md, "Callback")
MSG_UNKNOWN = ("This sign-in link has already been used or has expired. "
               "Go back to the generator and press Generate again.")
MSG_OTHER_BROWSER = "Please complete the sign-in in the same browser where you pressed Generate."
MSG_CANCELLED = "Sign-in was cancelled or didn't complete."
MSG_FAILED = "Sign-in failed. Please try again."
MSG_GENERATOR_CLOSED = "The generator tab that started this sign-in was closed. Press Generate again."

# Reasons shown under "Authentication failed" in the generator tab
REASON_REFUSED = "only Curious Learning (curiouslearning.org) accounts can add languages (signed in as {email})"
REASON_CANCELLED = "sign-in was cancelled or didn't complete"
REASON_FAILED = "sign-in failed"
REASON_OTHER_BROWSER = "the sign-in was completed in a different browser"

FINAL = ("success", "refused", "failed")


class SetupError(Exception):
    """The web sign-in isn't configured. The message is shown on the page."""


# -------------------------------------------
# Configuration
# -------------------------------------------
def load_client_config():
    """{"client_config", "client_id", "redirect_uri"}, or SetupError (FR-011: nothing runs)."""
    path = os.environ.get("FTM_OAUTH_CLIENT_FILE") or DEFAULT_CLIENT_FILE
    redirect_uri = os.environ.get("FTM_PUBLIC_URL") or DEFAULT_PUBLIC_URL
    name = os.path.basename(path)

    if not os.path.isfile(path):
        raise SetupError(f"{name} is missing")
    try:
        with open(path, encoding="utf-8") as f:
            client_config = json.load(f)
    except (OSError, ValueError):
        raise SetupError(f"{name} can't be read") from None
    web = client_config.get("web") if isinstance(client_config, dict) else None
    if not web or not web.get("client_id") or not web.get("client_secret"):
        raise SetupError(f"{name} isn't a Web application OAuth client (no web.client_id / web.client_secret)")
    if google_auth.is_hosted() and not redirect_uri.startswith("https://"):
        raise SetupError("FTM_PUBLIC_URL must be https when FTM_HOSTED=1")

    # Google may return the granted scopes in another order; that isn't an error
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    if redirect_uri.startswith("http://localhost"):
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # local development only

    return {"client_config": client_config, "client_id": web["client_id"], "redirect_uri": redirect_uri}


def _flow(config, **kwargs):
    return Flow.from_client_config(
        config["client_config"], scopes=google_auth.WEB_SCOPES, redirect_uri=config["redirect_uri"], **kwargs)


# -------------------------------------------
# Pending store: state → PendingSignIn (data-model.md)
# -------------------------------------------
@st.cache_resource
def pending_store():
    return {"lock": threading.Lock(), "entries": {}}


def _expire_old(entries):
    now = time.monotonic()
    for state in [s for s, e in entries.items() if now - e["created"] > SIGNIN_TIMEOUT_SECONDS]:
        del entries[state]


def start_signin(config, session_id):
    """New sign-in request for this session. Returns (state, browser_nonce, auth_url)."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)
    # PKCE: from_client_config leaves it off unless asked for explicitly
    flow = _flow(config, autogenerate_code_verifier=True)
    auth_url, _ = flow.authorization_url(
        state=state,
        access_type="offline",                 # refresh token: a long run keeps working
        prompt="select_account consent",       # always offer the account chooser (FR-007)
        include_granted_scopes="false",
        hd=ALLOWED_DOMAIN,                     # a hint for Google's chooser only, not a check
    )
    store = pending_store()
    with store["lock"]:
        _expire_old(store["entries"])
        store["entries"][state] = {
            "session_id": session_id,
            "browser_nonce": nonce,
            "code_verifier": flow.code_verifier,
            "created": time.monotonic(),
            "status": "pending",
            "email": None,
            "credentials_info": None,
            "reason": None,
        }
    return state, nonce, auth_url


def get_status(state):
    """'pending', a final status, or 'expired' (also when the entry is gone)."""
    store = pending_store()
    with store["lock"]:
        _expire_old(store["entries"])
        entry = store["entries"].get(state)
        return entry["status"] if entry else "expired"


def pop_result(state, session_id):
    """The final entry for this session's request, removed from the store (single use), or None."""
    store = pending_store()
    with store["lock"]:
        entry = store["entries"].get(state)
        if not entry or entry["session_id"] != session_id or entry["status"] not in FINAL:
            return None
        return store["entries"].pop(state)


def discard(state):
    """Forget a request the generator tab gave up on (timeout, tab closed)."""
    store = pending_store()
    with store["lock"]:
        store["entries"].pop(state, None)


# -------------------------------------------
# Admission (research R3)
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


# -------------------------------------------
# Callback (runs in the sign-in tab)
# -------------------------------------------
def handle_callback(config, params, cookie_value, session_is_active):
    """
    Complete the sign-in Google redirected to. Returns (kind, message) for the sign-in tab, where
    kind is "unknown", "failed", "refused" or "success". The outcome is left in the pending store
    for the generator tab that started it.
    """
    state = params.get("state")
    store = pending_store()

    with store["lock"]:
        _expire_old(store["entries"])
        entry = store["entries"].get(state) if state else None
        if not entry or entry["status"] != "pending":
            return "unknown", MSG_UNKNOWN  # unknown, expired or already used
        entry["status"] = "checking"  # claimed: a second callback for this state is now "unknown"

    def finish(status, message, reason=None, email=None, info=None):
        with store["lock"]:
            entry.update(status=status, reason=reason, email=email, credentials_info=info)
        return status, message

    if not session_is_active(entry["session_id"]):
        with store["lock"]:
            store["entries"].pop(state, None)
        return "failed", MSG_GENERATOR_CLOSED
    if not cookie_value or not secrets.compare_digest(cookie_value, entry["browser_nonce"]):
        return finish("failed", MSG_OTHER_BROWSER, REASON_OTHER_BROWSER)
    if params.get("error") or not params.get("code"):
        return finish("failed", MSG_CANCELLED, REASON_CANCELLED)

    try:
        flow = _flow(config, state=state, code_verifier=entry["code_verifier"], autogenerate_code_verifier=False)
        flow.fetch_token(code=params["code"])
        creds = flow.credentials
        claims = id_token.verify_oauth2_token(
            creds.id_token, Request(), config["client_id"], clock_skew_in_seconds=10)
    except Exception as e:
        # Server log only: the exception type and message, never a token or the code
        print(f"web_signin: sign-in failed ({type(e).__name__}: {e})", file=sys.stderr)
        return finish("failed", MSG_FAILED, REASON_FAILED)

    admitted, email = admit(claims)
    if not admitted:
        reason = REASON_REFUSED.format(email=email or "an unknown account")
        return finish("refused",
                      f"Only Curious Learning (curiouslearning.org) accounts can add languages. "
                      f"You signed in as {email or 'an unknown account'}.",
                      reason, email)

    return finish("success",
                  f"✅ Signed in as {email}. Return to the generator tab: your run continues there. "
                  f"You can close this tab.",
                  email=email, info=json.loads(creds.to_json()))
