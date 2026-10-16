# Contract: Package download (UI) and `package_store` (module)

## UI: in `render_summary`, after the unused-audio / AI sections, before "Download log"

| Availability | Element(s) |
|---|---|
| `available` | `st.download_button("📦 Download language package (.zip)", data=<callable>, file_name=<zip name>, mime="application/zip", key=f"pkg_{lang}_{started}", on_click="ignore", type="primary")`. Below it, a caption: **hosted** `Kept on the server only until you close or reload this page. Download it now.`; **local** `Also saved in lang/<lang>/ on this computer.` |
| `regenerating` | `st.caption("📦 <Lang> is being generated again right now, so this package isn't available.")` |
| `replaced` | `st.caption("📦 This package was replaced by a later run of <Lang>. Download it from that run.")` |
| `gone` | `st.caption("📦 This package is no longer on the server. Generate <Lang> again to get it.")` |
| none (error/cancelled/unauthenticated) | nothing |

- The button never reruns the page (`on_click="ignore"`). The zip is built on click, on a worker thread.
- If the package became unavailable between render and click, the callable raises `package_store.Unavailable`. Streamlit shows its download error, and the next render shows the right note.

## `language_automation/package_store.py`

```text
class Unavailable(Exception)

claim(lang, session_id) -> run_id                     # new uuid, entry active=True (replaces any entry; remembers it)
finish(lang, run_id, touched=True)                    # active=False if the entry still has this run_id;
                                                      # touched=False (stopped before the wipe): earlier owner restored
sweep(...)                                            # orphans = languages claimed in THIS process with no entry;
                                                      # pre-existing folders are never deleted
availability(lang, run_id, state) -> "available" | "regenerating" | "replaced" | "gone" | None
build_zip(lang, run_id) -> bytes                      # re-checks availability; raises Unavailable
owned_by(lang, session_id) -> bool                    # finished entry owned by this session (hosted "already generated" check)
sweep(is_alive, now) -> list[str]                     # one janitor pass; returns the removed lang keys
start_janitor(is_alive, interval=15, grace=60)        # daemon thread calling sweep(); hosted only, idempotent
```

- Registry state is module-level, created once per process. `app.py` calls `start_janitor` from a `st.cache_resource` function so it runs once.
- `is_alive(session_id) -> bool` is injected (`app.session_alive`), so the module has no Streamlit dependency.
- Server log line per removal: `🧹 Cleaned up lang/<lang> (session ended)` or `🧹 Cleaned up lang/<lang> (no owner)`. It goes to stdout, the server log only, and isn't part of the pipeline log contract.

## Unchanged

- Pipeline log prefixes (constitution IV), `generate_language.py`, CLI behaviour, local `lang/` persistence.
