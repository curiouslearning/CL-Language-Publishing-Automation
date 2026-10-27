"""Pause an idle page so the hosted server can scale to zero (spec 011).

Cloud Run bills a service for as long as any request is open. Every open Streamlit tab keeps a
websocket (/_stcore/stream) open, so a tab left open all day keeps the server billed all day,
even when nobody is using it. This module adds a small script to the page: after
FTM_IDLE_PAUSE_MINUTES with no mouse, keyboard, touch or scroll activity, and no run in
progress in this tab, the tab leaves the app for a local "paused" page. That closes the
websocket, and with no open connections Cloud Run stops billing. "Resume" loads the app again.

On by default only on the hosted deploy (FTM_HOSTED=1); locally it's off unless the variable is set.
"""
import json
import os
import time

import streamlit as st

import ai_providers

# A minute's warning before pausing, so someone reading the results can stay
WARNING_SECONDS = 60
# The Google sign-in tab has nothing more to do once it has shown its message
CALLBACK_MINUTES = 2


def idle_minutes():
    """Minutes of inactivity before the page pauses; 0 = never. Hosted default 15, local default 0."""
    default = "15" if ai_providers.is_hosted() else "0"
    try:
        return max(0.0, float(os.environ.get("FTM_IDLE_PAUSE_MINUTES", default)))
    except ValueError:
        return float(default)


_SCRIPT = """<script>
(() => {
  const cfg = __CFG__;
  const w = window;
  if (!w.__ftmIdle) {
    const s = w.__ftmIdle = {last: Date.now(), cfg: cfg, banner: null, paused: false};
    const seen = () => {
      s.last = Date.now();
      if (s.banner) { s.banner.remove(); s.banner = null; }
    };
    ["mousemove", "mousedown", "keydown", "wheel", "scroll", "touchstart", "focus"].forEach(
      ev => w.addEventListener(ev, seen, {passive: true, capture: true}));
    const pause = () => {
      s.paused = true;
      const html = s.cfg.page.split("__BACK__").join(location.origin + location.pathname);
      try {
        location.replace(URL.createObjectURL(new Blob([html], {type: "text/html"})));
      } catch (e) {
        location.replace("about:blank");
      }
    };
    setInterval(() => {
      const c = s.cfg;
      if (s.paused || !(c.minutes > 0)) return;
      if (c.running) { s.last = Date.now(); return; }  // never during a run in this tab
      const left = c.minutes * 60000 - (Date.now() - s.last);
      if (left <= 0) { pause(); return; }
      if (left <= c.warning * 1000 && !s.banner) {
        const b = s.banner = document.createElement("div");
        b.setAttribute("role", "status");
        b.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:100000;"
          + "background:#fff8e1;color:#31333f;border:1px solid #f0c36d;border-radius:8px;padding:10px 16px;"
          + "box-shadow:0 2px 8px rgba(0,0,0,.15);font-family:system-ui,sans-serif;font-size:14px;max-width:90vw";
        b.textContent = "\\u23f8\\ufe0f No activity: this page will pause in a minute to save server costs. "
          + "Move the mouse or press a key to stay.";
        document.body.appendChild(b);
      }
    }, 1000);
  }
  // Every render: take the latest settings; a rerun (run finished, button clicked) counts as activity
  w.__ftmIdle.cfg = cfg;
  w.__ftmIdle.last = Date.now();
})();
</script>"""


# The local page a paused tab shows. Sent inside the config with every "<" escaped: Streamlit's
# HTML sanitizer drops a script whose text looks like markup.
_PAUSED_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paused · FTM Language Generator</title></head>
<body style="font-family:system-ui,sans-serif;max-width:560px;margin:15vh auto;padding:0 16px;color:#31333f">
<h2>⏸️ The Language Generator is paused</h2>
<p>This page had no activity for {minutes} minutes, so it disconnected from the server to save hosting costs.</p>
{hosted_note}
<p><a href="__BACK__" style="display:inline-block;padding:8px 18px;background:#ff4b4b;color:#fff;border-radius:8px;text-decoration:none">▶ Resume</a></p>
</body></html>"""
_HOSTED_NOTE = ("<p>Language packages that weren't downloaded have been removed from the server. "
                "Generate the language again if you still need it.</p>")


def install(running, minutes=None):
    """Add or refresh the idle watcher. running: a run is queued or in progress in this tab."""
    minutes = idle_minutes() if minutes is None else minutes
    if minutes <= 0:
        return
    cfg = {"minutes": minutes, "running": bool(running), "warning": min(WARNING_SECONDS, minutes * 30),
           "t": time.time(),  # new content on every render, so the script runs again
           "page": _PAUSED_PAGE.format(minutes=f"{minutes:g}",
                                       hosted_note=_HOSTED_NOTE if ai_providers.is_hosted() else "")}
    config = json.dumps(cfg, ensure_ascii=False).replace("<", "\\u003c")
    st.html(_SCRIPT.replace("__CFG__", config), unsafe_allow_javascript=True)
