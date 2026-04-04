export type Sender = "user" | "assistant";

export type QuickReply = {
  id: string;
  label: string;
  value?: string; // text sent when clicked; falls back to label
};

export type BookingCardData = {
  provider_name: string;
  specialty: string;
  body_part: string;
  booked_slot: {
    date: string;
    time: string;
  };
};

type BaseMessage = {
  id: string;
  sender: Sender;
  text: string;
  createdAt: string;
};

export type SlotOption = {
  id: string;
  label: string;   // human-readable "Mon, Apr 7 · 9:00 AM"
  value: string;   // "1", "2" … sent to backend
};

export type Message =
  | (BaseMessage & {
      type: "text";
      quickReplies?: QuickReply[];
    })
  | (BaseMessage & {
      sender: "assistant";
      type: "typing";
    })
  | (BaseMessage & {
      sender: "assistant";
      type: "booking-card";
      booking: BookingCardData;
    })
  | (BaseMessage & {
      sender: "assistant";
      type: "slot-cards";
      slots: SlotOption[];
    })
  | (BaseMessage & {
      sender: "assistant";
      type: "intake-summary";
      summary: IntakeSummary;
    })
  | (BaseMessage & {
      sender: "assistant";
      type: "appointment-options";
      slots: AppointmentSlot[];
    });


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

export type SchedulingField = keyof IntakeSummary;

export type SchedulingState = {
  active: boolean;
  data: Partial<IntakeSummary>;
  currentField: SchedulingField | null;
  matchedSlots: AppointmentSlot[];
  filteredSlots: AppointmentSlot[];
  isComplete: boolean;
};