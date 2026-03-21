"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  onSend: (text: string) => void;
  disabled?: boolean;
};

export default function ChatInput({ onSend, disabled = false }: Props) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  useEffect(() => {
    if (!disabled) {
      inputRef.current?.focus();
    }
  }, [disabled]);

  return (
    <div className="glass px-4 py-4 md:px-6">
      <div className="flex items-center gap-3">
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              handleSubmit();
            }
          }}
          placeholder={disabled ? "Elara is typing..." : "Type your message..."}
          disabled={disabled}
          className="flex-1 rounded-xl border border-white/40 bg-white/70 px-4 py-3 text-sm text-slate-800 outline-none backdrop-blur-md placeholder:text-slate-400 focus:border-blue-400 disabled:cursor-not-allowed disabled:opacity-60"
        />

        <button
          onClick={handleSubmit}
          disabled={disabled}
          className="cursor-pointer rounded-xl bg-blue-600 px-5 py-3 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}