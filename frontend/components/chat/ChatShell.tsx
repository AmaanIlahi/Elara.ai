"use client";

import { useEffect, useState } from "react";
import ChatHeader from "./ChatHeader";
import MessageList from "./MessageList";
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

function createTextMessage(
  id: string,
  sender: "user" | "assistant",
  text: string
): Message {
  return {
    id,
    sender,
    type: "text",
    text,
    createdAt: getTimestamp(),
  };
}

function createTypingMessage(id: string): Message {
  return {
    id,
    sender: "assistant",
    type: "typing",
    text: "",
    createdAt: getTimestamp(),
  };
}

const DEFAULT_MESSAGES: Message[] = [
  {
    id: "welcome-message",
    sender: "assistant",
    type: "text",
    text: "Hi, I’m Elara. How can I help you today?",
    createdAt: "Now",
  },
];

const DEFAULT_CHAT_META = {
  workflowType: "",
  state: "",
  nextStep: "",
};

export default function ChatShell() {
  const [messages, setMessages] = useState<Message[]>(DEFAULT_MESSAGES);
  const [isTyping, setIsTyping] = useState(false);
  const [isCalling, setIsCalling] = useState(false);
  const [chatMeta, setChatMeta] = useState(DEFAULT_CHAT_META);
  const [hydrated, setHydrated] = useState(false);
  const [sessionId, setSessionIdState] = useState<string | null>(null);

  useEffect(() => {
    const storedMessages = getStoredMessages<Message>();
    const storedMeta = getStoredChatMeta<typeof DEFAULT_CHAT_META>();
    const storedSessionId = getStoredSessionId();

    if (storedMessages && storedMessages.length > 0) {
      setMessages(storedMessages.filter((message) => message.type !== "typing"));
    }

    if (storedMeta) {
      setChatMeta(storedMeta);
    }

    if (storedSessionId) {
      setSessionIdState(storedSessionId);
    }

    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    setStoredMessages(messages);
  }, [messages, hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    setStoredChatMeta(chatMeta);
  }, [chatMeta, hydrated]);

  const appendMessage = (message: Message) => {
    setMessages((prev) => [...prev, message]);
  };

  const removeTypingMessage = () => {
    setMessages((prev) => prev.filter((message) => message.type !== "typing"));
  };

  const handleSend = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isTyping) return;

    appendMessage(createTextMessage(createId(), "user", trimmed));

    setIsTyping(true);
    appendMessage(createTypingMessage(createId()));

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

      removeTypingMessage();

      appendMessage(
        createTextMessage(createId(), "assistant", response.message)
      );

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

        // console.log("BOOKING RESPONSE SESSION ID", response.session_id);
        // console.log("CURRENT SESSION ID BEFORE EMAIL", activeSessionId);

      if (activeSessionId) {
        try {
          await sendBookingConfirmationEmail(activeSessionId);
        } catch (error) {
          // console.error("Failed to send confirmation email", error);
          alert(error instanceof Error ? error.message : "Email send failed");
          // console.error("Failed to send confirmation email", error);
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
  };

  if (!hydrated) {
    return null;
  }

  return (
    <div className="mx-auto flex h-screen w-full max-w-4xl flex-col px-4 py-6">
      <div className="overflow-hidden rounded-3xl border border-white/40 bg-white/60 shadow-xl backdrop-blur-xl">
        <ChatHeader />

        <div className="flex h-[calc(100vh-8rem)] flex-col">
          <div className="flex-1 overflow-y-auto">
            <MessageList messages={messages} onQuickReply={handleSend} />
          </div>

          <div className="border-t border-slate-200/60">
            {/* <div className="px-6 pt-2 text-xs text-slate-500">
              Workflow: {chatMeta.workflowType || "-"} | State:{" "}
              {chatMeta.state || "-"} | Next: {chatMeta.nextStep || "-"}
            </div> */}

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