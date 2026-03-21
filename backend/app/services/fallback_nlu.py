# app/services/fallback_nlu.py

from app.services.llm_service import LLMExtractionResult


def fallback_extract(user_message: str) -> LLMExtractionResult:
    text = user_message.lower()

    intent = "unknown"
    if any(x in text for x in ["appointment", "schedule", "book", "see a doctor", "see someone"]):
        intent = "schedule"
    elif any(x in text for x in ["refill", "renew", "medication", "medicine", "prescription"]):
        intent = "refill"
    elif any(x in text for x in ["hours", "open", "address", "location", "phone", "office"]):
        intent = "practice_info"

    practice_info_topic = None
    if "hours" in text or "open" in text:
        practice_info_topic = "hours"
    elif "address" in text or "location" in text:
        practice_info_topic = "address"
    elif "phone" in text or "call" in text:
        practice_info_topic = "phone"
    elif "office" in text:
        practice_info_topic = "general"

    body_parts = [
        "knee", "shoulder", "back", "neck", "hip", "ankle",
        "wrist", "elbow", "skin", "eye", "ear", "throat", "foot"
    ]
    found_body_part = next((bp for bp in body_parts if bp in text), None)

    time_pref = None
    if "morning" in text:
        time_pref = "morning"
    elif "afternoon" in text:
        time_pref = "afternoon"
    elif "evening" in text:
        time_pref = "evening"

    return LLMExtractionResult(
        intent=intent,
        body_part=found_body_part,
        reason=user_message[:120],
        requested_time_pref=time_pref,
        practice_info_topic=practice_info_topic,
        confidence=0.35,
    )