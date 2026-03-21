from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import re

from app.data.provider_data import PROVIDERS


UNSUPPORTED_CONCERN_KEYWORDS = {
    "eye": "eye-related concerns",
    "vision": "eye-related concerns",
    "tooth": "dental concerns",
    "teeth": "dental concerns",
    "dental": "dental concerns",
    "ear": "ear-related concerns",
    "hearing": "ear-related concerns",
}

WEEKDAY_MAP = {
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
}


def extract_body_part(message: str) -> Optional[str]:
    message = message.lower().strip()

    for provider in PROVIDERS:
        for body_part in provider["body_parts"]:
            normalized_body_part = body_part.lower()
            if normalized_body_part in message:
                return normalized_body_part

    return None


def detect_unsupported_concern(message: str) -> Optional[str]:
    normalized = message.lower().strip()

    for keyword, label in UNSUPPORTED_CONCERN_KEYWORDS.items():
        if re.search(rf"\b{re.escape(keyword)}\b", normalized):
            return label

    return None


def find_provider_for_body_part(body_part: str) -> Optional[Dict[str, Any]]:
    for provider in PROVIDERS:
        if body_part in provider["body_parts"]:
            return provider
    return None


def get_next_available_slots(provider: Dict[str, Any], limit: int = 5) -> List[Dict[str, str]]:
    return provider["slots"][:limit]


def build_slot_list_message(
    provider_name: str,
    specialty: str,
    body_part: str,
    slots: List[Dict[str, str]],
    intro: Optional[str] = None,
) -> str:
    slot_lines = [
        f"{idx + 1}. {slot['date']} at {slot['time']}"
        for idx, slot in enumerate(slots)
    ]
    slot_text = "\n".join(slot_lines)

    if not intro:
        intro = f"I'm sorry to hear about your {body_part} concern. Let me help you get that taken care of. I found availability with {provider_name} ({specialty})."

    return (
        f"{intro}\n"
        f"Here are the next available slots:\n{slot_text}\n"
        f"Please reply with the date/time that works best for you."
    )


def normalize_requested_day(day_text: Optional[str]) -> Optional[str]:
    if not day_text:
        return None

    normalized = day_text.lower().strip()
    normalized = normalized.replace("next ", "").replace("this ", "").strip()

    for key, value in WEEKDAY_MAP.items():
        if key == normalized:
            return value

    return None


def extract_weekday_preference(message: str) -> Optional[str]:
    normalized = message.lower()
    normalized = normalized.replace("next ", " ").replace("this ", " ")

    for key, value in WEEKDAY_MAP.items():
        if key in normalized:
            return value

    return None


def extract_day_of_month(message: str) -> Optional[int]:
    # Avoid treating times like 9:00 AM as day-of-month requests
    if ":" in message:
        return None

    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", message.lower())
    if not match:
        return None

    day = int(match.group(1))
    if 1 <= day <= 31:
        return day

    return None


def filter_slots_by_weekday(slots: List[Dict[str, str]], weekday: str) -> List[Dict[str, str]]:
    filtered = []

    for slot in slots:
        slot_date = datetime.strptime(slot["date"], "%Y-%m-%d")
        if slot_date.strftime("%A").lower() == weekday.lower():
            filtered.append(slot)

    return filtered


def filter_slots_by_day_of_month(slots: List[Dict[str, str]], day: int) -> List[Dict[str, str]]:
    filtered = []

    for slot in slots:
        slot_date = datetime.strptime(slot["date"], "%Y-%m-%d")
        if slot_date.day == day:
            filtered.append(slot)

    return filtered


def normalize_time_text(value: str) -> str:
    return value.lower().replace(" ", "").replace(".", "")


def parse_time_choice(user_message: str, slots: List[Dict[str, str]]) -> Optional[int]:
    normalized_input = normalize_time_text(user_message.strip())

    for idx, slot in enumerate(slots, start=1):
        slot_time_normalized = normalize_time_text(slot["time"])

        if normalized_input == slot_time_normalized:
            return idx

        # Support "9am" for "09:00 AM"
        simplified_slot_time = slot_time_normalized.replace(":00", "")
        if normalized_input == simplified_slot_time:
            return idx

    return None


def parse_relative_slot_preference(user_message: str, slots: List[Dict[str, str]]) -> Optional[int]:
    normalized = user_message.lower().strip()

    if not slots:
        return None

    earliest_phrases = [
        "early one",
        "earlier one",
        "first one",
        "morning one",
        "earliest",
        "early slot",
    ]
    latest_phrases = [
        "later one",
        "last one",
        "afternoon one",
        "latest",
        "late one",
        "late slot",
    ]

    if any(phrase in normalized for phrase in earliest_phrases):
        return 1

    if any(phrase in normalized for phrase in latest_phrases):
        return len(slots)

    return None


