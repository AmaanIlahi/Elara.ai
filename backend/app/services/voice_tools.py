from typing import Any

from app.services.session_service import get_session, update_session
from app.services.scheduling_service import (
    build_scheduling_response,
    resolve_slot_preference,
    parse_slot_choice,
    confirm_booking_from_session_data,
)


async def execute_voice_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    session_id = params.get("session_id")
    if not session_id:
        raise ValueError("session_id is required")

    session = get_session(session_id)
    if not session:
        raise ValueError("Session not found")

    user_message = params.get("message", "")

    # 🔹 1. Get current session state
    if tool_name == "get_session_context":
        return {
            "success": True,
            "session_id": session.session_id,
            "state": session.state,
            "collected_data": session.collected_data or {},
        }

    # 🔹 2. Continue scheduling flow using SAME logic as chat
    if tool_name == "continue_scheduling":

        # STEP 1: If no slots yet → start scheduling
        if not session.collected_data.get("slots"):
            response = build_scheduling_response(user_message)

            update_session(session.session_id, {
                "state": response["state"],
                "workflow_type": response.get("workflow_type"),
                "collected_data": response.get("metadata", {}),
            })

            return {
                "success": True,
                "response": response["message"],
                "state": response["state"],
                "metadata": response.get("metadata"),
            }

        # STEP 2: Try filtering (Monday / 15th etc)
        preference_result = resolve_slot_preference(
            user_message,
            session.collected_data.get("slots", []),
            session.collected_data.get("provider_name"),
            session.collected_data.get("specialty"),
            session.collected_data.get("body_part"),
        )

        if preference_result:
            update_session(session.session_id, {
                "state": preference_result["state"],
                "collected_data": preference_result.get("metadata", {}),
            })

            return {
                "success": True,
                "response": preference_result["message"],
                "state": preference_result["state"],
                "metadata": preference_result.get("metadata"),
            }

        # STEP 3: Try selecting slot (1, 2, etc)
        slot_choice = parse_slot_choice(user_message)

        if slot_choice:
            success, result = confirm_booking_from_session_data(
                session.collected_data,
                slot_choice
            )

            if success:
                update_session(session.session_id, {
                    "state": result["state"],
                    "collected_data": result.get("metadata", {}),
                })

                return {
                    "success": True,
                    "response": result["message"],
                    "state": result["state"],
                    "metadata": result.get("metadata"),
                }

            return {
                "success": False,
                "response": result["message"],
                "state": result["state"],
            }

        # STEP 4: fallback
        return {
            "success": False,
            "response": "I didn’t quite understand that. Could you repeat your preference?",
        }

    raise ValueError(f"Unsupported tool: {tool_name}")