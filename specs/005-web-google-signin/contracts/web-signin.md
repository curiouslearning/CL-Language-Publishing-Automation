# Contract: Web Sign-In (app.py ↔ Google ↔ browser)

## Starting a sign-in

When: Generate is pressed and `st.session_state` has no `google_signin` (see [data-model.md](../data-model.md)).

1. Create a `PendingSignIn` (`state`, `browser_nonce`, `code_verifier`, `session_id`).
2. Render, in the run's status box:
   - `🔐 Authentication in progress: please sign in with your Curious Learning Google account. The run is cancelled if sign-in isn't completed within 3 minutes.`
   - `st.link_button("Sign in with Google", auth_url)`, which opens in a new tab.
   - A fixed script that sets the cookie `ftm_signin=<browser_nonce>; Path=/; SameSite=Lax; Max-Age=600[; Secure]`.
3. Poll the pending store every 0.2 s, watching for:
   - a final status;
   - 180 s passing → cancelled: "Google sign-in wasn't completed";
   - the tab closing → cancelled.

**Authorization URL**: `https://accounts.google.com/o/oauth2/auth` with these parameters:
- `client_id`, `redirect_uri=FTM_PUBLIC_URL`, `response_type=code`, `state`
- `scope="openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/spreadsheets.readonly"`
- `access_type=offline`, `prompt="select_account consent"`, `hd=curiouslearning.org`
- `code_challenge` with `code_challenge_method=S256`

## Callback

Request: `GET FTM_PUBLIC_URL?state=<state>&code=<code>[&scope=…&hd=…]`, or `?state=<state>&error=access_denied`.

The app detects `code` or `error` in `st.query_params` before drawing anything else. It then runs callback mode and calls `st.stop()`, so the generator UI is not drawn in this tab.

| Condition | Pending status | Callback tab shows |
|---|---|---|
| Unknown, expired or already-used `state` | — | "This sign-in link has already been used or has expired. Go back to the generator and press Generate again." |
| `ftm_signin` cookie ≠ nonce | `failed` | "Please complete the sign-in in the same browser where you pressed Generate." |
| `error` param present | `failed` | "Sign-in was cancelled or didn't complete." |
| Exchange or ID-token verification fails | `failed` | "Sign-in failed. Please try again." (details go only to the server log, never tokens) |
| Verified, but not admitted (R3) | `refused` | "Only Curious Learning (curiouslearning.org) accounts can add languages. You signed in as <email>." |
| Verified and admitted | `success` | "✅ Signed in as <email>. Return to the generator tab: your run continues there. You can close this tab." |

After handling, the query params are cleared (`st.query_params.clear()`), so a reload doesn't replay the code.

**Admission rule**: `verify_oauth2_token` succeeds, `email_verified is True`, `hd == "curiouslearning.org"`, and `email.lower().endswith("@curiouslearning.org")`.

## Generator tab: outcome → UI (spec 004 flow preserved)

| Outcome | Run box |
|---|---|
| `success` | Store `google_signin`. Start the pipeline subprocess with `FTM_GOOGLE_CREDENTIALS`. The pipeline prints `🔐 Authenticating…` then `✅ Authenticated as <email>`, and the steps and log appear. |
| `refused` | `❌ Authentication failed: only Curious Learning (curiouslearning.org) accounts can add languages (signed in as <email>). Nothing was created or deleted.` The title is "Authentication failed", with no steps. The remaining queued languages are not started. |
| `failed` | `❌ Authentication failed: <reason>. Nothing was created or deleted.` (same as above) |
| timeout or tab closed | Existing cancelled wording: `⏹️ Authentication cancelled: … Nothing was created or deleted.` |

When the session is already signed in, no link is shown. The pipeline runs straight away, and its `✅ Authenticated as` line still appears before the steps (FR-010).

## Setup error (fail closed)

If the web client config is missing or invalid, or `FTM_HOSTED=1` with a non-https `FTM_PUBLIC_URL`:
- **Page:** a top-of-page `st.error("Google sign-in isn't set up on this server: <reason>. No language can be generated.")`.
- **Form:** Generate is disabled.
- **Runs:** none are started.
