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
  /** Needed for the "Add to calendar" download; absent on cards saved by older versions. */
  session_id?: string;
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
    });
