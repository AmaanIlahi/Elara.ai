from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    phone_number: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    workflow_type: Optional[str] = None
    state: str
    message: str
    next_step: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)