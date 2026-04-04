from typing import Dict, Any, Optional
from uuid import uuid4
from datetime import datetime

from app.data.refill_data import REFILL_REQUESTS


def extract_refill_details(user_message: str) -> Dict[str, Optional[str]]:
    message = user_message.strip()

    medication_name = None
    pharmacy_name = None

    lowered = message.lower()

    trigger_phrases = [
        "refill for",
        "refill my",
        "prescription for",
        "medication for",
    ]

    for phrase in trigger_phrases:
        if phrase in lowered:
            start_idx = lowered.find(phrase) + len(phrase)
            medication_name = message[start_idx:].strip(" .")
            break

    pharmacy_markers = ["at", "to", "from"]
    for marker in pharmacy_markers:
        token = f" {marker} "
        if token in lowered and medication_name:
            med_part, pharmacy_part = message.split(marker, 1)
            pharmacy_name = pharmacy_part.strip(" .")
            med_lower = med_part.lower()

            for phrase in trigger_phrases:
                if phrase in med_lower:
                    med_start = med_lower.find(phrase) + len(phrase)
                    medication_name = med_part[med_start:].strip(" .")
                    break
            break

    return {
        "medication_name": medication_name,
        "pharmacy_name": pharmacy_name,
    }


def build_refill_response(user_message: str) -> Dict[str, Any]:
    details = extract_refill_details(user_message)

    medication_name = details.get("medication_name")
    pharmacy_name = details.get("pharmacy_name")

    if not medication_name:
        return {
            "state": "REFILL_NEEDS_MEDICATION",
            "message": (
                "Of course, I can help get that sorted for you! "
                "Which medication would you like a refill for?"
            ),
            "workflow_type": "refill",
            "metadata": {},
        }

    if not pharmacy_name:
        return {
            "state": "REFILL_NEEDS_PHARMACY",
            "message": (
                f"Got it — a refill for {medication_name}. "
                f"Which pharmacy would you like it sent to?"
            ),
            "workflow_type": "refill",
            "metadata": {"medication_name": medication_name},
        }

    return {
        "state": "REFILL_CONFIRMING",
        "message": (
            f"Just to confirm — you'd like a refill for **{medication_name}** "
            f"sent to **{pharmacy_name}**. Shall I go ahead and submit this request?"
        ),
        "workflow_type": "refill",
        "metadata": {
            "medication_name": medication_name,
            "pharmacy_name": pharmacy_name,
        },
    }


def submit_refill_request(
    session_id: str,
    medication_name: str,
    pharmacy_name: str,
    pharmacy_phone: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    refill_request = {
        "refill_request_id": str(uuid4()),
        "session_id": session_id,
        "medication_name": medication_name,
        "pharmacy_name": pharmacy_name,
        "pharmacy_phone": pharmacy_phone,
        "notes": notes,
        "status": "submitted",
        "created_at": datetime.utcnow().isoformat(),
    }

    REFILL_REQUESTS.append(refill_request)
    return refill_request


_MEDICAL_ADVICE_PHRASES = [
    "recommend", "suggest", "what should i take", "what medicine", "what medication",
    "which medicine", "which drug", "what drug", "can you prescribe", "what tablet",
    "what pill", "advise me", "what to take",
]

_NEGATION_PHRASES = [
    "not a refill", "no refill", "don't need a refill", "don't want a refill",
    "isn't a refill", "is not a refill",
]


def _looks_like_medical_advice_request(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _MEDICAL_ADVICE_PHRASES)


def _looks_like_valid_medication_name(text: str) -> bool:
    """Reject multi-sentence or clearly conversational strings as medication names."""
    words = text.strip().split()
    # Real medication names are short; reject anything over 5 words
    if len(words) > 5:
        return False
    # Reject if it contains negation phrases
    lowered = text.lower()
    if any(phrase in lowered for phrase in _NEGATION_PHRASES):
        return False
    return True


def _looks_like_valid_pharmacy_name(text: str) -> bool:
    """Reject clearly conversational strings as pharmacy names."""
    words = text.strip().split()
    if len(words) > 6:
        return False
    lowered = text.lower()
    if any(phrase in lowered for phrase in _NEGATION_PHRASES):
        return False
    return True


def continue_refill_flow(user_message: str, collected_data: dict) -> Dict[str, Any]:
    medication_name = collected_data.get("medication_name")
    pharmacy_name = collected_data.get("pharmacy_name")

    if not medication_name:
        # Guard: user asking for medical advice instead of a refill
        if _looks_like_medical_advice_request(user_message):
            return {
                "state": "GENERAL_CONVERSATION",
                "message": (
                    "I'm not able to recommend or prescribe medications — that's something only "
                    "your doctor can do. However, I'd be happy to help you schedule an appointment "
                    "with one of our providers. Would you like to do that?"
                ),
                "workflow_type": "unknown",
                "metadata": {},
            }

        if not _looks_like_valid_medication_name(user_message):
            return {
                "state": "REFILL_NEEDS_MEDICATION",
                "message": (
                    "I want to make sure I get the right medication for you. "
                    "Could you just share the name of the medication you need refilled? "
                    "(For example: \"Lisinopril\" or \"Metformin\")"
                ),
                "workflow_type": "refill",
                "metadata": {},
            }

        medication_name = user_message.strip()
        return {
            "state": "REFILL_NEEDS_PHARMACY",
            "message": (
                f"Got it — a refill for {medication_name}. "
                f"Which pharmacy would you like it sent to?"
            ),
            "workflow_type": "refill",
            "metadata": {"medication_name": medication_name},
        }

    if not pharmacy_name:
        if not _looks_like_valid_pharmacy_name(user_message):
            return {
                "state": "REFILL_NEEDS_PHARMACY",
                "message": (
                    f"I didn't quite catch that. Which pharmacy should I send the {medication_name} "
                    f"refill to? (For example: \"CVS\" or \"Walgreens on 5th Ave\")"
                ),
                "workflow_type": "refill",
                "metadata": {"medication_name": medication_name},
            }

        pharmacy_name = user_message.strip()
        return {
            "state": "REFILL_CONFIRMING",
            "message": (
                f"Perfect! Just to confirm — you'd like a refill for **{medication_name}** "
                f"sent to **{pharmacy_name}**. Shall I go ahead and submit this?"
            ),
            "workflow_type": "refill",
            "metadata": {
                "medication_name": medication_name,
                "pharmacy_name": pharmacy_name,
            },
        }

    return {
        "state": "REFILL_CONFIRMING",
        "message": (
            f"Just to double-check — you'd like a refill for **{medication_name}** "
            f"sent to **{pharmacy_name}**. Want me to go ahead and submit this?"
        ),
        "workflow_type": "refill",
        "metadata": {
            "medication_name": medication_name,
            "pharmacy_name": pharmacy_name,
        },
    }
