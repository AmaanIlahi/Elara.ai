const SESSION_ID_KEY = "elara_session_id";
const CHAT_MESSAGES_KEY = "elara_chat_messages";
const CHAT_META_KEY = "elara_chat_meta";

// Chat state lives in sessionStorage: a refresh resumes the conversation, while a
// new tab or a new visit starts fresh. Earlier versions used localStorage, so
// drop any leftovers once per page load.
export function clearLegacyLocalStorage() {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(SESSION_ID_KEY);
    localStorage.removeItem(CHAT_MESSAGES_KEY);
    localStorage.removeItem(CHAT_META_KEY);
  } catch {
    // storage may be unavailable (private mode); nothing to clean up then
  }
}

export function getStoredSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(SESSION_ID_KEY);
}

export function setStoredSessionId(sessionId: string) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(SESSION_ID_KEY, sessionId);
}

export function clearStoredSessionId() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(SESSION_ID_KEY);
}

export function getStoredMessages<T>(): T[] | null {
  if (typeof window === "undefined") return null;

  const raw = sessionStorage.getItem(CHAT_MESSAGES_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as T[];
  } catch {
    return null;
  }
}

export function setStoredMessages<T>(messages: T[]) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(CHAT_MESSAGES_KEY, JSON.stringify(messages));
}

export function clearStoredMessages() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(CHAT_MESSAGES_KEY);
}

export function getStoredChatMeta<T>(): T | null {
  if (typeof window === "undefined") return null;

  const raw = sessionStorage.getItem(CHAT_META_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function setStoredChatMeta<T>(meta: T) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(CHAT_META_KEY, JSON.stringify(meta));
}

export function clearStoredChatMeta() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(CHAT_META_KEY);
}

export function clearStoredChatState() {
  clearStoredSessionId();
  clearStoredMessages();
  clearStoredChatMeta();
}