from fastapi import APIRouter, HTTPException

from app.schemas.booking import BookingRequest
from app.services.intake_service import get_missing_intake_field
from app.services.session_service import get_session, update_session
from app.services.scheduling_service import confirm_booking_from_session_data

router = APIRouter(tags=["Booking"])


@router.post("/scheduling/book")
def book_appointment(request: BookingRequest):
    session = get_session(request.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    missing_field = get_missing_intake_field(
        session.collected_data,
        {
            "first_name": session.first_name,
            "last_name": session.last_name,
            "dob": session.dob,
            "phone_number": session.phone_number,
            "email": session.email,
        },
    )

    if missing_field:
        updated_collected_data = dict(session.collected_data)
        updated_collected_data["pending_intake_field"] = missing_field

        updated_session = update_session(
            session.session_id,
            {
                "state": "COLLECTING_INTAKE",
                "collected_data": updated_collected_data,
            },
        )

        return {
            "session_id": updated_session.session_id,
            "workflow_type": updated_session.workflow_type,
            "state": updated_session.state,
            "message": f"Before I confirm your appointment, I need a few details. {missing_field.replace('_', ' ').title()} please.",
            "metadata": {"pending_intake_field": missing_field},
        }

    success, result = confirm_booking_from_session_data(
        session.collected_data,
        request.slot_choice,
    )

    if not success:
        return {
            "session_id": session.session_id,
            "workflow_type": session.workflow_type,
            "state": result["state"],
            "message": result["message"],
            "metadata": result["metadata"],
        }

    updated_collected_data = dict(session.collected_data)
    updated_collected_data.update(result["metadata"])

    updated_session = update_session(
        session.session_id,
        {
            "state": result["state"],
            "status": "completed",
            "collected_data": updated_collected_data,
        },
    )

    return {
        "session_id": updated_session.session_id,
        "workflow_type": updated_session.workflow_type,
        "state": updated_session.state,
        "message": result["message"],
        "metadata": result["metadata"],
    }