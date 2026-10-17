/**
 * Single fetch wrapper for the whole app.
 *
 * - attaches the bearer token
 * - refreshes once on 401, then retries the original request
 * - unwraps the backend's `{ error: { code, message, details } }` envelope
 */
const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
export const API_BASE = RAW_BASE.replace(/\/$/, "");

const ACCESS_KEY = "campushub.access";
const REFRESH_KEY = "campushub.refresh";

/**
 * Where the sign-in lives.
 *
 * Each tab keeps its own in sessionStorage, so a student signed in in one tab
 * and a coordinator in another stay who they are when either is refreshed.
 * localStorage, which every tab shares, used to be the only copy, so the last
 * person to sign in anywhere took over every tab on its next reload.
 *
 * localStorage still holds the most recent sign-in, but only to start a *new*
 * tab (a link opened in a new tab, a reopened browser) already signed in. A tab
 * reads it once, when it has nothing of its own, and from then on keeps its own.
 */
const SIGNED_OUT_KEY = "campushub.signed_out";

function read(store: Storage, key: string): string | null {
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function write(store: Storage, key: string, value: string | null) {
  try {
    if (value === null) store.removeItem(key);
    else store.setItem(key, value);
  } catch {
    // Storage blocked (private mode, quota): the sign-in lasts for this page only.
  }
}

/** Adopt the most recent sign-in if this tab has none of its own yet. */
function ensureTabCopy() {
  // A tab that signed itself out stays signed out, even on reload.
  if (read(sessionStorage, ACCESS_KEY) || read(sessionStorage, SIGNED_OUT_KEY)) return;
  const access = read(localStorage, ACCESS_KEY);
  if (!access) return;
  write(sessionStorage, ACCESS_KEY, access);
  write(sessionStorage, REFRESH_KEY, read(localStorage, REFRESH_KEY));
}

export const tokenStore = {
  access: () => {
    ensureTabCopy();
    return read(sessionStorage, ACCESS_KEY);
  },
  refresh: () => {
    ensureTabCopy();
    return read(sessionStorage, REFRESH_KEY);
  },
  /** A new sign-in: this tab's, and the one new tabs start with. */
  set(access: string, refresh: string) {
    write(sessionStorage, SIGNED_OUT_KEY, null);
    write(sessionStorage, ACCESS_KEY, access);
    write(sessionStorage, REFRESH_KEY, refresh);
    write(localStorage, ACCESS_KEY, access);
    write(localStorage, REFRESH_KEY, refresh);
  },
  /** Fresh tokens for whoever this tab is signed in as. The shared copy is
   *  updated only if it is still this same sign-in; otherwise refreshing the
   *  student's tab would make new tabs open as the student again. */
  rotate(access: string, refresh: string) {
    const shared = read(localStorage, REFRESH_KEY) === read(sessionStorage, REFRESH_KEY);
    write(sessionStorage, ACCESS_KEY, access);
    write(sessionStorage, REFRESH_KEY, refresh);
    if (shared) {
      write(localStorage, ACCESS_KEY, access);
      write(localStorage, REFRESH_KEY, refresh);
    }
  },
  /** Sign this tab out. The shared copy goes too only if it is this tab's, so
   *  signing the student out does not sign the coordinator's tab out. */
  clear() {
    if (read(localStorage, REFRESH_KEY) === read(sessionStorage, REFRESH_KEY)) {
      write(localStorage, ACCESS_KEY, null);
      write(localStorage, REFRESH_KEY, null);
    }
    write(sessionStorage, ACCESS_KEY, null);
    write(sessionStorage, REFRESH_KEY, null);
    write(sessionStorage, SIGNED_OUT_KEY, "1");
  },
};

export type FieldError = { field: string; message: string };

export class ApiError extends Error {
  status: number;
  code: string;
  fields: FieldError[];

  constructor(status: number, code: string, message: string, fields: FieldError[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }

  /** Message for a specific form field, if the backend flagged one. */
  fieldError(name: string): string | undefined {
    return this.fields.find((f) => f.field === name)?.message;
  }
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; raw?: boolean };

let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refresh = tokenStore.refresh();
  if (!refresh) return false;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!response.ok) return false;
        const data = await response.json();
        tokenStore.rotate(data.access_token, data.refresh_token ?? refresh);
        return true;
      } catch {
        return false;
      } finally {
        // Allow a later 401 to trigger a fresh attempt.
        setTimeout(() => (refreshInFlight = null), 0);
      }
    })();
  }
  return refreshInFlight;
}

async function toError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed (${response.status})`;
  let fields: FieldError[] = [];
  try {
    const body = await response.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      if (Array.isArray(body.error.details)) fields = body.error.details;
    }
  } catch {
    /* non-JSON error body — keep the generic message */
  }
  if (response.status === 500) {
    message = "Something went wrong on the server. Please try again.";
  }
  return new ApiError(response.status, code, message, fields);
}

async function send<T>(path: string, options: Options, retry = true): Promise<T> {
  const { body, raw, headers, ...rest } = options;
  const isFormData = body instanceof FormData;

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...(tokenStore.access() ? { Authorization: `Bearer ${tokenStore.access()}` } : {}),
      ...headers,
    },
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  // A 401 on anything other than signing in means the session is over. Every
  // unrecoverable case must end the session — including having no refresh token
  // at all, which previously fell straight through and left the user looking at
  // a fully rendered shell with "credentials were not provided" in the middle.
  const isAuthAttempt = path.startsWith("/auth/login") || path.startsWith("/auth/refresh");
  if (response.status === 401 && retry && !isAuthAttempt) {
    if (tokenStore.refresh() && await refreshAccessToken()) {
      return send<T>(path, options, false);
    }
    tokenStore.clear();
    window.dispatchEvent(new CustomEvent("campushub:signed-out"));
  }

  if (!response.ok) throw await toError(response);
  if (raw) return response as unknown as T;
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string) => send<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) => send<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => send<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body?: unknown) => send<T>(path, { method: "PUT", body }),
  delete: <T>(path: string, body?: unknown) => send<T>(path, { method: "DELETE", body }),
  upload: <T>(path: string, form: FormData) => send<T>(path, { method: "POST", body: form }),
};

/** Build a query string, dropping empty values. */
export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}


/**
 * Open a file that lives behind an authenticated endpoint.
 *
 * `file_url` is always an API route (`/files/{id}/download`), never a storage
 * path, so it carries no public access of its own — the bearer token has to be
 * attached. The response is turned into a short-lived object URL; the browser
 * renders the PDF and the URL is revoked once it has loaded.
 */
export async function openProtectedFile(path: string): Promise<void> {
  const response = await send<Response>(path.replace(API_BASE, ""), { method: "GET", raw: true });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const opened = window.open(url, "_blank", "noopener");
  if (!opened) {
    // Pop-up blocked — fall back to a same-tab navigation.
    window.location.href = url;
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function downloadProtectedFile(path: string, defaultFilename?: string): Promise<void> {
  const response = await send<Response>(path.replace(API_BASE, ""), { method: "GET", raw: true });
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  let filename = defaultFilename ?? "download.csv";
  if (disposition && disposition.includes("filename=")) {
    const match = disposition.match(/filename="?([^";]+)"?/);
    if (match?.[1]) filename = match[1];
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export const chatbotApi = {
  getConfig: () => api.get<import("@/types").ChatInitialConfigResponse>("/chatbot/config"),
  sendQuery: (query: string, history: import("@/types").ChatMessageItem[] = []) =>
    api.post<import("@/types").ChatQueryResponse>("/chatbot/query", { query, history }),
};
