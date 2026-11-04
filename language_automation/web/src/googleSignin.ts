// Google sign-in in a popup (spec 012, research R4): Google Identity Services' token model.
// The access token stays in this tab's memory only; the server checks it again for every run.
import type { SignIn } from "./types";

const GIS_SRC = "https://accounts.google.com/gsi/client";
export const SCOPES = [
  "openid",
  "email",
  "https://www.googleapis.com/auth/drive",
  "https://www.googleapis.com/auth/spreadsheets.readonly",
].join(" ");
export const SIGNIN_TIMEOUT_SECONDS = 180;
/** Ask again when less than this is left: a run must not outlive its token */
const MIN_TOKEN_LEFT_MS = 10 * 60 * 1000;

export class SignInError extends Error {
  constructor(public kind: "cancelled" | "blocked" | "failed", message: string) {
    super(message);
  }
}

interface TokenResponse {
  access_token?: string;
  expires_in?: number | string;
  scope?: string;
  error?: string;
  error_description?: string;
}
interface TokenClient {
  requestAccessToken(overrides?: { prompt?: string; login_hint?: string }): void;
}
declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2: {
          initTokenClient(config: {
            client_id: string;
            scope: string;
            hd?: string;
            prompt?: string;
            include_granted_scopes?: boolean;
            login_hint?: string;
            callback: (r: TokenResponse) => void;
            error_callback?: (e: { type: string; message?: string }) => void;
          }): TokenClient;
          hasGrantedAllScopes(r: TokenResponse, ...scopes: string[]): boolean;
        };
      };
    };
  }
}

let loading: Promise<void> | null = null;

/** Loads Google's script once (called when the page opens, so the popup can open on the first click). */
export function loadGoogle(): Promise<void> {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = GIS_SRC;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => {
        loading = null;
        reject(new SignInError("failed", "Google's sign-in script couldn't be loaded"));
      };
      document.head.appendChild(s);
    });
  }
  return loading;
}

export function stillValid(signin: SignIn | null): signin is SignIn {
  return !!signin && signin.expiresAt - Date.now() > MIN_TOKEN_LEFT_MS;
}

/**
 * Opens Google's popup with the account chooser, so any signed-in Google account can be picked
 * (no hd / login_hint: those make Google skip the chooser and use the default account).
 * Must be called from a click. Resolves with the token, or rejects with a
 * SignInError (popup closed, blocked, scopes not allowed, or not finished within 3 minutes).
 */
export function requestToken(clientId: string): Promise<SignIn> {
  const google = window.google;
  if (!google?.accounts?.oauth2) {
    return Promise.reject(new SignInError("failed", "Google's sign-in script isn't loaded yet. Please try again"));
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = window.setTimeout(
      () => finish(() => reject(new SignInError("cancelled", "Google sign-in wasn't completed"))),
      SIGNIN_TIMEOUT_SECONDS * 1000,
    );
    function finish(f: () => void) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      f();
    }
    const client = google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPES,
      include_granted_scopes: false,
      callback: (r) => {
        if (r.error || !r.access_token) {
          finish(() => reject(new SignInError("cancelled", r.error_description || "Google sign-in wasn't completed")));
          return;
        }
        const scopes = SCOPES.split(" ").filter((s) => s.startsWith("https://"));
        if (!google.accounts.oauth2.hasGrantedAllScopes(r, scopes[0], scopes[1])) {
          finish(() =>
            reject(new SignInError("failed", "Google Drive and Sheets access weren't both allowed. Please sign in again and allow them")),
          );
          return;
        }
        const seconds = Number(r.expires_in) || 3599;
        finish(() => resolve({ token: r.access_token!, expiresAt: Date.now() + seconds * 1000 }));
      },
      error_callback: (e) => {
        if (e.type === "popup_failed_to_open") {
          finish(() =>
            reject(new SignInError("blocked", "the browser blocked Google's sign-in popup. Allow popups for this site and press Generate again")),
          );
        } else {
          finish(() => reject(new SignInError("cancelled", "Google sign-in wasn't completed")));
        }
      },
    });
    client.requestAccessToken({ prompt: "select_account" }); // always show the account chooser
  });
}
