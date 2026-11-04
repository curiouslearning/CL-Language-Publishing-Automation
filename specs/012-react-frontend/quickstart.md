# Quickstart: React Frontend

## One-time

1. Google Cloud console → APIs & Services → Credentials → the **Web application** OAuth client in `ftm-language-generator` → **Authorized JavaScript origins**: add `http://localhost:8080`, `http://localhost:5173` and the Cloud Run URL (`https://ftm-language-generator-<project number>.us-central1.run.app`). The redirect URI is no longer used.
2. `python -m pip install -r requirements.txt` and Node.js 20+.

## Run locally (built page)

```bash
cd language_automation/web && npm ci && npm run build
cd .. && python server.py            # http://localhost:8080
```

## Develop the page (live reload)

```bash
cd language_automation && python server.py        # API on :8080
cd language_automation/web && npm run dev          # page on :5173, /api proxied to :8080
```

## Verify

1. Open the page, open DevTools → Network: after load, no request stays pending.
2. Generate `Hausa`, sign in in the popup, compare steps, summary and zip with an earlier Streamlit run.
3. Close the tab mid-run: the server log shows the run cancelled; a new tab can generate right away.
4. Hosted: leave a tab open 20 minutes; Cloud Run's instance count goes to 0.
