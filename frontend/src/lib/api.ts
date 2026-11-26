export type Conflict = { id: string; title: string; start_at: string; end_at: string };

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string[] | string>;
  conflicts: Conflict[];

  constructor(message: string, status: number, code = "error", fields = {}, conflicts: Conflict[] = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.conflicts = conflicts;
  }

  get offline() {
    return this.status === 0;
  }
}

function cookie(name: string) {
  return document.cookie.split("; ").find((row) => row.startsWith(`${name}=`))?.split("=")[1] ?? "";
}

function firstMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  const error = record.error as { message?: string } | undefined;
  if (error?.message) return error.message;
  for (const value of Object.values(record)) {
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
    if (typeof value === "string") return value;
  }
  return null;
}

/** Same-origin JSON client with session cookies and CSRF. */
export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      credentials: "same-origin",
      ...rest,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": decodeURIComponent(cookie("csrftoken")),
        ...rest.headers,
      },
    });
  } catch {
    throw new ApiError("You appear to be offline. Changes need a connection.", 0, "offline");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = payload?.error ?? {};
    throw new ApiError(
      firstMessage(payload) ?? `Request failed (${response.status})`,
      response.status,
      error.code ?? (response.status === 409 ? "conflict" : "error"),
      error.fields ?? (payload && typeof payload === "object" && !payload.error ? payload : {}),
      error.conflicts ?? [],
    );
  }
  if (response.status === 204) return undefined as T;
  // DRF renders Response(None) as an empty body; treat it as JSON null.
  const text = await response.text();
  return (text ? JSON.parse(text) : null) as T;
}

/**
 * POST JSON. Pass `idempotencyKey` (one per user action, reused only when
 * retrying that same action) and the server replays its first answer
 * instead of creating a second record; see backend/api/idempotency.py.
 */
export function post<T>(path: string, json: unknown = {}, options: { idempotencyKey?: string } = {}) {
  const headers = options.idempotencyKey ? { "Idempotency-Key": options.idempotencyKey } : undefined;
  return api<T>(path, { method: "POST", json, headers });
}

export function patch<T>(path: string, json: unknown) {
  return api<T>(path, { method: "PATCH", json });
}

export function newId() {
  return crypto.randomUUID();
}
