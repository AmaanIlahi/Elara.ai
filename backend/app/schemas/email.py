from pydantic import BaseModel


class BookingEmailRequest(BaseModel):
    session_id: str