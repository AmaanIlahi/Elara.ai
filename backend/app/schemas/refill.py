from typing import Optional
from pydantic import BaseModel


class RefillSubmitRequest(BaseModel):
    session_id: str
    medication_name: str
    pharmacy_name: str
    pharmacy_phone: Optional[str] = None
    notes: Optional[str] = None