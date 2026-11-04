// A run on the page: the live status box while it runs, the summary after it, and the
// "Latest run" / "Previous runs" expanders (port of app.py's run_pipeline UI, render_summary, show_run).
import type { Run, RunState } from "../types";
import { stepLines } from "../runParser";
import { SIGNIN_TIMEOUT_SECONDS } from "../googleSignin";
import { AiLog, AiSection } from "./AiSection";
import { Alert, Caption, CodeLog, DownloadButton, Expander, Inline, saveFile } from "./ui";

const STATE_ICONS: Record<RunState, string> = { complete: "✅", warning: "⚠️", error: "❌", running: "⏹️", cancelled: "⏹️" };

function stamp(run: Run) {
  return run.started.replace(/:/g, "-").replace(" ", "_");
}

function Steps({ run }: { run: Run }) {
  const lines = stepLines(run);
  if (!lines.length) return null;
  return (
    <div className="steps">
      {lines.map((l, i) => (
        <div key={i}>{l}</div>
      ))}
    </div>
  );
}

function Errors({ run }: { run: Run }) {
  if (!run.errors.length) return null;
  return (
    <Alert kind="error" pre>
      {run.errors.join("\n\n")}
    </Alert>
  );
}

function Package({ run, hosted }: { run: Run; hosted: boolean }) {
  const pkg = run.pkg;
  if (!pkg) return null;
  switch (pkg.status) {
    case "fetching":
      return <Caption>📦 Preparing the language package…</Caption>;
    case "error":
      return <Caption>📦 The language package couldn't be fetched: {pkg.error}. Generate {run.lang} again to get it.</Caption>;
    case "replaced":
      return <Caption>📦 This package was replaced by a later run of {run.lang}. Download it from that run.</Caption>;
    case "ready":
      return (
        <>
          <DownloadButton primary label="📦 Download language package (.zip)" onClick={() => saveFile(pkg.blob, `${run.lang}_${stamp(run)}.zip`)} />
          <Caption>
            {hosted ? (
              "Kept in this page only until you close or reload it. Download it now."
            ) : (
              <Inline text={`Also saved in \`lang/${run.lang.trim().toLowerCase()}/\` on this computer.`} />
            )}
          </Caption>
        </>
      );
  }
}

export function RunSummary({ run, hosted, showTokens }: { run: Run; hosted: boolean; showTokens: boolean }) {
  const logButton = (
    <DownloadButton label="Download log" onClick={() => saveFile(run.log.join("\n"), `${run.lang}_${stamp(run)}.log`)} />
  );
  // Sign-in never completed: no audio check ran, so there is nothing else to summarize
  if (!run.authenticated) return logButton;

  const lookalikeFor: Record<string, string> = {};
  for (const pair of run.lookalike) {
    const [drive, json] = pair.split(" ≈ ");
    if (json !== undefined) lookalikeFor[json] = drive;
  }
  const missing = [...run.missing].sort();
  const deleted = [...run.deleted].sort();

  return (
    <>
      <h4>🎧 Audio check</h4>

      {missing.length ? (
        <Alert kind="warning">
          <Inline
            text={`**Missing audios:** ${missing.length} audio file(s) are referenced in the JSON but were not found on Drive:`}
          />
          <ul>
            {missing.map((m) => (
              <li key={m}>
                {m}
                {lookalikeFor[m] ? `  (Drive has a look-alike: ${lookalikeFor[m]}, see below)` : ""}
              </li>
            ))}
          </ul>
        </Alert>
      ) : run.missingChecked ? (
        <Alert kind="success">
          <Inline text="**Missing audios:** none. Every audio referenced in the JSON is available." />
        </Alert>
      ) : (
        <Caption>Missing-audio check did not run (the pipeline stopped earlier).</Caption>
      )}

      {run.lookalike.length > 0 && (
        <Alert kind="warning">
          <Inline text="**Name differs only in upper/lowercase** (Drive file ≈ name in the sheet). Rename one so they match:" />
          <ul>
            {run.lookalike.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </Alert>
      )}

      {run.standardized.length > 0 && (
        <Caption>🔤 Look-alike vowel signs written in the standard form: {run.standardized.join(", ")}</Caption>
      )}

      {deleted.length ? (
        <Expander
          title={<Inline text={`🗑 **Unused audios removed:** ${deleted.length} file(s) from Drive are not used in the JSON`} />}
        >
          <ul className="md">
            {deleted.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </Expander>
      ) : run.unusedChecked ? (
        <Alert kind="success">
          <Inline text="**Unused audios:** none. Every downloaded audio is used in the JSON." />
        </Alert>
      ) : (
        <Caption>Unused-audio check did not run (the pipeline stopped earlier).</Caption>
      )}

      {run.ai && (
        <>
          <AiSection ai={run.ai} lang={run.lang} showTokens={showTokens} />
          <AiLog lines={run.aiLog} fileName={`${run.lang}_${stamp(run)}_ai.log`} />
        </>
      )}

      {run.mp3Count != null && (
        <Caption>
          <Inline text={`📂 ${run.mp3Count} mp3 file(s) in \`lang/${run.lang.toLowerCase()}/audios\``} />
        </Caption>
      )}

      <Package run={run} hosted={hosted} />
      {logButton}
    </>
  );
}

/** The run while it runs (st.status), until the batch ends and the page moves it to "Latest run". */
export function StatusBox(props: { run: Run; hosted: boolean; showTokens: boolean; onSignIn: () => void }) {
  const { run } = props;
  const running = run.state === "running" || run.aiRunning;
  const title = run.aiRunning ? "🤖 AI language check in progress…" : run.title;
  const icon = running ? (
    <span className="spinner" aria-label="Running" />
  ) : run.state === "complete" ? (
    <span className="icon-ok">✓</span>
  ) : (
    <span className="icon-err">✕</span>
  );
  return (
    <details className="box" open>
      <summary>
        {icon}
        <span>
          <strong>{run.lang}</strong> · {title}
        </span>
        <span className="chev" aria-hidden="true">⌄</span>
      </summary>
      <div className="body">
        {run.showSigninButton ? (
          <Alert kind="warning">
            🔐 Authentication in progress: please sign in with your Curious Learning Google account. The sign-in opens in a
            Google popup. The run is cancelled if sign-in isn't completed within {SIGNIN_TIMEOUT_SECONDS / 60} minutes.
            <div>
              <button type="button" className="btn primary" onClick={props.onSignIn}>
                Sign in with Google
              </button>
            </div>
          </Alert>
        ) : (
          <Alert kind={run.auth.kind}>{run.auth.text}</Alert>
        )}
        <Steps run={run} />
        {run.note && <Alert kind={run.note.kind}>{run.note.text}</Alert>}
        <Errors run={run} />
        {run.authenticated && <CodeLog lines={run.log} fixed />}
        {!running && <RunSummary run={run} hosted={props.hosted} showTokens={props.showTokens} />}
      </div>
    </details>
  );
}

/** A finished run under "Latest run" / "Previous runs" (show_run) */
export function RunExpander(props: { run: Run; expanded: boolean; hosted: boolean; showTokens: boolean }) {
  const { run } = props;
  return (
    <Expander title={`${STATE_ICONS[run.state] ?? ""} ${run.lang} · ${run.started}`} defaultOpen={props.expanded}>
      <Steps run={run} />
      <Errors run={run} />
      <CodeLog lines={run.log} />
      <RunSummary run={run} hosted={props.hosted} showTokens={props.showTokens} />
    </Expander>
  );
}
