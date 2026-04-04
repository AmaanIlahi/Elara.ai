from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import re

from app.data.provider_data import PROVIDERS, is_slot_booked, mark_slot_booked
from app.data.practice_data import PRACTICE_INFO


def format_slot_date(date_str: str, time_str: str) -> str:
    """Return a human-readable slot label, e.g. 'Mon, Apr 7 · 9:00 AM'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        # Use dt.day (int) to avoid %-d which is Linux-only
        day = f"{dt.strftime('%a, %b')} {dt.day}"  # 'Mon, Apr 7'
    except (ValueError, TypeError):
        day = date_str
    # Normalise time: strip leading zero from hour
    try:
        t = datetime.strptime(time_str, "%I:%M %p")
        hour = t.hour % 12 or 12
        time_label = f"{hour}:{t.strftime('%M %p')}"  # '9:00 AM'
    except (ValueError, TypeError):
        time_label = time_str
    return f"{day} · {time_label}"


def build_slot_quick_replies(slots: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Build a quick-reply object for each slot."""
    replies = []
    for idx, slot in enumerate(slots, start=1):
        replies.append({
            "id": f"slot_{idx}",
            "label": format_slot_date(slot["date"], slot["time"]),
            "value": str(idx),
        })
    return replies


UNSUPPORTED_CONCERN_KEYWORDS = {
    # Eye / vision
    "eye": "eye-related concerns",
    "vision": "eye-related concerns",
    # Dental
    "tooth": "dental concerns",
    "teeth": "dental concerns",
    "dental": "dental concerns",
    # Ear
    "ear": "ear-related concerns",
    "hearing": "ear-related concerns",
    # Neurological / head
    "head": "headaches or neurological concerns",
    "headache": "headaches or neurological concerns",
    "migraine": "migraines or neurological concerns",
    "dizziness": "dizziness or neurological concerns",
    "dizzy": "dizziness or neurological concerns",
    # General / internal medicine (not mapped to a specialist here)
    "stomach": "stomach or digestive concerns",
    "chest": "chest-related concerns",
    "heart": "cardiac concerns",
    "breathing": "respiratory concerns",
    "lung": "respiratory concerns",
    "fever": "general illness concerns",
    "fatigue": "general wellness concerns",
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
    provider_id = provider["provider_id"]
    available = [
        s for s in provider["slots"]
        if not is_slot_booked(provider_id, s["date"], s["time"])
    ]
    return available[:limit]


def build_slot_list_message(
    provider_name: str,
    specialty: str,
    body_part: str,
    slots: List[Dict[str, str]],
    intro: Optional[str] = None,
) -> str:
    slot_lines = [
        f"{idx + 1}. {format_slot_date(slot['date'], slot['time'])}"
        for idx, slot in enumerate(slots)
    ]
    slot_text = "\n".join(slot_lines)

    if not intro:
        intro = (
            f"I found some great availability with {provider_name} ({specialty}) "
            f"for your {body_part}. Here are the next open slots — just tap one or type the number:"
        )

    return f"{intro}\n\n{slot_text}"


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
                f"Hmm, it looks like there’s no availability on {weekday} right now for {body_part}. "
                f"Here are the nearest open slots — feel free to pick one or suggest another day:"
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
            phone = PRACTICE_INFO.get("phone", "the office")
            return {
                "state": "SCHEDULING_UNSUPPORTED_BODY_PART",
                "message": (
                    f"I'm sorry to hear that — unfortunately we don't currently schedule appointments for {unsupported_concern} through this system. "
                    f"Please give the office a call at **{phone}** and they'll be happy to help. Is there anything else I can assist you with?"
                ),
                "workflow_type": "scheduling",
                "metadata": {"unsupported_concern": unsupported_concern},
            }

        return {
            "state": "SCHEDULING_NEEDS_BODY_PART",
            "message": "Of course! What's the concern you'd like to be seen for? Just let me know the area or symptom and I'll find the right specialist.",
            "workflow_type": "scheduling",
            "metadata": {},
        }

    provider = find_provider_for_body_part(body_part)

    if not provider:
        phone = PRACTICE_INFO.get("phone", "the office")
        return {
            "state": "SCHEDULING_UNSUPPORTED_BODY_PART",
            "message": (
                f"I'm sorry, it looks like we don't currently have a specialist available for {body_part}. "
                f"Please give us a call at **{phone}** and we'll point you in the right direction."
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

    # Mark the slot as taken so no other session can book it
    provider_id = collected_data.get("provider_id", "")
    mark_slot_booked(provider_id, selected_slot["date"], selected_slot["time"])

    slot_label = format_slot_date(selected_slot["date"], selected_slot["time"])
    return True, {
        "state": "BOOKED",
        "message": (
            f"You're all set! Your appointment with {provider_name} ({specialty}) "
            f"for {body_part} is confirmed for {slot_label}. "
            f"You'll receive a confirmation email shortly."
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