# app/routes/email.py
from fastapi import APIRouter, HTTPException

from app.schemas.email import BookingEmailRequest
from app.services.session_service import get_session, update_session
from app.services.email_service import send_booking_confirmation_email

# print("EMAIL ROUTER MODULE LOADED", flush=True)

router = APIRouter(tags=["Email"])


@router.get("/ping")
async def ping():
    print("EMAIL PING HIT", flush=True)
    return {"ok": True}


@router.post("/send-confirmation-email")
async def send_confirmation_email(req: BookingEmailRequest):
    print("=== EMAIL ROUTE HIT ===", flush=True)
    print("REQUEST BODY:", req.dict(), flush=True)

    session = get_session(req.session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    collected_data = session.collected_data or {}

    email = collected_data.get("email") or session.email
    first_name = collected_data.get("first_name") or ""
    last_name = collected_data.get("last_name") or ""
    dob = collected_data.get("dob") or ""
    provider_name = collected_data.get("provider_name") or ""
    specialty = collected_data.get("specialty") or ""
    body_part = collected_data.get("body_part") or ""
    booked_slot = collected_data.get("booked_slot") or {}
    booking_confirmed = collected_data.get("booking_confirmed")
    confirmation_email_sent = collected_data.get("confirmation_email_sent", False)

    if confirmation_email_sent:
        return {"success": True, "message": "Confirmation email already sent."}

    if not booking_confirmed or not booked_slot:
        raise HTTPException(status_code=400, detail="Booking is not confirmed yet")

    if not email:
        raise HTTPException(status_code=400, detail="No email found in session")

    booked_date = booked_slot.get("date") or ""
    booked_time = booked_slot.get("time") or ""

    try:
        success = send_booking_confirmation_email(
            to_email=email,
            first_name=first_name,
            last_name=last_name,
            dob=dob,
            provider_name=provider_name,
            specialty=specialty,
            body_part=body_part,
            booked_date=booked_date,
            booked_time=booked_time,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Email send failed: {str(exc)}")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to send confirmation email")

    updated_collected_data = dict(collected_data)
    updated_collected_data["confirmation_email_sent"] = True
    update_session(session.session_id, {"collected_data": updated_collected_data})

    return {"success": True, "message": "Confirmation email sent successfully."}