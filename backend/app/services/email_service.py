import requests
from app.core.config import settings


def send_booking_confirmation_email(
    to_email: str,
    first_name: str,
    last_name: str,
    dob: str,
    provider_name: str,
    specialty: str,
    body_part: str,
    booked_date: str,
    booked_time: str,
) -> bool:
    api_key = settings.resend_api_key
    from_email = settings.resend_from_email

    if not api_key:
        raise ValueError("RESEND_API_KEY is not configured")

    if not from_email:
        raise ValueError("RESEND_FROM_EMAIL is not configured")

    if not to_email:
        raise ValueError("Recipient email is missing")

    subject = "Your appointment is confirmed"

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px;">
      <h2 style="color: #16a34a; margin-bottom: 16px;">Appointment Confirmed</h2>

      <p>Hi {first_name},</p>
      <p>Your appointment has been successfully booked. Here are the details:</p>

      <h3 style="margin-top: 24px;">Patient Information</h3>
      <div style="background: #f1f5f9; border-radius: 10px; padding: 12px;">
        <p><strong>First Name:</strong> {first_name}</p>
        <p><strong>Last Name:</strong> {last_name}</p>
        <p><strong>Date of Birth:</strong> {dob}</p>
      </div>

      <h3 style="margin-top: 24px;">Appointment Details</h3>
      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px;">
        <p><strong>Provider:</strong> {provider_name}</p>
        <p><strong>Specialty:</strong> {specialty}</p>
        <p><strong>Concern:</strong> {body_part}</p>
        <p><strong>Date:</strong> {booked_date}</p>
        <p><strong>Time:</strong> {booked_time}</p>
      </div>

      <p style="margin-top: 20px;">If you need to reschedule or cancel, please contact the clinic.</p>
      <p style="margin-top: 24px;">Thanks,<br/>Elara Care Team</p>
    </div>
    """

    print("RESEND CONFIG CHECK", {
        "has_api_key": bool(api_key),
        "from_email": from_email,
        "to_email": to_email,
    })

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
        },
        timeout=15,
    )

    print("RESEND STATUS", response.status_code)
    print("RESEND BODY", response.text)

    # email_service.py — bottom of the function
    if response.status_code == 403:
        print("RESEND SANDBOX LIMIT - skipping", flush=True)
        return True  # fail silently, don't crash the app

    if response.status_code not in (200, 201):
        raise ValueError(f"Resend request failed: {response.status_code} {response.text}")

    return True