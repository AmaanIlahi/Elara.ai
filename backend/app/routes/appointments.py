from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.core.limiter import default_limit
from app.services.calendar_service import build_ics, is_booked
from app.services.session_service import get_session

router = APIRouter(tags=["Appointments"])


@router.get("/appointments/{session_id}/calendar.ics")
@default_limit
def appointment_calendar(session_id: str, request: Request):
    """iCalendar file for a booked appointment. 404 for unknown or not-yet-booked sessions."""
    session = get_session(session_id)
    if not session or not is_booked(session.collected_data, session.state):
        raise HTTPException(status_code=404, detail="No booked appointment for this session")

    return Response(
        content=build_ics(session.session_id, session.collected_data),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="elara-appointment.ics"'},
    )
