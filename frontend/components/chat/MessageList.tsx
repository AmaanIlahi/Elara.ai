"use client";

import { useEffect, useRef } from "react";
import { Message } from "@/lib/types";
import MessageBubble from "./MessageBubble";

type Props = {
  messages: Message[];
  onQuickReply: (label: string) => void;
};

export default function MessageList({
  messages,
  onQuickReply,
}: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto bg-transparent px-4 py-6 md:px-6">
      <div className="space-y-4">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onQuickReply={onQuickReply}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}