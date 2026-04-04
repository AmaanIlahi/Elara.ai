"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChatHeader from "./ChatHeader";
import MessageList from "./MessageList";
import MessageListErrorBoundary from "./MessageListErrorBoundary";
import ChatInput from "./ChatInput";
import { Message } from "@/lib/types";
import { sendChatMessage, startVoiceHandoff, sendBookingConfirmationEmail } from "@/lib/api";
import {
  clearStoredChatState,
  getStoredChatMeta,
  getStoredMessages,
  getStoredSessionId,
  setStoredChatMeta,
  setStoredMessages,
  setStoredSessionId,
} from "@/lib/session";

// Minimum ms the typing indicator stays visible — makes fast responses feel natural
const MIN_TYPING_MS = 400;
// Words-per-second the typing indicator mimics
const WORDS_PER_SECOND = 14;
// Inactivity timeout before a session-expiry warning (10 minutes)
const TIMEOUT_MS = 10 * 60 * 1000;

function createId() {
  return Math.random().toString(36).slice(2, 9);
}

function getTimestamp() {
  const now = new Date();
  let hours = now.getHours();
  const minutes = now.getMinutes().toString().padStart(2, "0");
  const suffix = hours >= 12 ? "PM" : "AM";
  hours = hours % 12;
  if (hours === 0) hours = 12;
  return `${hours}:${minutes} ${suffix}`;
}

function typingDelay(text: string): number {
  const words = text.trim().split(/\s+/).length;
  return Math.max(MIN_TYPING_MS, (words / WORDS_PER_SECOND) * 1000);
}

function createTextMessage(
  id: string,
  sender: "user" | "assistant",
  text: string
): Message {
  return { id, sender, type: "text", text, createdAt: getTimestamp() };
}

function createTypingMessage(id: string): Message {
  return { id, sender: "assistant", type: "typing", text: "", createdAt: getTimestamp() };
}

const DEFAULT_MESSAGES: Message[] = [
  {
    id: "welcome-message",
    sender: "assistant",
    type: "text",
    text: "Hi, I'm Elara! I can help you schedule an appointment, request a prescription refill, or answer questions about our office. What can I do for you today?",
    createdAt: "Now",
    quickReplies: [
      { id: "qr-schedule", label: "Schedule an appointment", value: "I'd like to schedule an appointment" },
      { id: "qr-refill", label: "Prescription refill", value: "I need a prescription refill" },
      { id: "qr-info", label: "Office information", value: "I have a question about the office" },
    ],
  },
];

const DEFAULT_CHAT_META = { workflowType: "", state: "", nextStep: "" };

