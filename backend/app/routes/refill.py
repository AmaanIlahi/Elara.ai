from fastapi import APIRouter, HTTPException

from app.schemas.refill import RefillSubmitRequest
from app.services.intake_service import get_missing_intake_field
from app.services.refill_service import submit_refill_request
from app.services.session_service import get_session, update_session

router = APIRouter(tags=["Refill"])


@router.post("/refill/submit")
def submit_refill(request: RefillSubmitRequest):
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
            request.session_id,
            {
                "state": "COLLECTING_INTAKE",
                "collected_data": updated_collected_data,
            },
        )

        return {
            "session_id": updated_session.session_id,
            "workflow_type": updated_session.workflow_type,
            "state": updated_session.state,
            "message": f"Before I submit your refill request, I need a few details. {missing_field.replace('_', ' ').title()} please.",
            "metadata": {"pending_intake_field": missing_field},
        }

    refill_request = submit_refill_request(
        session_id=request.session_id,
        medication_name=request.medication_name,
        pharmacy_name=request.pharmacy_name,
        pharmacy_phone=request.pharmacy_phone,
        notes=request.notes,
    )

    updated_collected_data = dict(session.collected_data)
    updated_collected_data.update(
        {
            "medication_name": request.medication_name,
            "pharmacy_name": request.pharmacy_name,
            "pharmacy_phone": request.pharmacy_phone,
            "refill_request_id": refill_request["refill_request_id"],
        }
    )

    updated_session = update_session(
        request.session_id,
        {
            "state": "REFILL_SUBMITTED",
            "status": "completed",
            "collected_data": updated_collected_data,
        },
    )

    return {
        "session_id": updated_session.session_id,
        "workflow_type": updated_session.workflow_type,
        "state": updated_session.state,
        "message": f"Your refill request for {request.medication_name} has been submitted to {request.pharmacy_name}.",
        "metadata": {
            "refill_request_id": refill_request["refill_request_id"],
            "medication_name": request.medication_name,
            "pharmacy_name": request.pharmacy_name,
            "pharmacy_phone": request.pharmacy_phone,
        },
    }