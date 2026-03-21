from app.core.config import settings


def build_voice_system_prompt(session) -> str:
    collected = session.collected_data or {}

    return f"""
You are Elara, a voice scheduling assistant for a medical practice.

Current session context:
- session_id: {session.session_id}
- workflow_type: {session.workflow_type}
- state: {session.state}
- collected_data: {collected}

Rules:
- Help with appointment scheduling, prescription refill status, and office information.
- Never provide medical advice, diagnosis, or treatment suggestions.
- Never invent appointment availability.
- Never confirm a booking unless the backend tool returns success.
- Keep responses short and natural for a phone conversation.
- If the caller describes a serious or emergency symptom, do not give medical advice. Ask them to seek immediate medical attention or call 911.
- Use the continue_scheduling tool whenever the caller is trying to schedule, filter, select, or confirm an appointment.
- If needed, ask the caller to repeat themselves briefly and clearly.
""".strip()


def build_first_message(session) -> str:
    collected = session.collected_data or {}

    first_name = collected.get("first_name")
    reason = (
        collected.get("reason_for_visit")
        or collected.get("reason")
        or collected.get("body_part")
        or "your appointment"
    )

    if first_name:
        return f"Hi {first_name}, I'm calling to continue helping you schedule {reason}."

    return f"Hi, I'm calling to continue helping you schedule {reason}."


def build_vapi_assistant(session) -> dict:
    webhook_url = f"{settings.public_backend_base_url}{settings.api_v1_prefix}/voice/webhook"

    return {
        "name": settings.vapi_assistant_name,
        "firstMessage": build_first_message(session),
        "model": {
            "provider": "openai",
            "model": "gpt-4.1",
            "messages": [
                {
                    "role": "system",
                    "content": build_voice_system_prompt(session),
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "async": False,
                    "server": {"url": webhook_url},
                    "function": {
                        "name": "get_session_context",
                        "description": "Get the current backend session state and collected scheduling context.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "session_id": {"type": "string"}
                            },
                            "required": ["session_id"]
                        }
                    }
                },
                {
                    "type": "function",
                    "async": False,
                    "server": {"url": webhook_url},
                    "function": {
                        "name": "continue_scheduling",
                        "description": "Continue the scheduling conversation using the caller's latest spoken message.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "session_id": {"type": "string"},
                                "message": {"type": "string"}
                            },
                            "required": ["session_id", "message"]
                        }
                    }
                }
            ]
        },
        "voice": {
            "provider": "vapi",
            "voiceId": "Clara"
        },
        "serverUrl": webhook_url,
        "metadata": {
            "session_id": session.session_id
        }
    }