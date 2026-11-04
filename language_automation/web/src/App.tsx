// The Feed the Monster language generator page (spec 012; flow from specs 003, 004, 005, 006, 008).
// The page talks to the server only to load its settings, to run a language (one streaming request
// for the run's length) and to fetch the package, so an open tab costs nothing while idle.
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { fetchPackage, getConfig, getExisting, HttpError, streamRun, type RunEvent } from "./api";
import { loadGoogle, requestToken, SignInError, SIGNIN_TIMEOUT_SECONDS, stillValid } from "./googleSignin";
import { finalTitle, finishPipeline, handleLine, newRun, stopBeforeRun } from "./runParser";
import type { Run, ServerConfig, SignIn } from "./types";
import { RegenerateDialog } from "./components/RegenerateDialog";
import { RunExpander, StatusBox } from "./components/RunViews";
import { Alert, Caption, Inline, Toggle } from "./components/ui";

const VALID_NAME = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$/; // lang_paths.validate_language_name
const BUSY_TEXT = "⏳ Another language is being generated right now. Please try again when it finishes.";

type Confirm = { langs: string[]; existing: Record<string, number> };

export default function App() {
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [langInput, setLangInput] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<string[] | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [aiCheck, setAiCheck] = useState(false);
  const [showTokens, setShowTokens] = useState(false);
  const [running, setRunning] = useState(false);
  const [otherRun, setOtherRun] = useState(false);
  const [history, setHistory] = useState<Run[]>([]); // newest first, like the Streamlit page
  const [batch, setBatch] = useState<Run[]>([]); // the runs of the batch in progress
  const [lastBatch, setLastBatch] = useState(0);
  const [, setTick] = useState(0);
  const [signedInAs, setSignedInAs] = useState<string | null>(null); // shown under the form

  const signin = useRef<SignIn | null>(null); // tab memory only (FR-006)
  const signinClick = useRef<(() => void) | null>(null);
  const abort = useRef<AbortController | null>(null);
  const historyRef = useRef<Run[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const frame = useRef<number | null>(null);

  // Runs are updated in place as lines arrive; redraw at most once per frame
  const redraw = useCallback(() => {
    if (frame.current !== null) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      setTick((t) => t + 1);
    });
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const c = await getConfig();
      setConfig(c);
      setConfigError(null);
      setOtherRun(c.busy);
    } catch (e) {
      setConfigError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void loadConfig();
    loadGoogle().catch(() => undefined); // ready before the first click; failures are reported on sign-in
    // Closing or reloading the tab ends the run's request, so the server stops the run (FR-008)
    const onHide = () => abort.current?.abort();
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [loadConfig]);

  const hosted = !!config?.hosted;
  const signinSetUp = !!config?.signin;
  const busy = running || otherRun || !config || !signinSetUp;

  // ---------------------------------------------------------------- sign-in
  /** The tab's Google token, asking for it with the "Sign in with Google" button when needed. */
  async function ensureSignIn(run: Run): Promise<SignIn> {
    if (stillValid(signin.current)) return signin.current;
    const cfg = config!.signin!;
    run.showSigninButton = true;
    redraw();
    try {
      return await new Promise<SignIn>((resolve, reject) => {
        const timer = window.setTimeout(() => {
          signinClick.current = null;
          reject(new SignInError("cancelled", "Google sign-in wasn't completed"));
        }, SIGNIN_TIMEOUT_SECONDS * 1000);
        signinClick.current = () => {
          signinClick.current = null;
          requestToken(cfg.client_id).then(
            (s) => {
              window.clearTimeout(timer);
              resolve(s);
            },
            (e) => {
              window.clearTimeout(timer);
              reject(e);
            },
          );
        };
      });
    } finally {
      run.showSigninButton = false;
      redraw();
    }
  }

  // ---------------------------------------------------------------- one language
  async function runOne(run: Run): Promise<"ok" | "stop"> {
    let token: SignIn;
    try {
      token = await ensureSignIn(run);
    } catch (e) {
      const err = e instanceof SignInError ? e : new SignInError("failed", "sign-in failed");
      stopBeforeRun(run, err.kind === "cancelled" ? "cancelled" : "error", err.message);
      redraw();
      return "stop";
    }
    signin.current = token;

    let pipelineEnded = false;
    let packageId: string | null = null;
    const controller = new AbortController();
    abort.current = controller;

    const onEvent = (e: RunEvent) => {
      switch (e.type) {
        case "busy":
          stopBeforeRun(run, "cancelled", "another language is being generated right now");
          run.auth = { kind: "warning", text: BUSY_TEXT };
          setOtherRun(true);
          break;
        case "auth":
          if (e.status === "ok") {
            run.account = e.email;
            if (signin.current) signin.current.email = e.email;
            setSignedInAs(e.email ?? null);
          } else {
            signin.current = null; // refused or expired: the next Generate asks Google again
            setSignedInAs(null);
            stopBeforeRun(run, "error", e.reason || "sign-in failed");
          }
          break;
        case "line":
          handleLine(run, e.text);
          break;
        case "pipeline_end":
          pipelineEnded = true;
          finishPipeline(run, e.returncode);
          if (!run.authenticated) {
            signin.current = null;
            setSignedInAs(null);
          }
          break;
        case "ai_start":
          run.aiRunning = true;
          break;
        case "ai_line":
          run.aiLog.push(e.text);
          break;
        case "ai_report": {
          const report = { ...e.report, warnings: e.report.warnings ?? [] };
          for (const w of report.warnings) {
            run.aiLog.push(
              `AI ${w.confidence} ${w.category}: ${w.text} → ${w.suggestion || "-"} (${w.reason}) at ${(w.locations ?? []).join(", ")}`,
            );
          }
          run.ai = report;
          run.aiRunning = false;
          run.title = finalTitle(run);
          break;
        }
        case "end":
          run.mp3Count = e.mp3_count ?? null;
          packageId = e.package_id ?? null;
          break;
        case "ping":
          return;
      }
      redraw();
    };

    try {
      await streamRun(run.lang, aiCheck, token.token, controller.signal, onEvent);
    } catch (e) {
      if (controller.signal.aborted) return "stop";
      if (e instanceof HttpError && e.status === 409) {
        stopBeforeRun(run, "cancelled", "another language is being generated right now");
        run.auth = { kind: "warning", text: BUSY_TEXT };
        setOtherRun(true);
        redraw();
        return "stop";
      }
      if (!pipelineEnded && run.state === "running") {
        const reason = e instanceof Error ? e.message : String(e);
        if (run.authenticated) {
          run.errors.push(`❌ The connection to the server was lost before the run finished (${reason}).`);
          finishPipeline(run, -1);
        } else {
          stopBeforeRun(run, "error", reason.replace(/\.$/, ""));
        }
      }
    } finally {
      abort.current = null;
    }
    if (run.state === "running") {
      // The stream ended without the pipeline's end (server restarted or redeployed)
      run.errors.push("❌ The connection to the server was lost before the run finished.");
      if (run.authenticated) finishPipeline(run, -1);
      else stopBeforeRun(run, "error", "the connection to the server was lost");
    }
    run.aiRunning = false;
    redraw();

    // Spec 008/012: fetch the package into this tab now; an earlier package of this language is replaced
    if (packageId) {
      const key = run.lang.trim().toLowerCase();
      for (const other of [...historyRef.current, ...batchRef.current]) {
        if (other !== run && other.lang.trim().toLowerCase() === key && other.pkg && other.pkg.status !== "error") {
          other.pkg = { status: "replaced" };
        }
      }
      run.pkg = { status: "fetching" };
      redraw();
      try {
        run.pkg = { status: "ready", blob: await fetchPackage(packageId) };
      } catch (e) {
        run.pkg = { status: "error", error: (e instanceof Error ? e.message : String(e)).replace(/\.$/, "") };
      }
      redraw();
    }
    return (run.state === "cancelled" || run.state === "error") && !run.authenticated ? "stop" : "ok";
  }

  const batchRef = useRef<Run[]>([]);

  // ---------------------------------------------------------------- a batch (comma-separated languages)
  async function startBatch(langs: string[]) {
    if (!langs.length) return;
    setRunning(true);
    const done: Run[] = [];
    batchRef.current = [];
    setBatch([]);
    try {
      for (const lang of langs) {
        const run = newRun(lang);
        batchRef.current = [...batchRef.current, run];
        setBatch(batchRef.current);
        const outcome = await runOne(run);
        done.unshift(run);
        if (outcome === "stop") break; // sign-in failed or the tab closed: don't start the remaining languages
      }
    } finally {
      historyRef.current = [...done, ...historyRef.current];
      setHistory(historyRef.current);
      setLastBatch(done.length);
      batchRef.current = [];
      setBatch([]);
      setRunning(false);
    }
  }

  // ---------------------------------------------------------------- form
  async function onGenerate(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setFormError(null);
    setSkipped(null);
    const langs = langInput.split(",").map((l) => l.trim()).filter(Boolean);
    const invalid = langs.filter((l) => !VALID_NAME.test(l));
    if (!langs.length) {
      setFormError("Please type a language name.");
      return;
    }
    if (invalid.length) {
      setFormError(`Invalid language name: ${invalid.join(", ")}. Use letters, digits, spaces, - or _.`);
      return;
    }
    setLangInput(""); // the form clears on submit

    let existing: Record<string, number> = {};
    if (hosted) {
      // Hosted: only the packages this tab holds count (spec 008/012)
      for (const l of langs) {
        const own = historyRef.current.find((r) => r.lang.trim().toLowerCase() === l.toLowerCase() && r.pkg?.status === "ready");
        if (own) existing[l] = own.mp3Count ?? 0;
      }
    } else {
      setRunning(true); // keep Generate disabled while asking the server
      try {
        existing = await getExisting(langs);
      } finally {
        setRunning(false);
      }
    }
    if (Object.keys(existing).length) setConfirm({ langs, existing });
    else void startBatch(langs);
  }

  /** Yes: run everything. No (or the dialog closed): run only the languages that don't exist yet. */
  function answerRegenerate(regenerate: boolean) {
    const c = confirm;
    setConfirm(null);
    if (!c) return;
    if (!regenerate) setSkipped(Object.keys(c.existing));
    void startBatch(regenerate ? c.langs : c.langs.filter((l) => !(l in c.existing)));
  }

  function startNewLanguage() {
    setLastBatch(0);
    setLangInput("");
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => inputRef.current?.focus(), 300);
  }

  /** Forget this tab's sign-in: the next Generate opens Google's account chooser again. */
  function switchAccount() {
    signin.current = null;
    setSignedInAs(null);
  }

  async function checkAgain() {
    await loadConfig();
  }

  // ---------------------------------------------------------------- page
  const latest = history.slice(0, lastBatch);
  const earlier = history.slice(lastBatch);
  const allDone = latest.length > 0 && !busy && latest.every((r) => r.state === "complete" || r.state === "warning");
  const ai = config?.ai;

  return (
    <main className="main stack">
      <h1>🌍 Feed the Monster · Language Generator</h1>
      <Caption>
        <Inline
          text={
            "Fetches the language sheet, game JSON and audio files from Google Drive into `lang/<language>/`, then checks for " +
            "unused and missing audios. When you press Generate, you'll be asked to sign in with your Curious Learning Google " +
            "account in a Google popup (once per page visit)."
          }
        />
      </Caption>
      {configError && <Alert kind="error">The server couldn't be reached: {configError}. Reload the page to try again.</Alert>}
      {config && !config.signin && (
        <Alert kind="error">
          Google sign-in isn't set up on this server: {config.signin_error}. No language can be generated.
        </Alert>
      )}

      <form className="form" onSubmit={onGenerate}>
        <label className="widget-label" htmlFor="lang_input">
          Language name
          <span
            className="help"
            title="The same name you would type after `python generate_language.py`. Separate several with commas."
          >
            ?
          </span>
        </label>
        <input
          id="lang_input"
          ref={inputRef}
          type="text"
          autoComplete="off"
          value={langInput}
          onChange={(e) => setLangInput(e.target.value)}
          placeholder="e.g. Hausa  (or several: Hausa, IndianEnglish)"
          disabled={busy}
        />
        <button type="submit" className="btn primary" disabled={busy}>
          Generate
        </button>
      </form>

      <div>
        <Toggle
          label="🤖 AI language check"
          checked={aiCheck}
          disabled={busy}
          onChange={setAiCheck}
          help="After generating, an AI reviews the language's letters, words and feedback sentences and suggests corrections. One request per language; unchanged content isn't sent again."
        />
      </div>
      {aiCheck && ai && (
        <>
          <Caption>
            {ai.reason ? (
              <Inline text={`Not configured: ${ai.reason}.${hosted ? "" : " See `.env.example`."}`} />
            ) : (
              `Uses ${ai.provider} (${ai.model}).`
            )}
          </Caption>
          <div className="indented">
            <Toggle
              label="🔢 Show tokens used"
              checked={showTokens}
              disabled={busy}
              onChange={setShowTokens}
              help="Shows the model and the real input and output tokens of each AI check, to compare the cost of models and providers."
            />
          </div>
        </>
      )}

      {signedInAs && !running && (
        <Caption>
          🔐 Signed in as {signedInAs} ·{" "}
          <a href="#" onClick={(e) => { e.preventDefault(); switchAccount(); }}>
            Use another account
          </a>
        </Caption>
      )}
      {formError && <Alert kind="error">{formError}</Alert>}
      {skipped && <Alert kind="info">Not regenerated: {skipped.join(", ")} (kept as it is).</Alert>}
      {otherRun && !running ? (
        <Alert kind="warning">
          ⏳ Another language is being generated right now. Check again when it finishes.
          <div>
            <button type="button" className="btn" onClick={() => void checkAgain()}>
              Check again
            </button>
          </div>
        </Alert>
      ) : null}

      {confirm && <RegenerateDialog existing={confirm.existing} hosted={hosted} onAnswer={answerRegenerate} />}

      {batch.length > 0 && (
        <>
          <Alert kind="info">⚠️ Keep this page open until the run finishes. Generate is disabled until then.</Alert>
          {batch.map((run) => (
            <StatusBox key={run.id} run={run} hosted={hosted} showTokens={showTokens} onSignIn={() => signinClick.current?.()} />
          ))}
        </>
      )}

      {latest.length > 0 && (
        <>
          {allDone && (
            <div className="banner">
              <Alert kind="success">✅ {latest.map((r) => r.lang).join(", ")} generated. You can add another language now.</Alert>
              <button type="button" className="btn primary stretch" onClick={startNewLanguage}>
                ➕ Add another language
              </button>
            </div>
          )}
          <h2 className="subheader">Latest run</h2>
          {latest.map((run) => (
            <RunExpander key={run.id} run={run} expanded hosted={hosted} showTokens={showTokens} />
          ))}
          {allDone && (
            <div>
              <button type="button" className="btn primary" onClick={startNewLanguage}>
                ➕ Add another language
              </button>
            </div>
          )}
        </>
      )}
      {earlier.length > 0 && (
        <>
          <hr className="divider" />
          <h2 className="subheader">Previous runs</h2>
          {earlier.map((run) => (
            <RunExpander key={run.id} run={run} expanded={false} hosted={hosted} showTokens={showTokens} />
          ))}
        </>
      )}
    </main>
  );
}
