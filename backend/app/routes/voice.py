import json
import httpx

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.schemas.voice import VoiceHandoffRequest, VoiceHandoffResponse
from app.services.voice_prompt import build_vapi_assistant
from app.services.voice_tools import execute_voice_tool
from app.services.session_service import get_session

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/handoff", response_model=VoiceHandoffResponse)
async def handoff_to_phone(req: VoiceHandoffRequest):
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not settings.vapi_api_key:
        raise HTTPException(status_code=500, detail="Vapi API key is not configured")

    if not settings.vapi_phone_number_id:
        raise HTTPException(status_code=500, detail="Vapi phone number ID is not configured")

    collected = session.collected_data or {}
    phone_number = collected.get("phone_number") or session.phone_number
    if not phone_number:
        raise HTTPException(status_code=400, detail="No phone number found in session")

    assistant = build_vapi_assistant(session)

    payload = {
        "customer": {
            "number": "+1"+phone_number
        },
        "phoneNumberId": settings.vapi_phone_number_id,
        "assistant": assistant,
        "metadata": {
            "session_id": session.session_id
        }
    }

    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }

    # print("\nPayload:")
    # print(json.dumps(payload, indent=2))

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.vapi.ai/call",
            headers=headers,
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=response.text)

    data = response.json()

    return VoiceHandoffResponse(
        success=True,
        call_id=data.get("id"),
        message="Phone handoff started successfully.",
    )


@router.post("/webhook")
async def vapi_webhook(request: Request):
    payload = await request.json()
    message = payload.get("message", {})
    message_type = message.get("type")

    if message_type == "tool-calls":
        tool_calls = message.get("toolCallList", [])
        results = []

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_call_id = tool_call.get("id")
            params = tool_call.get("parameters", {}) or {}

            # Ensure session_id is always available to the tool
            if "session_id" not in params:
                call = message.get("call", {}) or {}
                metadata = call.get("metadata", {}) or payload.get("metadata", {}) or {}
                session_id = metadata.get("session_id")
                if session_id:
                    params["session_id"] = session_id

            try:
                result = await execute_voice_tool(tool_name, params)
                results.append({
                    "toolCallId": tool_call_id,
                    "name": tool_name,
                    "result": json.dumps(result),
                })
            except Exception as exc:
                results.append({
                    "toolCallId": tool_call_id,
                    "name": tool_name,
                    "result": json.dumps({
                        "success": False,
                        "error": str(exc),
                    }),
                })

        return JSONResponse({"results": results})

    # Useful lifecycle hooks to keep for debugging / future sync
    if message_type in {"status-update", "end-of-call-report", "assistant-request", "transcript"}:
        return JSONResponse({"ok": True})

    return JSONResponse({"ok": True})