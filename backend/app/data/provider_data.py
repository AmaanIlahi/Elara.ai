from datetime import date, timedelta
from typing import Set

# Global set of booked slot keys — format: "provider_id|date|time"
# In-memory only; prevents double-booking within a single server process.
BOOKED_SLOTS: Set[str] = set()


def slot_key(provider_id: str, slot_date: str, slot_time: str) -> str:
    return f"{provider_id}|{slot_date}|{slot_time}"


def is_slot_booked(provider_id: str, slot_date: str, slot_time: str) -> bool:
    return slot_key(provider_id, slot_date, slot_time) in BOOKED_SLOTS


def mark_slot_booked(provider_id: str, slot_date: str, slot_time: str) -> None:
    BOOKED_SLOTS.add(slot_key(provider_id, slot_date, slot_time))


def generate_slots(start_days_from_today: int, weekdays: list[int], times: list[str], total_days: int = 45):
    slots = []
    today = date.today()

    for offset in range(start_days_from_today, total_days):
        current_day = today + timedelta(days=offset)
        if current_day.weekday() in weekdays:
            for time in times:
                slots.append(
                    {
                        "date": current_day.isoformat(),
                        "time": time,
                    }
                )
    return slots


PROVIDERS = [
    {
        "provider_id": "prov_ortho_1",
        "name": "Dr. Sarah Chen",
        "specialty": "Orthopedics",
        "body_parts": ["knee", "leg", "ankle"],
        "slots": generate_slots(
            start_days_from_today=1,
            weekdays=[0, 2, 4],  # Mon Wed Fri
            times=["09:00 AM", "11:00 AM", "02:00 PM"],
        ),
    },
    {
        "provider_id": "prov_spine_1",
        "name": "Dr. Michael Rivera",
        "specialty": "Spine Care",
        "body_parts": ["back", "neck", "spine"],
        "slots": generate_slots(
            start_days_from_today=1,
            weekdays=[1, 3],  # Tue Thu
            times=["10:00 AM", "01:00 PM", "03:30 PM"],
        ),
    },
    {
        "provider_id": "prov_sports_1",
        "name": "Dr. Emily Patel",
        "specialty": "Sports Medicine",
        "body_parts": ["shoulder", "arm", "elbow", "wrist"],
        "slots": generate_slots(
            start_days_from_today=1,
            weekdays=[0, 1, 3],  # Mon Tue Thu
            times=["08:30 AM", "12:00 PM", "04:00 PM"],
        ),
    },
    {
        "provider_id": "prov_derm_1",
        "name": "Dr. James Wilson",
        "specialty": "Dermatology",
        "body_parts": ["skin", "rash", "scalp"],
        "slots": generate_slots(
            start_days_from_today=1,
            weekdays=[2, 4],  # Wed Fri
            times=["09:30 AM", "01:30 PM"],
        ),
    },
]