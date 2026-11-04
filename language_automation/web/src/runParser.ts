// The pipeline's stdout log contract (constitution principle IV) → what the page shows.
// A line-for-line port of the Streamlit page's handle() and end-of-run logic (app.py, specs 001/004/005).
// Keep these prefixes in step with generate_language.py and the other pipeline scripts.
import type { Run } from "./types";

/** (marker, label, optional: only listed once the pipeline reaches it) */
export const STEPS: [string, string, boolean][] = [
  ["🔎 Checking Google Drive for", "Step 1/7 · Find the language on Google Drive", false],
  ["🧽 Preparing a clean language folder", "Step 2/7 · Prepare a clean language folder", false],
  ["📁 Created folder structure", "Step 3/7 · Create folders", false],
  ["🚀 Fetching language sheet", "Step 4/7 · Fetch the language sheet and game JSON", false],
  ["🎵 Fetching audio files", "Step 5/7 · Download audio files from Drive", false],
  ["🔗 Downloading audios linked from Drive", "Step 5b/7 · Download audios the JSON links to on Drive", true],
  ["🧹 Checking unused audios", "Step 6/7 · Remove unused audio files", false],
  ["🔍 Checking for missing audios", "Step 7/7 · Check for missing audio files", false],
];
/** The pipeline prints this once it has checked this run's Google sign-in; steps are only shown after it */
export const AUTH_DONE = "✅ Authenticated as ";
const MISSING_HEADER = "❌ Missing audio files:";
const DONE_MARKER = "🚀 All steps completed successfully";
/** Index of "Prepare a clean language folder": before it, nothing on disk was touched */
export const WIPE_STEP = 1;

// Exactly one of these is printed per audio file by download_convert_to_mp3
const AUDIO_FILE_DONE =
  /^(?:⏩ Skipped \(already exists\): |📄 Saved MP3: |🎵 Converted to MP3: |❌ FFmpeg conversion error: |❌ Failed after retries|❌ Skipped unsafe file name: )(.*)$/u;
const AUDIO_TOTAL = /^(?:🎵 Total audio files found: |🔗 Found )(\d+)/u;

function pad(n: number) {
  return String(n).padStart(2, "0");
}

export function timestamp(d = new Date()) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

let counter = 0;

export function newRun(lang: string): Run {
  return {
    id: `${Date.now()}-${++counter}`,
    lang,
    started: timestamp(),
    state: "running",
    title: "Authentication in progress…",
    authenticated: false,
    auth: { kind: "info", text: "🔐 Authentication in progress…" },
    showSigninButton: false,
    step: null,
    reached: [],
    details: {},
    note: null,
    finalSteps: null,
    log: [],
    errors: [],
    missing: [],
    deleted: [],
    lookalike: [],
    standardized: [],
    unusedChecked: false,
    missingChecked: false,
    inMissingList: false,
    audioTotal: null,
    audioDone: 0,
    aiRunning: false,
    aiLog: [],
    pkg: null,
  };
}

function basename(path: string) {
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1];
}

/** One pipeline output line (mutates run). */
export function handleLine(run: Run, line: string) {
  run.log.push(line);
  const stripped = line.trim();

  // Step changes
  STEPS.forEach(([marker, label], i) => {
    if (stripped.startsWith(marker)) {
      run.step = i;
      if (!run.reached.includes(i)) run.reached.push(i);
      run.inMissingList = false;
      run.audioTotal = null;
      run.audioDone = 0;
      run.note = { kind: "info", text: `⏳ ${label}` };
      run.title = label;
    }
  });

  // Signed in: from here on the steps and the log are shown
  if (stripped.startsWith(AUTH_DONE)) {
    run.authenticated = true;
    run.auth = { kind: "success", text: `✅ Authenticated as ${stripped.slice(AUTH_DONE.length)}` };
    run.title = "Authenticated";
  }

  // Audio download progress (Step 5 and 5b), counted once per file
  const total = AUDIO_TOTAL.exec(stripped);
  const done = AUDIO_FILE_DONE.exec(stripped);
  if (total && run.step !== null) {
    run.audioTotal = Number(total[1]);
    run.details[run.step] = `0/${run.audioTotal} files`;
    run.note = { kind: "info", text: `⏳ Found ${run.audioTotal} audio file(s) on Drive, downloading…` };
  } else if (done && run.audioTotal) {
    run.audioDone += 1;
    const name = basename(done[1].trim()) || "(failed file)";
    if (run.step !== null) run.details[run.step] = `${run.audioDone}/${run.audioTotal} files`;
    run.note = { kind: "info", text: `⏳ Downloading audio files… ${run.audioDone}/${run.audioTotal} · ${name}` };
  }

  // Unused audio cleanup (Step 6)
  if (stripped.startsWith("🗑 Deleted: ")) {
    run.deleted.push(stripped.slice("🗑 Deleted: ".length));
  } else if (stripped.startsWith("🔤 Standard spelling: ")) {
    run.standardized.push(stripped.slice("🔤 Standard spelling: ".length).split(" (")[0]);
  } else if (stripped.startsWith("🔍 Look-alike: ")) {
    // Drive name ≈ sheet name: kept as is, never renamed automatically
    run.lookalike.push(stripped.slice("🔍 Look-alike: ".length).split(" (")[0]);
  } else if (stripped.startsWith("✔ Audio cleanup completed")) {
    run.unusedChecked = true;
    const parts: string[] = [];
    if (run.deleted.length) parts.push(`${run.deleted.length} removed`);
    if (run.lookalike.length) parts.push(`${run.lookalike.length} look-alike name(s) to check`);
    if (run.step !== null) run.details[run.step] = parts.join(", ") || "none unused";
  } else if (stripped.startsWith("✅ All audio files are available")) {
    run.missingChecked = true;
    if (run.step !== null) run.details[run.step] = "none missing";
  }

  // Missing audios (reported, not fatal)
  if (stripped.startsWith(MISSING_HEADER)) {
    run.inMissingList = true;
    run.missingChecked = true;
  } else if (run.inMissingList && stripped.startsWith("- ")) {
    run.missing.push(stripped.slice(2));
    if (run.step !== null) run.details[run.step] = `${run.missing.length} missing`;
  } else if (stripped.startsWith("❌")) {
    run.inMissingList = false;
    run.errors.push(stripped);
  }

  if (stripped.startsWith(DONE_MARKER)) {
    run.note = { kind: "success", text: "✅ All steps completed." };
  }
}

