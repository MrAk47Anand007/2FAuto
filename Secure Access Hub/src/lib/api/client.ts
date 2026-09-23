/**
 * Centralized, typed fetch client for the 2FAuto FastAPI backend.
 *
 * Rules enforced here:
 * - relative URLs only (same-origin through the dev proxy / prod gateway)
 * - credentials: "include" so the HttpOnly otp_session cookie travels
 * - X-CSRF-Token on every mutation (token comes from GET /api/v1/me)
 * - responses are NOT assumed to be JSON (HTML 401s, 303 redirects exist)
 */

export type ApiErrorKind =
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "gone"
  | "validation"
  | "step_up_required"
  | "throttled"
  | "server"
  | "network"
  | "unknown";

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  readonly fieldErrors: FieldError[];
  readonly retryAfterSeconds: number | null;

  constructor(init: {
    status: number;
    kind: ApiErrorKind;
    message: string;
    fieldErrors?: FieldError[];
    retryAfterSeconds?: number | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.kind = init.kind;
    this.fieldErrors = init.fieldErrors ?? [];
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }
}

function kindFor(status: number): ApiErrorKind {
  switch (status) {
    case 401:
      return "unauthenticated";
    case 403:
      return "forbidden";
    case 404:
      return "not_found";
    case 409:
      return "conflict";
    case 410:
      return "gone";
    case 422:
      return "validation";
    case 428:
      return "step_up_required";
    case 429:
      return "throttled";
    default:
      if (status === 503 || status === 504) return "network";
      return status >= 500 ? "server" : "unknown";
  }
}

const DEFAULT_MESSAGES: Record<ApiErrorKind, string> = {
  unauthenticated: "Your session is no longer valid. Sign in again.",
  forbidden: "Access denied. Your account may lack permission for this action.",
  not_found: "That item is unavailable or you cannot access it.",
  conflict: "That name is already in use.",
  gone: "This endpoint has been retired.",
  validation: "Check the highlighted fields and try again.",
  step_up_required: "Confirm your password to continue.",
  throttled: "Too many attempts. Wait a moment and try again.",
  server: "The server could not complete the request. Try again shortly.",
  network: "Could not reach the server. Check your connection and retry.",
  unknown: "Something went wrong. Try again.",
};

/** Session-derived CSRF token, held in memory only. Never persisted. */
let csrfToken: string | null = null;
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}
export function getCsrfToken(): string | null {
  return csrfToken;
}

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler;
}

interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  /** JSON body. */
  json?: unknown;
  /** URL-encoded body for the existing form endpoints. */
  form?: Record<string, string | number | undefined>;
  signal?: AbortSignal | undefined;
  /** Suppress the global sign-out reaction (used by login itself). */
  ignoreUnauthorized?: boolean | undefined;
}

async function readBody(response: Response): Promise<{ text: string; json: unknown }> {
  const text = await response.text().catch(() => "");
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("json") || text.trim() === "") return { text, json: null };
  try {
    return { text, json: JSON.parse(text) as unknown };
  } catch {
    return { text, json: null };
  }
}

function normalizeError(
  status: number,
  payload: unknown,
  raw: string,
  retryAfter: string | null,
): ApiError {
  const kind = kindFor(status);
  let message = DEFAULT_MESSAGES[kind];
  const fieldErrors: FieldError[] = [];

  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const detail = record["detail"];
    if (typeof detail === "string" && detail.trim()) {
      message = detail;
    } else if (Array.isArray(detail)) {
      for (const item of detail) {
        if (!item || typeof item !== "object") continue;
        const entry = item as { loc?: unknown[]; msg?: string };
        const loc = Array.isArray(entry.loc) ? entry.loc : [];
        const field = String(loc[loc.length - 1] ?? "form");
        fieldErrors.push({ field, message: entry.msg ?? "Invalid value" });
      }
      const first = fieldErrors[0];
      if (first) message = first.message;
    } else if (typeof record["error"] === "string" && (record["error"] as string).trim()) {
      message = record["error"] as string;
    }
  } else if (raw && !raw.trimStart().startsWith("<") && raw.length < 240) {
    message = raw;
  }

  const retryAfterSeconds = retryAfter && /^\d+$/.test(retryAfter) ? Number(retryAfter) : null;
  return new ApiError({ status, kind, message, fieldErrors, retryAfterSeconds });
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", json, form, signal, ignoreUnauthorized } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;

  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(form)) {
      if (value !== undefined) params.set(key, String(value));
    }
    // Existing form handlers also accept the csrf_token field.
    if (csrfToken && !params.has("csrf_token")) params.set("csrf_token", csrfToken);
    body = params.toString();
  }

  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      ...(body === undefined ? {} : { body }),
      ...(signal ? { signal } : {}),
      credentials: "include",
      cache: "no-store",
      redirect: "follow",
      referrerPolicy: "same-origin",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({ status: 0, kind: "network", message: DEFAULT_MESSAGES.network });
  }

  // Existing admin form handlers answer 303 -> /admin (HTML). Treat as success.
  if (response.ok || response.type === "opaqueredirect") {
    const { json: parsed } = await readBody(response);
    return (parsed ?? ({} as unknown)) as T;
  }

  const { text, json: parsed } = await readBody(response);
  const error = normalizeError(response.status, parsed, text, response.headers.get("retry-after"));
  if (error.status === 401 && !ignoreUnauthorized) onUnauthorized?.();
  throw error;
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function errorMessage(error: unknown): string {
  if (isApiError(error)) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return DEFAULT_MESSAGES.unknown;
}

export function needsStepUp(error: unknown): boolean {
  return isApiError(error) && error.kind === "step_up_required";
}
