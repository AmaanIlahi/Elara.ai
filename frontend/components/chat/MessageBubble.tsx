import BookedAppointmentCard from "@/components/cards/BookedAppointmentCard";
import { Message } from "@/lib/types";

type Props = {
  message: Message;
  onQuickReply: (label: string) => void;
};

export default function MessageBubble({
  message,
  onQuickReply,
}: Props) {
  const isUser = message.sender === "user";

  if (message.type === "typing") {
    return (
      <div className="flex justify-start">
        <div className="rounded-2xl border border-white/40 bg-white/70 px-4 py-3 text-slate-800 shadow-sm backdrop-blur-md">
          <div className="flex items-center gap-1">
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
            <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="max-w-[85%]">
        {message.type === "text" ? (
          <div
            className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${
              isUser
                ? "bg-blue-600 text-white shadow-lg"
                : "border border-white/40 bg-white/70 text-slate-800 backdrop-blur-md"
            }`}
          >
            <p className="whitespace-pre-wrap font-medium leading-6">
              {message.text}
            </p>

            <p
              className={`mt-2 text-[11px] ${
                isUser ? "text-blue-100/90" : "text-slate-500"
              }`}
            >
              {message.createdAt}
            </p>
          </div>
        ) : null}

        {message.type === "text" && message.quickReplies?.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {message.quickReplies.map((reply) => (
              <button
                key={reply.id}
                onClick={() => onQuickReply(reply.label)}
                className="
                  cursor-pointer
                  rounded-full
                  border border-white/40
                  bg-white/60
                  px-4 py-1.5
                  text-sm text-blue-700
                  backdrop-blur-md
                  transition-all duration-200 ease-out
                  hover:-translate-y-[1px]
                  hover:border-blue-200
                  hover:bg-blue-50
                  hover:text-blue-800
                  hover:shadow-[0_4px_20px_rgba(37,99,235,0.18)]
                  active:scale-95
                "
              >
                {reply.label}
              </button>
            ))}
          </div>
        ) : null}

        {message.type === "booking-card" ? (
          <BookedAppointmentCard booking={message.booking} />
        ) : null}
      </div>
    </div>
  );
}