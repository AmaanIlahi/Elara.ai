from typing import Dict, Any, Optional, Tuple
import re
from datetime import datetime


REQUIRED_INTAKE_FIELDS = [
    "first_name",
    "last_name",
    "dob",
    "phone_number",
    "email",
]


FIELD_PROMPTS = {
    "first_name": "Before we continue, may I have your first name?",
    "last_name": "Thanks. May I also have your last name?",
    "dob": "What is your date of birth? Please use YYYY-MM-DD format.",
    "phone_number": "What is your phone number?",
    "email": "What is your email address?",
}

FIELD_VALIDATION_ERRORS = {
    "first_name": "That doesn't look like a valid first name. Please enter your first name using letters only.",
    "last_name": "That doesn't look like a valid last name. Please enter your last name using letters only.",
    "dob": "That doesn't look like a valid date of birth. Please enter a real past date in YYYY-MM-DD format, for example 2000-01-01.",
    "phone_number": "That doesn't look like a valid 10-digit phone number. Please enter numbers only, for example 1234567890.",
    "email": "That doesn't look like a valid email address. Please enter something like name@example.com.",
}

MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def get_missing_intake_field(collected_data: Dict[str, Any], session_dict: Dict[str, Any]) -> Optional[str]:
    for field in REQUIRED_INTAKE_FIELDS:
        session_value = session_dict.get(field)
        collected_value = collected_data.get(field)

        if not session_value and not collected_value:
            return field
    return None


def build_intake_prompt(missing_field: str) -> str:
    return FIELD_PROMPTS[missing_field]


def validate_dob(value: str) -> bool:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        # Reject future dates and unreasonably old dates
        if parsed > datetime.now() or parsed.year < 1900:
            return False
        return True
    except ValueError:
        return False


def validate_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return len(digits) == 10


def validate_email(value: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value) is not None


def looks_like_dob_missing_year(value: str) -> bool:
    normalized = value.lower().strip()
    has_day = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", normalized) is not None
    has_month = any(re.search(rf"\b{re.escape(month)}\b", normalized) for month in MONTH_MAP.keys())
    has_year = re.search(r"\b\d{4}\b", normalized) is not None
    return has_day and has_month and not has_year


def normalize_dob(value: str) -> Optional[str]:
    text = value.strip()
    if not text:
        return None

    if validate_dob(text):
        return text

    normalized = text.lower().strip()
    normalized = normalized.replace(",", " ")
    normalized = re.sub(r"\s+", " ", normalized)

    # Remove ordinal suffixes like 30th -> 30
    normalized = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", normalized)

    # Try month name formats:
    # "30 july 1998", "july 30 1998"
    month_pattern = "|".join(sorted(MONTH_MAP.keys(), key=len, reverse=True))

    match_day_month_year = re.search(
        rf"\b(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})\b",
        normalized,
    )
    if match_day_month_year:
        day = int(match_day_month_year.group(1))
        month = MONTH_MAP[match_day_month_year.group(2)]
        year = int(match_day_month_year.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    match_month_day_year = re.search(
        rf"\b({month_pattern})\s+(\d{{1,2}})\s+(\d{{4}})\b",
        normalized,
    )
    if match_month_day_year:
        month = MONTH_MAP[match_month_day_year.group(1)]
        day = int(match_month_day_year.group(2))
        year = int(match_month_day_year.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    # Try slash or dash numeric formats
    numeric_patterns = [
        ("%d/%m/%Y", normalized),
        ("%m/%d/%Y", normalized),
        ("%d-%m-%Y", normalized),
        ("%m-%d-%Y", normalized),
    ]

    for fmt, candidate in numeric_patterns:
        try:
            parsed = datetime.strptime(candidate, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def extract_field_value(field_name: str, user_message: str) -> Optional[str]:
    value = user_message.strip()

    if not value:
        return None

    if field_name in ["first_name", "last_name"]:
        # Reject if the message has more than 3 words — it's likely conversational, not a name
        words = value.split()
        if len(words) > 3:
            return None
        # Take only the first word (the actual name) if multi-word
        name_part = words[0] if words else value
        cleaned = re.sub(r"[^a-zA-Z\-']", "", name_part)
        # Reject common conversational words
        if cleaned.lower() in {"yes", "no", "ok", "sure", "go", "back", "yeah", "nah", "hi", "hello", "hey"}:
            return None
        return cleaned or None

    if field_name == "dob":
        normalized_dob = normalize_dob(value)
        if normalized_dob and validate_dob(normalized_dob):
            return normalized_dob
        return None

    if field_name == "phone_number":
        digits = re.sub(r"\D", "", value)
        if len(digits) == 10:
            return digits
        return None

    if field_name == "email":
        normalized = value.strip().lower()
        if validate_email(normalized):
            return normalized
        return None

    return value


def apply_intake_field_to_session_update(field_name: str, field_value: str) -> Dict[str, Any]:
    if field_name in ["first_name", "last_name", "dob", "email", "phone_number"]:
        return {field_name: field_value}
    return {}


def continue_intake_flow(
    user_message: str,
    pending_field: str,
    collected_data: Dict[str, Any],
    session_dict: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    extracted_value = extract_field_value(pending_field, user_message)

    if not extracted_value:
        error_message = FIELD_VALIDATION_ERRORS.get(
            pending_field,
            f"I couldn’t understand that. {FIELD_PROMPTS[pending_field]}",
        )

        if pending_field == "dob" and looks_like_dob_missing_year(user_message):
            error_message = (
                "That date of birth looks incomplete. Please include the full year in YYYY-MM-DD format, "
                "for example 2000-01-30."
            )

        return False, {
            "state": "COLLECTING_INTAKE",
            "message": error_message,
            "metadata": {"pending_intake_field": pending_field},
            "session_updates": {},
            "collected_data": dict(collected_data),
        }

    updated_collected_data = dict(collected_data)
    updated_collected_data[pending_field] = extracted_value

    session_updates = apply_intake_field_to_session_update(pending_field, extracted_value)

    next_missing = get_missing_intake_field(updated_collected_data, {**session_dict, **session_updates})

    if next_missing:
        updated_collected_data["pending_intake_field"] = next_missing
        return True, {
            "state": "COLLECTING_INTAKE",
            "message": FIELD_PROMPTS[next_missing],
            "metadata": {"pending_intake_field": next_missing},
            "collected_data": updated_collected_data,
            "session_updates": session_updates,
        }

    updated_collected_data.pop("pending_intake_field", None)

    return True, {
        "state": "INTAKE_COMPLETE",
        "message": "Thank you. I now have your intake details.",
        "metadata": {},
        "collected_data": updated_collected_data,
        "session_updates": session_updates,
    }