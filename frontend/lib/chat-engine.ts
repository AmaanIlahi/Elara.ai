import { AppointmentSlot, IntakeSummary, Message, SchedulingState } from "./types";
import {
  fieldQuestions,
  getNextField,
  matchSlotsByReason,
  validateField,
} from "./conversation";
import { getTimestamp } from "./time";

export function createTextMessage(
  id: string,
  sender: "user" | "assistant",
  text: string,
  quickReplies?: { id: string; label: string }[]
): Message {
  return {
    id,
    sender,
    type: "text",
    text,
    quickReplies,
    createdAt: getTimestamp(),
  };
}

export function createTypingMessage(id: string): Message {
  return {
    id,
    sender: "assistant",
    type: "typing",
    text: "",
    createdAt: getTimestamp(),
  };
}

export function processSchedulingStep(
  scheduling: SchedulingState,
  input: string
):
  | {
      kind: "validation-error";
      message: Message;
    }
  | {
      kind: "next-question";
      updatedScheduling: SchedulingState;
      message: Message;
    }
  | {
      kind: "complete";
      updatedScheduling: SchedulingState;
      summaryMessage: Message;
      slotsMessage: Message | null;
    } {
  if (!scheduling.currentField) {
    return {
      kind: "validation-error",
      message: createTextMessage(
        crypto.randomUUID(),
        "assistant",
        "Something went wrong in the scheduling flow. Please start over."
      ),
    };
  }

  const validation = validateField(scheduling.currentField, input);

  if (!validation.isValid) {
    return {
      kind: "validation-error",
      message: createTextMessage(
        crypto.randomUUID(),
        "assistant",
        validation.message || "That input looks invalid."
      ),
    };
  }

  const updatedData = {
    ...scheduling.data,
    [scheduling.currentField]: input.trim(),
  };

  const nextField = getNextField(updatedData);

  if (nextField) {
    return {
      kind: "next-question",
      updatedScheduling: {
        ...scheduling,
        data: updatedData,
        currentField: nextField,
      },
      message: createTextMessage(
        crypto.randomUUID(),
        "assistant",
        fieldQuestions[nextField],
        [{ id: "restart", label: "Start over" }]
      ),
    };
  }

  const fullData = updatedData as IntakeSummary;
  const slots = matchSlotsByReason(fullData.reason);

  const summaryMessage: Message = {
    id: crypto.randomUUID(),
    sender: "assistant",
    type: "intake-summary",
    text: "Thanks. Here is the information I captured for your appointment request.",
    summary: fullData,
    createdAt: getTimestamp(),
  };

  const slotsMessage: Message | null =
    slots.length > 0
      ? {
          id: crypto.randomUUID(),
          sender: "assistant",
          type: "appointment-options",
          text: "I found these available appointments. Please select a slot that works for you, or ask for a specific day like Tuesday.",
          slots,
          createdAt: getTimestamp(),
        }
      : createTextMessage(
          crypto.randomUUID(),
          "assistant",
          "I’m sorry, but we do not currently have a provider for that treatment area in this demo clinic.",
          [{ id: "restart", label: "Start over" }]
        );

  return {
    kind: "complete",
    updatedScheduling: {
      ...scheduling,
      data: fullData,
      currentField: null,
      matchedSlots: slots,
      filteredSlots: slots,
      isComplete: true,
    },
    summaryMessage,
    slotsMessage,
  };
}

export function createBookingConfirmationMessage(
  slot: AppointmentSlot,
  email?: string
): Message {
  return createTextMessage(
    crypto.randomUUID(),
    "assistant",
    `You’re all set. I’ve booked your appointment with ${slot.doctorName}, ${slot.specialty}, on ${slot.date} at ${slot.time}. A confirmation has been sent to ${email || "your email address"}.`,
    [{ id: "restart", label: "Book another appointment" }]
  );
}