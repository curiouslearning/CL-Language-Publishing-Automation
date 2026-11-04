// The "AI language check" report (spec 003, contracts/ai-check-cli-and-ui.md) and token usage (spec 006).
// Advisory: warnings, never errors.
import type { AiReport, AiWarning } from "../types";
import { Alert, Caption, CodeLog, DownloadButton, Expander, Inline, saveFile } from "./ui";

const CATEGORY_LABELS: Record<string, string> = {
  misspelled_word: "Misspelled word",
  foreign_letter: "Letter not used in this language",
  bad_sentence: "Feedback sentence",
  recording_mismatch: "Recording name",
  letters_dont_spell_word: "Letters don't spell the word",
  letter_not_in_word: "Letter not in the word",
};
const BADGES: Record<string, string> = { high: "🔴 high", medium: "🟠 medium", low: "🟡 low" };

function Warning({ w }: { w: AiWarning }) {
  const locations = w.locations ?? [];
  const where = locations.slice(0, 8).join(", ") + (locations.length > 8 ? ` and ${locations.length - 8} more` : "");
  return (
    <div className="md ai-warning">
      {BADGES[w.confidence ?? ""] ?? w.confidence} · <strong>{CATEGORY_LABELS[w.category ?? ""] ?? w.category}</strong> ·{" "}
      <code>{String(w.text)}</code>
      {w.suggestion ? (
        <>
          {" "}→ <code>{w.suggestion}</code>
        </>
      ) : null}
      <br />
      {w.reason ?? ""}
      <br />
      <em>Where:</em> {where}
    </div>
  );
}

function Usage({ ai }: { ai: AiReport }) {
  const model = ai.model || "?";
  const usage = ai.usage;
  if (!usage) {
    if (ai.status !== "unavailable" || ai.model) {
      const note = ai.cached
        ? "earlier check, token counts weren't recorded then"
        : ai.status === "unavailable"
          ? "no tokens used"
          : "not reported by the API";
      return (
        <p className="md">
          <strong>Model:</strong> <code>{model}</code> · <strong>Tokens:</strong> {note}
        </p>
      );
    }
    return null;
  }
  const inp = usage.input_tokens ?? 0;
  const out = usage.output_tokens ?? 0;
  const fmt = (n: number) => n.toLocaleString("en-US");
  return (
    <>
      <p className="md">
        <strong>Model:</strong> <code>{model}</code> · <strong>Input tokens:</strong> {fmt(inp)} · <strong>Output tokens:</strong>{" "}
        {fmt(out)}
        {usage.thinking_tokens ? ` (incl. ${fmt(usage.thinking_tokens)} thinking)` : ""} · <strong>Total:</strong> {fmt(inp + out)}
      </p>
      {ai.cached && <Caption>These are the counts of the earlier request. This run reused its result and used 0 tokens.</Caption>}
    </>
  );
}

export function AiSection({ ai, lang, showTokens }: { ai: AiReport; lang: string; showTokens: boolean }) {
  const provider = ai.provider || "AI";
  const language = ai.assumed_language ? `, language: ${ai.assumed_language}` : "";
  const found = ai.warnings ?? [];
  const fromAi = found.filter((w) => w.source === "ai");
  const consistency = found.filter((w) => w.source === "consistency");
  return (
    <>
      <h4>
        🤖 AI language check ({provider}
        {language})
      </h4>
      {showTokens && <Usage ai={ai} />}
      {ai.cached && <Caption>From earlier check on {ai.checked_at}: content unchanged, so no new AI request was made.</Caption>}
      {ai.status === "unavailable" ? (
        <Alert kind="warning">AI check unavailable: {ai.reason}</Alert>
      ) : ai.status === "cannot_judge" ? (
        <Alert kind="info">
          {provider} could not reliably review {lang}: {ai.reason}
        </Alert>
      ) : !fromAi.length ? (
        <Alert kind="success">{consistency.length ? "No language issues found by the AI" : "No issues found"}</Alert>
      ) : (
        <p className="md">
          <Inline text={`**${fromAi.length} possible issue(s)** (highest confidence first)`} />
        </p>
      )}
      {fromAi.map((w, i) => (
        <Warning key={`ai${i}`} w={w} />
      ))}
      {consistency.length > 0 && (
        <>
          <p className="md">
            <strong>Consistency check (letters vs words):</strong> {consistency.length} issue(s)
          </p>
          {consistency.map((w, i) => (
            <Warning key={`c${i}`} w={w} />
          ))}
        </>
      )}
    </>
  );
}

export function AiLog({ lines, fileName }: { lines: string[]; fileName: string }) {
  if (!lines.length) return null;
  return (
    <>
      <Expander title="🤖 AI check log">
        <CodeLog lines={lines} />
      </Expander>
      <DownloadButton label="Download AI log" onClick={() => saveFile(lines.join("\n"), fileName)} />
    </>
  );
}
