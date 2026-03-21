from app.data.practice_data import PRACTICE_INFO


def get_full_practice_info() -> dict:
    return PRACTICE_INFO


def answer_practice_question(user_message: str) -> str:
    message = user_message.lower()

    if any(word in message for word in ["hour", "open", "close", "timing", "time"]):
        hours = PRACTICE_INFO["hours"]
        hours_text = (
            f"Office hours are: Monday {hours['monday']}, Tuesday {hours['tuesday']}, "
            f"Wednesday {hours['wednesday']}, Thursday {hours['thursday']}, "
            f"Friday {hours['friday']}, Saturday {hours['saturday']}, "
            f"and Sunday {hours['sunday']}."
        )
        return hours_text

    if any(word in message for word in ["address", "location", "located", "where"]):
        return f"Our office is located at {PRACTICE_INFO['address']}."

    if any(word in message for word in ["phone", "call", "contact", "number"]):
        return (
            f"You can reach our office at {PRACTICE_INFO['phone']} "
            f"or email us at {PRACTICE_INFO['email']}."
        )

    return (
        f"{PRACTICE_INFO['name']} is located at {PRACTICE_INFO['address']}. "
        f"You can call us at {PRACTICE_INFO['phone']}."
    )