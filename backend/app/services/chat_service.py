def detect_workflow(user_message: str) -> str:
    message = user_message.lower()

    scheduling_keywords = [
        "appointment", "schedule", "book", "visit", "doctor", "pain", "knee",
        "back", "shoulder", "neck", "arm", "leg", "injury", "consultation"
    ]

    refill_keywords = [
        "refill", "prescription", "medicine", "medication", "pharmacy", "drug"
    ]

    practice_info_keywords = [
        "address", "location", "hours", "open", "close", "office", "phone", "contact"
    ]

    if any(keyword in message for keyword in refill_keywords):
        return "refill"

    if any(keyword in message for keyword in practice_info_keywords):
        return "practice_info"

    if any(keyword in message for keyword in scheduling_keywords):
        return "scheduling"

    return "unknown"


def get_workflow_response(workflow_type: str) -> tuple[str, str]:
    if workflow_type == "scheduling":
        return (
            "SCHEDULING_STARTED",
            "Sure, I can help you schedule an appointment. May I know the reason for your visit or which body part needs attention?"
        )

    if workflow_type == "refill":
        return (
            "REFILL_STARTED",
            "I can help with your prescription refill request. Please share the medication name and your preferred pharmacy."
        )

    if workflow_type == "practice_info":
        return (
            "PRACTICE_INFO_STARTED",
            "I can help with practice information. Ask me about office hours, location, or contact details."
        )

    return (
        "GENERAL_CONVERSATION",
        "I can help with appointments, prescription refills, or practice information. How can I assist you today?"
    )