/** Sign-in didn't succeed: the pipeline never started, so nothing was created or deleted. */
export function stopBeforeRun(run: Run, outcome: "cancelled" | "error", reason: string) {
  run.showSigninButton = false;
  if (outcome === "cancelled") {
    run.state = "cancelled";
    const text = `⏹️ Authentication cancelled: ${reason}. Nothing was created or deleted.`;
    run.auth = { kind: "warning", text };
    run.log.push(text);
    run.title = "Cancelled";
  } else {
    run.state = "error";
    const text = `❌ Authentication failed: ${reason}. Nothing was created or deleted.`;
    run.auth = { kind: "error", text };
    run.errors.push(text);
    run.log.push(text);
    run.title = "Authentication failed";
  }
}

function tail(run: Run) {
  return run.log.slice(-15).join("\n");
}

/** The pipeline ended (returncode) or was cancelled (cancelReason). Sets the final state, as app.py did. */
export function finishPipeline(run: Run, returncode: number | null, cancelReason?: string) {
  if (cancelReason) {
    run.state = "cancelled";
    const touched = run.step !== null && run.step >= WIPE_STEP;
    const detail = touched
      ? `lang/${run.lang} may be incomplete, so generate it again.`
      : "Nothing was created or deleted.";
    run.log.push(`⏹️ Run cancelled: ${cancelReason}. ${detail}`);
    if (run.authenticated) run.note = { kind: "warning", text: `⏹️ Run cancelled: ${cancelReason}. ${detail}` };
    else run.auth = { kind: "warning", text: `⏹️ Authentication cancelled: ${cancelReason}. ${detail}` };
    run.finalSteps = "error";
    run.title = "Cancelled";
  } else if (!run.authenticated) {
    // The pipeline refused this sign-in: it stopped before Step 1
    run.state = "error";
    run.auth = { kind: "error", text: "❌ Authentication failed. Nothing was created or deleted." };
    if (!run.errors.length) run.errors.push(tail(run));
    run.title = "Authentication failed";
  } else if (returncode !== 0) {
    run.state = "error";
    if (!run.errors.length) run.errors.push(tail(run)); // uncaught exception: show the traceback tail
    run.note = { kind: "error", text: `❌ The pipeline stopped with an error (exit code ${returncode}).` };
    run.finalSteps = "error";
    run.title = "Failed";
  } else if (run.errors.length) {
    run.state = "warning";
    run.note = { kind: "warning", text: "⚠️ The pipeline finished, but some steps reported errors. See above." };
    run.finalSteps = "complete";
    run.title = "Finished with errors";
  } else {
    run.state = "complete";
    run.finalSteps = "complete";
    run.title = "Completed";
  }
}

/** Title after the AI check, by the run's final state */
export function finalTitle(run: Run) {
  return { complete: "Completed", warning: "Finished with errors", cancelled: "Cancelled" }[run.state as string] ??
    (run.authenticated ? "Failed" : "Authentication failed");
}

/** The step list as [icon, text] pairs; empty until signed in */
export function stepLines(run: Run): string[] {
  if (!run.authenticated) return [];
  const lines: string[] = [];
  STEPS.forEach(([, label, optional], i) => {
    if (optional && !run.reached.includes(i)) return;
    const detail = i in run.details ? ` · ${run.details[i]}` : "";
    let icon: string;
    if ((run.step !== null && i < run.step) || (i === run.step && run.finalSteps === "complete")) icon = "✅";
    else if (i === run.step) icon = run.finalSteps === "error" ? "❌" : "⏳";
    else icon = "⬜";
    lines.push(`${icon} ${label}${detail}`);
  });
  return lines;
}
