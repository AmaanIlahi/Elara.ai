const SESSION_ID_KEY = "elara_session_id";
const CHAT_MESSAGES_KEY = "elara_chat_messages";
const CHAT_META_KEY = "elara_chat_meta";

export function getStoredSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(SESSION_ID_KEY);
}

export function setStoredSessionId(sessionId: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(SESSION_ID_KEY, sessionId);
}

export function clearStoredSessionId() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SESSION_ID_KEY);
}

export function getStoredMessages<T>(): T[] | null {
  if (typeof window === "undefined") return null;

  const raw = localStorage.getItem(CHAT_MESSAGES_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as T[];
  } catch {
    return null;
  }
}

export function setStoredMessages<T>(messages: T[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(CHAT_MESSAGES_KEY, JSON.stringify(messages));
}

export function clearStoredMessages() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(CHAT_MESSAGES_KEY);
}

export function getStoredChatMeta<T>(): T | null {
  if (typeof window === "undefined") return null;

  const raw = localStorage.getItem(CHAT_META_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function setStoredChatMeta<T>(meta: T) {
  if (typeof window === "undefined") return;
  localStorage.setItem(CHAT_META_KEY, JSON.stringify(meta));
}

export function clearStoredChatMeta() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(CHAT_META_KEY);
}

export function clearStoredChatState() {
  clearStoredSessionId();
  clearStoredMessages();
  clearStoredChatMeta();
}