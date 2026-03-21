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

export async function submitSchedulingRequest(
  payload: IntakeSummary
): Promise<SchedulingResponse> {
  const response = await fetch("/api/schedule", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error("Failed to submit scheduling request");
  }

  return response.json();
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type ChatRequest = {
  message: string;
  session_id?: string | null;
  phone_number?: string | null;
};

// export type ChatResponse = {
//   session_id: string;
//   workflow_type?: string;
//   state?: string;
//   message: string;
//   next_step?: string;
// };

export type ChatResponse = {
  session_id: string;
  workflow_type?: string;
  state?: string;
  message: string;
  next_step?: string;
  metadata?: {
    provider_name?: string;
    specialty?: string;
    body_part?: string;
    booked_slot?: {
      date: string;
      time: string;
    };
    booking_confirmed?: boolean;
  };
};

export async function sendChatMessage(
  payload: ChatRequest
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.detail || "Failed to connect to backend");
  }

  return data;
}

export type VoiceHandoffResponse = {
  success: boolean;
  call_id?: string | null;
  message: string;
};

export async function startVoiceHandoff(
  sessionId: string
): Promise<VoiceHandoffResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/voice/handoff`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.detail || "Failed to start phone handoff");
  }

  return data;
}


export async function sendBookingConfirmationEmail(sessionId: string) {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/send-confirmation-email`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ session_id: sessionId }),
    }
  );

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    console.error("EMAIL API ERROR", {
      status: response.status,
      data,
    });
    throw new Error(data?.detail || "Failed to send confirmation email");
  }

  return data;
}