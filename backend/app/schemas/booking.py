from pydantic import BaseModel


class BookingRequest(BaseModel):
    session_id: str
    slot_choice: int