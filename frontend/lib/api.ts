export type IntakeSummary = {
  firstName: string;
  lastName: string;
  dob: string;
  phone: string;
  email: string;
  reason: string;
};

export type AppointmentSlot = {
  id: string;
  doctorName: string;
  specialty: string;
  bodyPart: string;
  date: string;
  time: string;
  weekday: string;
};

export type SchedulingResponse = {
  summary: IntakeSummary;
  slots: AppointmentSlot[];
};

export async function submitSchedulingRequest(
  payload: IntakeSummary
): Promise<SchedulingResponse> {
  const response = await fetch("/api/schedule", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error("Failed to submit scheduling request");
  }

  return response.json();
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// --- Resilient fetch -------------------------------------------------------
// The backend on Fly.io stops when idle, so the first request after a quiet
// period can take several seconds or briefly fail while the machine boots.

export const REQUEST_TIMEOUT_MS = 15_000;
export const MAX_RETRIES = 3;
export const BACKOFF_BASE_MS = 500; // 500ms, 1s, 2s
export const SLOW_NOTICE_MS = 2_000;
const RETRYABLE_STATUSES = new Set([502, 503]);

export type ApiErrorKind = "network" | "timeout" | "http";

export class ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  detail?: unknown;

  constructor(kind: ApiErrorKind, message: string, status?: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

export class SessionExpiredError extends Error {
  constructor() {
    super("session_expired");
    this.name = "SessionExpiredError";
  }
}

export type RequestOptions = {
  /** Called once if the request (including retries) is still running after 2 s. */
  onSlow?: () => void;
  /** Overrides, mainly for tests and for non-idempotent calls. */
  retries?: number;
  timeoutMs?: number;
  backoffBaseMs?: number;
  slowAfterMs?: number;
};

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * fetch with a per-attempt timeout and exponential-backoff retries.
 * Retries on network errors and on 502/503 only. A timed-out attempt is retried
 * only for GET/HEAD: the server may already have processed a timed-out POST, so
 * replaying it could duplicate a chat turn.
 */
export async function apiFetch(
  url: string,
  init: RequestInit = {},
  options: RequestOptions = {}
): Promise<Response> {
  const retries = options.retries ?? MAX_RETRIES;
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const backoffBase = options.backoffBaseMs ?? BACKOFF_BASE_MS;
  const method = (init.method || "GET").toUpperCase();
  const safeToRetryTimeout = method === "GET" || method === "HEAD";

  const slowTimer = options.onSlow
    ? setTimeout(options.onSlow, options.slowAfterMs ?? SLOW_NOTICE_MS)
    : null;

  try {
    for (let attempt = 0; ; attempt++) {
      const controller = new AbortController();
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);

      try {
        const response = await fetch(url, { ...init, signal: controller.signal });
        if (RETRYABLE_STATUSES.has(response.status) && attempt < retries) {
          await sleep(backoffBase * 2 ** attempt);
          continue;
        }
        return response;
      } catch (err) {
        const kind: ApiErrorKind = timedOut ? "timeout" : "network";
        const canRetry = attempt < retries && (kind === "network" || safeToRetryTimeout);
        if (!canRetry) {
          throw new ApiError(
            kind,
            kind === "timeout" ? "Request timed out" : "Network error",
            undefined,
            err
          );
        }
        await sleep(backoffBase * 2 ** attempt);
      } finally {
        clearTimeout(timer);
      }
    }
  } finally {
    if (slowTimer) clearTimeout(slowTimer);
  }
}

/** Turn any thrown value into a message that is safe to show a patient. */
export function getFriendlyErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === "network" || error.kind === "timeout") {
      return "I'm having trouble reaching the assistant right now. Please check your connection and try again in a moment.";
    }
    const status = error.status ?? 0;
    if (status === 502 || status === 503 || status === 504) {
      return "The assistant is still starting up. Please try again in a few seconds.";
    }
    if (status === 429) {
      return "You're sending messages a little fast. Please wait a moment and try again.";
    }
    if (status === 404 && error.message === "Session not found") {
      return "That session is no longer active. Please start a new chat.";
    }
    // Backend 4xx details are written for patients (e.g. "I need your phone number...").
    if (status >= 400 && status < 500 && typeof error.detail === "string" && error.detail) {
      return error.detail;
    }
  }
  return "Something went wrong on our side. Please try again.";
}

async function parseOrThrow<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => null);

  if (response.status === 404 && data?.error === "session_expired") {
    throw new SessionExpiredError();
  }

  if (!response.ok) {
    const detail = data?.detail ?? data?.error;
    throw new ApiError(
      "http",
      typeof detail === "string" ? detail : `HTTP ${response.status}`,
      response.status,
      detail
    );
  }

  return data as T;
}

const jsonPost = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Fire-and-forget wake-up for the Fly machine. Never throws. */
export async function warmUpBackend(options: RequestOptions = {}): Promise<void> {
  try {
    await apiFetch(`${API_BASE_URL}/api/v1/health`, { method: "GET" }, options);
  } catch {
    // The first real request will surface any problem.
  }
}

export type ChatRequest = {
  message: string;
  session_id?: string | null;
  phone_number?: string | null;
};

export type ChatResponse = {
  session_id: string;
  workflow_type?: string;
  state?: string;
  message: string;
  next_step?: string;
  metadata?: {
    provider_name?: string;
    specialty?: string;
    body_part?: string;
    booked_slot?: {
      date: string;
      time: string;
    };
    booking_confirmed?: boolean;
    slots?: Array<{ date: string; time: string }>;
  };
  quick_replies?: Array<{ id: string; label: string; value: string }>;
};

export async function sendChatMessage(
  payload: ChatRequest,
  options: RequestOptions = {}
): Promise<ChatResponse> {
  const response = await apiFetch(`${API_BASE_URL}/api/v1/chat`, jsonPost(payload), options);
  return parseOrThrow<ChatResponse>(response);
}

export type VoiceHandoffResponse = {
  success: boolean;
  call_id?: string | null;
  message: string;
};

export async function startVoiceHandoff(
  sessionId: string,
  options: RequestOptions = {}
): Promise<VoiceHandoffResponse> {
  // retries: 0 by default so a flaky 502 can never place a second phone call.
  const response = await apiFetch(
    `${API_BASE_URL}/api/v1/voice/handoff`,
    jsonPost({ session_id: sessionId }),
    { retries: 0, ...options }
  );
  return parseOrThrow<VoiceHandoffResponse>(response);
}

export async function sendBookingConfirmationEmail(
  sessionId: string,
  options: RequestOptions = {}
) {
  // Safe to retry: the backend sends at most one email per session.
  const response = await apiFetch(
    `${API_BASE_URL}/api/v1/send-confirmation-email`,
    jsonPost({ session_id: sessionId }),
    options
  );
  return parseOrThrow<{ success: boolean; message: string }>(response);
}
