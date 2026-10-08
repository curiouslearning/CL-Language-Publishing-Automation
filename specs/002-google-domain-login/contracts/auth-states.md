# Contract: Authentication Stages in the Web Page

This is what the user sees, in order. No automation step (spec 001, Steps 1–7) is ever drawn
unless the most recent "Authenticating…" stage ended in **OK**.

## Stage A: on Generate while not signed in

```
Language form  ──[Generate]──►  pending request saved for this browser
                                 └─► straight to Google's login page (no steps drawn)
        ├─ login completed ──► back to the generator → Stage B (continues with the saved language)
        └─ tab closed / cancelled / not finished ──► request cancelled; nothing ran, nothing
             was created, the generator stays free. The pending request expires after 10 min.
             If the visitor comes back not signed in: "Sign-in was cancelled or didn't complete.
             Please try again." The form is empty.
```

A signed-in visitor sees ✅ "Signed in as <email>" [Sign out] above the form, plus previous runs.
Previous runs are hidden from anyone not signed in or refused.

## Stage B: on Generate while signed in, or on return from login with a pending request

```
[Authenticating…]   (domain check, then the Google token: audience, email, Drive scope,
                     time left ≥ MIN_TOKEN_SECONDS, sign-in age ≤ 8 h)
   ├─ refused ─────────────► ❌ "Only Curious Learning (curiouslearning.org) accounts can generate
   │                          languages. You're signed in as <email>."  [Use a different account]
   │                          No form, no history, no run, nothing created.
   ├─ token expired/short ─► ❌ "Your Google sign-in has expired. Please sign in again."
   │                          [Sign in again]  No run, nothing created.
   ├─ Google unreachable ──► ❌ "Couldn't confirm your sign-in with Google. Please try again."
   │                          No run, nothing created.
   └─ OK ──────────────────► ✅ "Signed in as <email>"
                              then: Steps 1–7 appear, and the run starts
                              (existing lock: if busy, "another language is being generated…")
```

## Messages (exact text)

| Key | Text |
|---|---|
| `refused` | Only Curious Learning (curiouslearning.org) accounts can generate languages. You're signed in as {email}. |
| `cancelled` | Sign-in was cancelled or didn't complete. Please try again. |
| `expired` | Your Google sign-in has expired. Please sign in again. |
| `unreachable` | Couldn't confirm your sign-in with Google. Please try again. |
| `ok` | Signed in as {email} |
| `no_drive` | Google Drive access wasn't granted during sign-in. Please sign in again and allow Drive access. *(Added during implementation: Google's consent screen lets users untick Drive.)* |

## During a run

- If the tab that started the run is closed, the run is cancelled within about 1 second: the
  subprocess is killed, the lock is released, and the run is recorded as `cancelled`.
- If the run waits more than 3 minutes for a Google sign-in, it is cancelled the same way.
- Message: "⏹️ Run cancelled: {reason}. Nothing was created or deleted." This text is used when
  the run stopped before the wipe step. Otherwise it ends "lang/{lang} may be incomplete, so
  generate it again."

## Guarantees

- No Drive call, folder operation or subprocess happens before Stage B ends in OK (FR-004).
- The access token appears in no message, log line or downloaded file.
