// Calls to ../server.py (contracts/http-api.md). Every request is short, except a run, which lasts
// exactly as long as the run. Nothing stays open while the page is idle (spec 012, FR-001).
import type { AiReport, ServerConfig } from "./types";

export type RunEvent =
  | { type: "busy"; reason: string }
  | { type: "auth"; status: "ok" | "refused" | "failed"; email?: string; reason?: string }
  | { type: "line"; text: string }
  | { type: "pipeline_end"; returncode: number }
  | { type: "ai_start" }
  | { type: "ai_line"; text: string }
  | { type: "ai_report"; report: AiReport }
  | { type: "ping" }
  | { type: "end"; package_id?: string | null; mp3_count?: number | null };

export class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
  } catch {
    /* not JSON */
  }
  return `the server answered ${res.status} ${res.statusText}`.trim();
}

export async function getConfig(): Promise<ServerConfig> {
  const res = await fetch("/api/config", { cache: "no-store" });
  if (!res.ok) throw new HttpError(res.status, await detail(res));
  return res.json();
}

export async function getExisting(langs: string[]): Promise<Record<string, number>> {
  const res = await fetch("/api/existing", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ langs }),
  });
  if (!res.ok) return {};
  return (await res.json()).existing ?? {};
}

/** Start a run and call onEvent for each streamed event. Resolves when the stream ends. */
export async function streamRun(
  lang: string,
  aiCheck: boolean,
  token: string,
  signal: AbortSignal,
  onEvent: (e: RunEvent) => void,
): Promise<void> {
  const res = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ lang, ai_check: aiCheck }),
    signal,
  });
  if (!res.ok || !res.body) throw new HttpError(res.status, await detail(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const raw = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (raw) onEvent(JSON.parse(raw) as RunEvent);
    }
  }
  const rest = (buffer + decoder.decode()).trim();
  if (rest) onEvent(JSON.parse(rest) as RunEvent);
}

export async function fetchPackage(packageId: string): Promise<Blob> {
  const res = await fetch(`/api/packages/${encodeURIComponent(packageId)}`, { cache: "no-store" });
  if (!res.ok) throw new HttpError(res.status, await detail(res));
  return res.blob();
}
