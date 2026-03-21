from pydantic import BaseModel
from typing import Any, Optional


class VoiceHandoffRequest(BaseModel):
    session_id: str


class VoiceHandoffResponse(BaseModel):
    success: bool
    call_id: Optional[str] = None
    message: str


class VapiToolResult(BaseModel):
    name: str
    toolCallId: str
    result: str


class VapiWebhookResponse(BaseModel):
    results: Optional[list[VapiToolResult]] = None
    ok: bool = True


class SessionContextResponse(BaseModel):
    session_id: str
    workflow_type: Optional[str] = None
    state: Optional[str] = None
    collected_data: dict[str, Any] = {}
    missing_fields: list[str] = []