def resolve_slot_preference(
    user_message: str,
    slots: List[Dict[str, str]],
    provider_name: str,
    specialty: str,
    body_part: str,
    requested_day: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    weekday = normalize_requested_day(requested_day) or extract_weekday_preference(user_message)
    if weekday:
        filtered_slots = filter_slots_by_weekday(slots, weekday)
        if filtered_slots:
            return {
                "state": "SCHEDULING_SHOWING_SLOTS",
                "message": build_slot_list_message(
                    provider_name,
                    specialty,
                    body_part,
                    filtered_slots,
                    intro=f"I found the following availability on {weekday} with {provider_name} ({specialty}) for {body_part}.",
                ),
                "metadata": {
                    "provider_name": provider_name,
                    "specialty": specialty,
                    "body_part": body_part,
                    "slots": filtered_slots,
                    "requested_day": weekday,
                },
            }

        return {
            "state": "SCHEDULING_SHOWING_SLOTS",
            "message": (
                f"I don’t see any availability on {weekday} right now for {body_part}. "
                f"Please choose from the currently available slots or tell me another preferred day."
            ),
            "metadata": {
                "provider_name": provider_name,
                "specialty": specialty,
                "body_part": body_part,
                "slots": slots,
                "requested_day": weekday,
            },
        }

    day_of_month = extract_day_of_month(user_message)
    if day_of_month:
        filtered_slots = filter_slots_by_day_of_month(slots, day_of_month)
        if filtered_slots:
            return {
                "state": "SCHEDULING_SHOWING_SLOTS",
                "message": build_slot_list_message(
                    provider_name,
                    specialty,
                    body_part,
                    filtered_slots,
                    intro=f"I found the following availability on the {day_of_month}th with {provider_name} ({specialty}) for {body_part}.",
                ),
                "metadata": {
                    "provider_name": provider_name,
                    "specialty": specialty,
                    "body_part": body_part,
                    "slots": filtered_slots,
                    "requested_day": None,
                },
            }

    return None


def build_scheduling_response(user_message: str) -> Dict[str, Any]:
    body_part = extract_body_part(user_message)

    if not body_part:
        unsupported_concern = detect_unsupported_concern(user_message)

        if unsupported_concern:
            return {
                "state": "SCHEDULING_UNSUPPORTED_BODY_PART",
                "message": (
                    f"I'm sorry, we do not currently schedule appointments for {unsupported_concern}. "
                    f"Please contact the office directly or let me know if you need help with another concern."
                ),
                "workflow_type": "scheduling",
                "metadata": {"unsupported_concern": unsupported_concern},
            }

        return {
            "state": "SCHEDULING_NEEDS_BODY_PART",
            "message": "I can help schedule your appointment. Which body part or concern would you like to be seen for?",
            "workflow_type": "scheduling",
            "metadata": {},
        }

    provider = find_provider_for_body_part(body_part)

    if not provider:
        return {
            "state": "SCHEDULING_UNSUPPORTED_BODY_PART",
            "message": (
                f"At the moment, we do not have a provider available for {body_part}. "
                f"Please contact the office for further assistance."
            ),
            "workflow_type": "scheduling",
            "metadata": {"body_part": body_part},
        }

    slots = get_next_available_slots(provider)

    return {
        "state": "SCHEDULING_SHOWING_SLOTS",
        "message": build_slot_list_message(
            provider["name"],
            provider["specialty"],
            body_part,
            slots,
        ),
        "workflow_type": "scheduling",
        "metadata": {
            "body_part": body_part,
            "provider_id": provider["provider_id"],
            "provider_name": provider["name"],
            "specialty": provider["specialty"],
            "slots": slots,
        },
    }


def confirm_booking_from_session_data(collected_data: dict, slot_choice: int) -> Tuple[bool, dict]:
    slots = collected_data.get("slots", [])

    if not slots:
        return False, {
            "state": "SCHEDULING_NO_SLOTS_FOUND",
            "message": "I could not find any available slots in the current session. Please start scheduling again.",
            "metadata": {},
        }

    if slot_choice < 1 or slot_choice > len(slots):
        return False, {
            "state": "SCHEDULING_INVALID_SLOT_CHOICE",
            "message": f"Please choose a valid slot number between 1 and {len(slots)}.",
            "metadata": {"slots": slots},
        }

    selected_slot = slots[slot_choice - 1]

    provider_name = collected_data.get("provider_name")
    specialty = collected_data.get("specialty")
    body_part = collected_data.get("body_part")

    confirmation_metadata = {
        "provider_name": provider_name,
        "specialty": specialty,
        "body_part": body_part,
        "booked_slot": selected_slot,
        "booking_confirmed": True,
    }

    return True, {
        "state": "BOOKED",
        "message": (
            f"Your appointment has been confirmed with {provider_name} ({specialty}) "
            f"for {body_part} on {selected_slot['date']} at {selected_slot['time']}."
        ),
        "metadata": confirmation_metadata,
    }


def parse_slot_choice(user_message: str) -> Optional[int]:
    message = user_message.strip()

    if message.isdigit():
        return int(message)

    words = message.lower().split()
    for word in words:
        if word.isdigit():
            return int(word)

    return None