// Shapes shared by the page (spec 012, data-model.md). Everything lives in tab memory only.

export type Kind = "info" | "success" | "warning" | "error";
export type Message = { kind: Kind; text: string };
export type RunState = "running" | "complete" | "warning" | "error" | "cancelled";

export interface ServerConfig {
  hosted: boolean;
  signin: { client_id: string; hd: string } | null;
  signin_error: string | null;
  ai: { provider: string | null; model: string | null; reason: string | null };
  busy: boolean;
}

export interface AiWarning {
  source?: "ai" | "consistency";
  category?: string;
  confidence?: "high" | "medium" | "low" | string;
  text?: string;
  suggestion?: string | null;
  reason?: string;
  locations?: string[];
}

export interface AiReport {
  status?: "ok" | "unavailable" | "cannot_judge" | string;
  reason?: string;
  provider?: string;
  model?: string;
  assumed_language?: string;
  cached?: boolean;
  checked_at?: string;
  warnings?: AiWarning[];
  usage?: { input_tokens?: number; output_tokens?: number; thinking_tokens?: number } | null;
}

export type PackageInfo =
  | { status: "fetching" }
  | { status: "ready"; blob: Blob }
  | { status: "error"; error: string }
  | { status: "replaced" };

export interface Run {
  id: string;
  lang: string;
  started: string; // "YYYY-MM-DD HH:MM:SS", as on the Streamlit page
  state: RunState;
  title: string; // status title after "<lang> · "
  authenticated: boolean;
  auth: Message;
  showSigninButton: boolean;
  account?: string;
  // steps (runParser.ts)
  step: number | null;
  reached: number[];
  details: Record<number, string>;
  note: Message | null;
  finalSteps: "complete" | "error" | null;
  // results
  log: string[];
  errors: string[];
  missing: string[];
  deleted: string[];
  lookalike: string[];
  standardized: string[];
  unusedChecked: boolean;
  missingChecked: boolean;
  // parser state
  inMissingList: boolean;
  audioTotal: number | null;
  audioDone: number;
  // AI check
  aiRunning: boolean;
  ai?: AiReport;
  aiLog: string[];
  // after the run
  mp3Count?: number | null;
  pkg: PackageInfo | null;
}

export interface SignIn {
  token: string;
  email?: string;
  expiresAt: number; // ms since epoch
}
