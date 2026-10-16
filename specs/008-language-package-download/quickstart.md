# Quickstart / Validation: Language Package Download

See [contracts/package-download.md](contracts/package-download.md) for the exact UI texts and module API.

## V1. Registry and janitor logic (no Streamlit, no Drive)

From `language_automation/`, a throwaway script in the session scratchpad (not committed):
1. Create fake `lang/zz_a/` and `lang/zz_b/` folders, each with a JSON file and `audios/x.mp3`.
2. `claim`/`finish` them for sessions `s1` / `s2`.
3. `sweep(is_alive=lambda s: s == "s2", now=t)` twice, the second time with `t + 61`.

Expected:
- `zz_a` is removed only on the second pass;
- `zz_b` is untouched;
- an unclaimed `lang/zz_orphan/` is removed;
- an `active` entry is never removed.

Also check:
- `build_zip` on `zz_b` has entries `zz_b/`, `zz_b/images/`, `zz_b/ftm_zz_b.json`, `zz_b/audios/x.mp3`;
- `availability` returns `replaced` after a second `claim`;
- `build_zip` then raises `Unavailable`.

Remove the fake folders afterwards.

## V2. Local page (FTM_HOSTED unset)

`python -m streamlit run app.py`, then generate a small language (e.g. `Marathi`, about 11 MB).
- The summary shows **📦 Download language package (.zip)** with the "Also saved in lang/marathi/" caption.
- Downloading gives `Marathi_<stamp>.zip`. Unzipped, `marathi/` matches `lang/marathi/` (same file list; identical JSON, checked with `fc`/`diff`).
- Clicking doesn't rerun the page.
- Regenerate Marathi: the earlier run under Previous runs shows "replaced by a later run".
- Close the tab: `lang/marathi/` is **still there** (local, no cleanup).

## V3. Hosted: download (US1)

Deploy (`gcloud builds submit --config cloudbuild.yaml --project=ftm-language-generator`). On the service URL:
- generate a language: the button appears with the hosted note;
- the zip matches a local build of the same language (V2 check);
- a batch `Marathi, Hindi`: Marathi's button works while Hindi is still running, and Hindi's run isn't interrupted.

## V4. Hosted: cleanup (US2)

1. Generate a language and note the time. Server log: no `🧹` line yet.
2. Close the tab. Within 2 minutes, Cloud Logging (`gcloud run services logs read ftm-language-generator --region=us-central1 --project=ftm-language-generator --limit=50`) shows `🧹 Cleaned up lang/<lang> (session ended)`.
3. Two tabs, A and B: generate language X in A and Y in B, then close A. Only X is cleaned. B's Y download still works.
4. Close a tab mid-run: the run is cancelled (existing behaviour), then its partial folder is cleaned within 2 minutes.
5. Reload the page after a run: the old session's package is cleaned. The new session doesn't offer the old run, because its history is empty.

## V5. Hosted: replaced / regenerating (US2-2, US2-3)

- Tab A generates X. Tab B generates X again: during B's run, A's X shows "being generated again"; after it, "replaced by a later run".
- When A closes, B's X package is **not** deleted.

## V6. Large package and memory (FR-012, SC-007)

Generate the largest available language (or a test language near 300 MB) and download it. Then check Cloud Run → Metrics → Memory utilization:
- no restart / OOM in the logs;
- memory drops back within 2 minutes of closing the tab.

If it fails at 2 GiB, set `--memory=4Gi` in `cloudbuild.yaml`, redeploy and repeat.

## V7. Pipeline unaffected

Run `python generate_language.py Hausa` from the CLI: same output as before, nothing deleted afterwards.
