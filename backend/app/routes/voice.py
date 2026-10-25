import hmac
import json
import httpx

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.limiter import limiter
from app.schemas.voice import VoiceHandoffRequest, VoiceHandoffResponse
from app.services.voice_prompt import build_vapi_assistant
from app.services.voice_tools import execute_voice_tool
from app.services.intake_service import normalize_us_phone
from app.services.session_service import get_session, update_session

WEBHOOK_SECRET_HEADER = "x-vapi-secret"

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/handoff", response_model=VoiceHandoffResponse)
@limiter.limit("3/hour")
async def handoff_to_phone(req: VoiceHandoffRequest, request: Request):
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not settings.vapi_api_key:
        raise HTTPException(status_code=500, detail="Vapi API key is not configured")

    if not settings.vapi_phone_number_id:
        raise HTTPException(status_code=500, detail="Vapi phone number ID is not configured")

    if not settings.vapi_webhook_secret:
        raise HTTPException(status_code=500, detail="Vapi webhook secret is not configured")

    collected = session.collected_data or {}
    raw_phone = collected.get("phone_number") or session.phone_number
    if not raw_phone:
        raise HTTPException(
            status_code=400,
            detail="I need your phone number before I can connect you — please complete the intake first."
        )

    phone_number = normalize_us_phone(raw_phone)
    if not phone_number:
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a valid 10-digit US phone number, so I can't place the call. Please start a new chat and enter it again.",
        )

    # At most one outbound call per session. Claim it before the network call so a
    # double-click or a retry cannot place a second call.
    if session.voice_call_started:
        raise HTTPException(
            status_code=409,
            detail="A call was already started for this chat. Please pick up your phone, or start a new chat to request another call.",
        )
    update_session(session.session_id, {"voice_call_started": True})

    assistant = build_vapi_assistant(session)

    payload = {
        "customer": {
            "number": "+1" + phone_number
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

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.vapi.ai/call",
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError:
        # The request may or may not have reached VAPI, so keep the claim: a
        # duplicate call is worse than asking the patient to start a new chat.
        raise HTTPException(
            status_code=502,
            detail="I couldn't reach the phone service. If your phone doesn't ring shortly, please start a new chat and try again.",
        )

    if response.status_code >= 400:
        # VAPI rejected it, so no call exists. Release the claim so the patient can retry.
        update_session(session.session_id, {"voice_call_started": False})
        raise HTTPException(
            status_code=502,
            detail="The phone service couldn't start the call right now. Please try again in a moment.",
        )

    data = response.json()

    return VoiceHandoffResponse(
        success=True,
        call_id=data.get("id"),
        message="Phone handoff started successfully.",
    )


def _webhook_secret_valid(request: Request) -> bool:
    expected = settings.vapi_webhook_secret
    provided = request.headers.get(WEBHOOK_SECRET_HEADER)
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


@router.post("/webhook")
@limiter.exempt
async def vapi_webhook(request: Request):
    # Fail closed: with no secret configured, nothing is accepted.
    if not _webhook_secret_valid(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

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