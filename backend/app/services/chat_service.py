def detect_workflow(user_message: str) -> str:
    message = user_message.lower()

    services_keywords = [
        "what services", "what do you offer", "what can you treat", "what specialties",
        "list of doctors", "available doctors", "what doctors", "which doctors",
        "services do you", "services you provide", "services you offer",
        "what do you do", "what do you provide",
    ]

    scheduling_keywords = [
        "appointment", "schedule", "book", "visit", "doctor", "pain", "knee",
        "back", "shoulder", "neck", "arm", "leg", "injury", "consultation"
    ]

    refill_keywords = [
        "refill", "prescription", "pharmacy", "drug"
    ]

    practice_info_keywords = [
        "address", "location", "hours", "open", "close", "office", "phone", "contact"
    ]

    if any(kw in message for kw in services_keywords):
        return "services"

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


def get_services_overview() -> str:
    """Return a formatted list of all available providers and their specialties."""
    from app.data.provider_data import PROVIDERS

    lines = ["Here's what we currently offer at our practice:\n"]
    for p in PROVIDERS:
        body_parts = ", ".join(p["body_parts"])
        lines.append(f"• **{p['name']}** — {p['specialty']}\n  Treats: {body_parts}")
    lines.append(
        "\nI can also help with prescription refill requests and answer questions about our office. "
        "What would you like to do?"
    )
    return "\n".join(lines)