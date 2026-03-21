import {
  AppointmentSlot,
  IntakeSummary,
  SchedulingField,
  SchedulingState,
} from "./types";

export const fieldQuestions: Record<SchedulingField, string> = {
  firstName: "Great, let’s get that scheduled. What is your first name?",
  lastName: "Thanks. What is your last name?",
  dob: "What is your date of birth? Please use MM/DD/YYYY.",
  phone: "What is your phone number?",
  email: "What is your email address?",
  reason:
    "What is the reason for your appointment, or which body part would you like treated?",
};

const mockSlots: AppointmentSlot[] = [
  {
    id: "slot1",
    doctorName: "Dr. Sarah Chen",
    specialty: "Cardiology",
    bodyPart: "heart",
    date: "Apr 2, 2026",
    time: "10:00 AM",
    weekday: "thursday",
  },
  {
    id: "slot2",
    doctorName: "Dr. Sarah Chen",
    specialty: "Cardiology",
    bodyPart: "heart",
    date: "Apr 3, 2026",
    time: "2:30 PM",
    weekday: "friday",
  },
  {
    id: "slot3",
    doctorName: "Dr. Michael Rivera",
    specialty: "Dermatology",
    bodyPart: "skin",
    date: "Apr 4, 2026",
    time: "11:00 AM",
    weekday: "saturday",
  },
  {
    id: "slot4",
    doctorName: "Dr. Michael Rivera",
    specialty: "Dermatology",
    bodyPart: "skin",
    date: "Apr 6, 2026",
    time: "9:30 AM",
    weekday: "monday",
  },
  {
    id: "slot5",
    doctorName: "Dr. Priya Patel",
    specialty: "Orthopedics",
    bodyPart: "knee",
    date: "Apr 7, 2026",
    time: "1:00 PM",
    weekday: "tuesday",
  },
  {
    id: "slot6",
    doctorName: "Dr. Priya Patel",
    specialty: "Orthopedics",
    bodyPart: "back",
    date: "Apr 8, 2026",
    time: "3:00 PM",
    weekday: "wednesday",
  },
  {
    id: "slot7",
    doctorName: "Dr. James Wilson",
    specialty: "ENT",
    bodyPart: "ear",
    date: "Apr 9, 2026",
    time: "10:30 AM",
    weekday: "thursday",
  },
  {
    id: "slot8",
    doctorName: "Dr. James Wilson",
    specialty: "ENT",
    bodyPart: "throat",
    date: "Apr 10, 2026",
    time: "12:00 PM",
    weekday: "friday",
  },
];

const keywordMap: Record<string, string[]> = {
  heart: ["heart", "chest", "cardio", "palpitations"],
  skin: ["skin", "rash", "dermatology", "acne", "eczema"],
  knee: ["knee", "leg", "joint", "knee pain"],
  back: ["back", "spine", "lower back", "upper back"],
  ear: ["ear", "hearing", "earache"],
  throat: ["throat", "tonsil", "sore throat"],
};

const weekdays = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

export function getNextField(
  data: Partial<IntakeSummary>
): SchedulingField | null {
  const orderedFields: SchedulingField[] = [
    "firstName",
    "lastName",
    "dob",
    "phone",
    "email",
    "reason",
  ];

  for (const field of orderedFields) {
    if (!data[field]) return field;
  }

  return null;
}

export function matchSlotsByReason(reason: string): AppointmentSlot[] {
  const lowerReason = reason.toLowerCase();

  for (const [bodyPart, keywords] of Object.entries(keywordMap)) {
    const matched = keywords.some((keyword) => lowerReason.includes(keyword));
    if (matched) {
      return mockSlots.filter((slot) => slot.bodyPart === bodyPart);
    }
  }

  return [];
}

export function extractWeekdayPreference(text: string): string | null {
  const lower = text.toLowerCase();

  for (const day of weekdays) {
    if (lower.includes(day)) return day;
  }

  return null;
}

export function filterSlotsByWeekday(
  slots: AppointmentSlot[],
  weekday: string
): AppointmentSlot[] {
  return slots.filter((slot) => slot.weekday === weekday.toLowerCase());
}

export function validateField(
  field: SchedulingField,
  value: string
): { isValid: boolean; message?: string } {
  const trimmed = value.trim();

  if (!trimmed) {
    return { isValid: false, message: "Please provide a response to continue." };
  }

  switch (field) {
    case "firstName":
    case "lastName":
      if (trimmed.length < 2) {
        return {
          isValid: false,
          message: "Please enter a valid name with at least 2 characters.",
        };
      }
      return { isValid: true };

    case "dob":
      if (!/^\d{2}\/\d{2}\/\d{4}$/.test(trimmed)) {
        return {
          isValid: false,
          message: "Please enter your date of birth in MM/DD/YYYY format.",
        };
      }
      return { isValid: true };

    case "phone":
      if (!/^[0-9()\-\s+]{10,}$/.test(trimmed)) {
        return {
          isValid: false,
          message: "Please enter a valid phone number.",
        };
      }
      return { isValid: true };

    case "email":
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
        return {
          isValid: false,
          message: "Please enter a valid email address.",
        };
      }
      return { isValid: true };

    case "reason":
      if (trimmed.length < 3) {
        return {
          isValid: false,
          message:
            "Please provide a bit more detail about the appointment reason.",
        };
      }
      return { isValid: true };

    default:
      return { isValid: true };
  }
}

export function createInitialSchedulingState(): SchedulingState {
  return {
    active: false,
    currentField: null,
    data: {},
    matchedSlots: [],
    filteredSlots: [],
    isComplete: false,
  };
}