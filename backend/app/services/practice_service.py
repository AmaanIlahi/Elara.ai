from app.data.practice_data import PRACTICE_INFO


def get_full_practice_info() -> dict:
    return PRACTICE_INFO


def answer_practice_question(user_message: str) -> str:
    message = user_message.lower()

    follow_up = "\n\nIs there anything else I can help you with — like scheduling an appointment or requesting a refill?"

    if any(word in message for word in ["hour", "open", "close", "timing", "time"]):
        hours = PRACTICE_INFO["hours"]
        weekday_hours = (
            f"Monday through Friday, we're open 9:00 AM – 5:00 PM, "
            f"and Saturdays from 10:00 AM – 2:00 PM. "
            f"We're closed on Sundays."
        )
        return (
            f"Great question! Here are our office hours:\n\n"
            f"{weekday_hours}"
            f"{follow_up}"
        )

    if any(word in message for word in ["address", "location", "located", "where", "find", "directions"]):
        return (
            f"You can find us at **{PRACTICE_INFO['address']}**. "
            f"If you need directions or have trouble finding us, feel free to give us a call and we'll help you out."
            f"{follow_up}"
        )

    if any(word in message for word in ["phone", "call", "contact", "number", "reach"]):
        return (
            f"You're welcome to reach us at **{PRACTICE_INFO['phone']}** — our team is happy to help. "
            f"You can also email us at **{PRACTICE_INFO['email']}** if that's easier for you."
            f"{follow_up}"
        )

    if any(word in message for word in ["email", "mail"]):
        return (
            f"You can email us at **{PRACTICE_INFO['email']}** and we'll get back to you as soon as possible. "
            f"For urgent matters, give us a call at **{PRACTICE_INFO['phone']}**."
            f"{follow_up}"
        )

    return (
        f"**{PRACTICE_INFO['name']}** is conveniently located at {PRACTICE_INFO['address']}. "
        f"We're open Monday–Friday 9:00 AM–5:00 PM and Saturdays 10:00 AM–2:00 PM. "
        f"Feel free to call us at {PRACTICE_INFO['phone']} or email {PRACTICE_INFO['email']} — we'd love to hear from you."
        f"{follow_up}"
    )
