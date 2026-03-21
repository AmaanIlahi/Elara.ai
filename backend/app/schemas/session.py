from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    phone_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[str] = None
    email: Optional[str] = None
    workflow_type: Optional[str] = None
    state: str = "INIT"
    collected_data: Dict[str, Any] = Field(default_factory=dict)
    last_message: Optional[str] = None
    status: str = "in_progress"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)