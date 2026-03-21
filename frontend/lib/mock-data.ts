import { Message } from "./types";
import { getTimestamp } from "./time";

export const initialMessages: Message[] = [
  {
    id: "m1",
    sender: "assistant",
    type: "text",
    text: "Hi, I’m Elara, your virtual assistant. I can help you schedule an appointment, check on a prescription refill, or share office hours and address details.",
    createdAt: "Now",
    quickReplies: [
      { id: "q1", label: "Schedule an appointment" },
      { id: "q2", label: "Prescription refill" },
      { id: "q3", label: "Office hours and address" },
    ],
  },
];