export default function ChatShell() {
  const [messages, setMessages] = useState<Message[]>(DEFAULT_MESSAGES);
  const [isTyping, setIsTyping] = useState(false);
  const [isCalling, setIsCalling] = useState(false);
  const [chatMeta, setChatMeta] = useState(DEFAULT_CHAT_META);
  const [hydrated, setHydrated] = useState(false);
  const [sessionId, setSessionIdState] = useState<string | null>(null);
  const [showTimeoutWarning, setShowTimeoutWarning] = useState(false);

  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // --- Session timeout ---
  const resetTimeout = useCallback(() => {
    setShowTimeoutWarning(false);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      setShowTimeoutWarning(true);
    }, TIMEOUT_MS);
  }, []);

  // Start timer on hydration; reset on every user interaction
  useEffect(() => {
    if (!hydrated) return;
    resetTimeout();
    return () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); };
  }, [hydrated, resetTimeout]);

  // --- Hydration ---
  useEffect(() => {
    const storedMessages = getStoredMessages<Message>();
    const storedMeta = getStoredChatMeta<typeof DEFAULT_CHAT_META>();
    const storedSessionId = getStoredSessionId();

    if (storedMessages && storedMessages.length > 0) {
      setMessages(storedMessages.filter((m) => m.type !== "typing"));
    }
    if (storedMeta) setChatMeta(storedMeta);
    if (storedSessionId) setSessionIdState(storedSessionId);
    setHydrated(true);
  }, []);

  useEffect(() => { if (hydrated) setStoredMessages(messages); }, [messages, hydrated]);
  useEffect(() => { if (hydrated) setStoredChatMeta(chatMeta); }, [chatMeta, hydrated]);

  const appendMessage = (message: Message) =>
    setMessages((prev) => [...prev, message]);

  const removeTypingMessage = () =>
    setMessages((prev) => prev.filter((m) => m.type !== "typing"));

  const clearAllQuickReplies = () =>
    setMessages((prev) =>
      prev.map((m) =>
        m.type === "text" && m.quickReplies?.length ? { ...m, quickReplies: [] } : m
      )
    );

  const handleSend = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isTyping) return;

    resetTimeout();
    clearAllQuickReplies();
    appendMessage(createTextMessage(createId(), "user", trimmed));

    setIsTyping(true);
    const typingId = createId();
    appendMessage(createTypingMessage(typingId));

    const startedAt = Date.now();

    try {
      const response = await sendChatMessage({
        message: trimmed,
        session_id: sessionId,
        phone_number: null,
      });

      const activeSessionId = response.session_id || sessionId || null;

      if (response.session_id) {
        setStoredSessionId(response.session_id);
        setSessionIdState(response.session_id);
      }

      setChatMeta({
        workflowType: response.workflow_type || "",
        state: response.state || "",
        nextStep: response.next_step || "",
      });

      // Proportional typing delay — hold indicator for at least MIN_TYPING_MS
      // or as long as it would "take" to type the response
      const elapsed = Date.now() - startedAt;
      const delay = typingDelay(response.message);
      const remaining = delay - elapsed;
      if (remaining > 0) await new Promise((r) => setTimeout(r, remaining));

      removeTypingMessage();

      const quickReplies = response.quick_replies?.map((qr) => ({
        id: qr.id,
        label: qr.label,
        value: qr.value,
      }));

      // If the response contains slot options, emit a slot-cards message
      // followed by the text message so the user can tap or type
      const isShowingSlots =
        response.state === "SCHEDULING_SHOWING_SLOTS" &&
        quickReplies &&
        quickReplies.length > 0;

      appendMessage({
        ...createTextMessage(createId(), "assistant", response.message),
        ...(isShowingSlots ? {} : quickReplies?.length ? { quickReplies } : {}),
      });

      if (isShowingSlots) {
        appendMessage({
          id: createId(),
          sender: "assistant",
          type: "slot-cards",
          text: "",
          createdAt: getTimestamp(),
          slots: quickReplies!,
        });
      }

      if (
        response.state === "BOOKED" &&
        response.metadata?.booking_confirmed &&
        response.metadata.provider_name &&
        response.metadata.specialty &&
        response.metadata.body_part &&
        response.metadata.booked_slot
      ) {
        appendMessage({
          id: createId(),
          sender: "assistant",
          type: "booking-card",
          text: "",
          createdAt: getTimestamp(),
          booking: {
            provider_name: response.metadata.provider_name,
            specialty: response.metadata.specialty,
            body_part: response.metadata.body_part,
            booked_slot: response.metadata.booked_slot,
          },
        });

        if (activeSessionId) {
          try {
            await sendBookingConfirmationEmail(activeSessionId);
          } catch (error) {
            alert(error instanceof Error ? error.message : "Email send failed");
          }
        }
      }
    } catch (error: any) {
      removeTypingMessage();
      appendMessage(
        createTextMessage(
          createId(),
          "assistant",
          error.message || "Something went wrong while connecting to the backend."
        )
      );
    } finally {
      setIsTyping(false);
    }
  };

  const handleVoiceHandoff = async () => {
    if (!sessionId || isCalling) return;
    try {
      setIsCalling(true);
      const response = await startVoiceHandoff(sessionId);
      appendMessage(
        createTextMessage(
          createId(),
          "assistant",
          response.message || "Calling your phone now. Please pick up to continue."
        )
      );
    } catch (error: any) {
      appendMessage(
        createTextMessage(
          createId(),
          "assistant",
          error.message || "I couldn't start the phone handoff right now."
        )
      );
    } finally {
      setIsCalling(false);
    }
  };

  const handleReset = () => {
    clearStoredChatState();
    setMessages(DEFAULT_MESSAGES);
    setChatMeta(DEFAULT_CHAT_META);
    setIsTyping(false);
    setIsCalling(false);
    setSessionIdState(null);
    setShowTimeoutWarning(false);
    resetTimeout();
  };

  if (!hydrated) return null;

  return (
    <div className="mx-auto flex h-screen w-full max-w-4xl flex-col px-4 py-6">
      <div className="overflow-hidden rounded-3xl border border-white/40 bg-white/60 shadow-xl backdrop-blur-xl">
        <ChatHeader />

        <div className="flex h-[calc(100vh-8rem)] flex-col">
          <div className="flex-1 overflow-y-auto">
            <MessageListErrorBoundary>
              <MessageList messages={messages} onQuickReply={handleSend} />
            </MessageListErrorBoundary>
          </div>

          <div className="border-t border-slate-200/60">
            {/* Session timeout warning banner */}
            {showTimeoutWarning && (
              <div className="flex items-center justify-between gap-3 bg-amber-50 px-4 py-2 text-xs text-amber-700 border-b border-amber-100">
                <span>⏱ Your session has been idle for 10 minutes. Send a message to continue, or start a new chat.</span>
                <button
                  onClick={handleReset}
                  className="shrink-0 rounded-md bg-amber-100 px-2 py-1 font-medium hover:bg-amber-200 transition"
                >
                  New chat
                </button>
              </div>
            )}

            <div className="flex items-center justify-between gap-3 px-4 pt-2">
              <button
                onClick={handleReset}
                className="inline-flex cursor-pointer items-center rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 transition hover:bg-blue-100 hover:text-blue-800"
              >
                New chat
              </button>

              <button
                onClick={handleVoiceHandoff}
                disabled={!sessionId || isCalling || isTyping}
                className="inline-flex cursor-pointer items-center rounded-lg border border-green-200 bg-green-50 px-3 py-1.5 text-sm font-medium text-green-700 transition hover:bg-green-100 hover:text-green-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isCalling ? "Calling..." : "Continue on phone"}
              </button>
            </div>

            <ChatInput onSend={handleSend} disabled={isTyping || isCalling} />
          </div>
        </div>
      </div>
    </div>
  );
}
