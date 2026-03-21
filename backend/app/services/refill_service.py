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
            "message": "I can help with your refill request. Please share the medication name.",
            "workflow_type": "refill",
            "metadata": {},
        }

    if not pharmacy_name:
        return {
            "state": "REFILL_NEEDS_PHARMACY",
            "message": f"Got it. You need a refill for {medication_name}. Please share your preferred pharmacy name.",
            "workflow_type": "refill",
            "metadata": {
                "medication_name": medication_name,
            },
        }

    return {
        "state": "REFILL_READY_TO_SUBMIT",
        "message": (
            f"I have your refill request for {medication_name} to be sent to {pharmacy_name}. "
            f"Please confirm and submit the refill request."
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

def continue_refill_flow(user_message: str, collected_data: dict) -> Dict[str, Any]:
    medication_name = collected_data.get("medication_name")
    pharmacy_name = collected_data.get("pharmacy_name")

    if not medication_name:
        medication_name = user_message.strip()
        return {
            "state": "REFILL_NEEDS_PHARMACY",
            "message": f"Got it. You need a refill for {medication_name}. Please share your preferred pharmacy name.",
            "workflow_type": "refill",
            "metadata": {
                "medication_name": medication_name,
            },
        }

    if not pharmacy_name:
        pharmacy_name = user_message.strip()
        return {
            "state": "REFILL_READY_TO_SUBMIT",
            "message": (
                f"I have your refill request for {medication_name} to be sent to {pharmacy_name}. "
                f"Please confirm and submit the refill request."
            ),
            "workflow_type": "refill",
            "metadata": {
                "medication_name": medication_name,
                "pharmacy_name": pharmacy_name,
            },
        }

    return {
        "state": "REFILL_READY_TO_SUBMIT",
        "message": (
            f"I already have your refill request for {medication_name} to be sent to {pharmacy_name}. "
            f"You can now submit the refill request."
        ),
        "workflow_type": "refill",
        "metadata": {
            "medication_name": medication_name,
            "pharmacy_name": pharmacy_name,
        },
    }