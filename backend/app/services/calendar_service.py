"""Build an iCalendar (RFC 5545) file for a booked appointment using only the stdlib.

Times are written as local America/New_York times with a TZID and an embedded
VTIMEZONE, so no tz database is needed on the server (slim images and Windows
often have none) and calendar apps still place the event correctly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.data.practice_data import PRACTICE_INFO

TZID = "America/New_York"
APPOINTMENT_MINUTES = 30

# US rules since 2007: DST starts 2nd Sunday of March, ends 1st Sunday of November.
VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    f"TZID:{TZID}",
    "BEGIN:DAYLIGHT",
    "TZOFFSETFROM:-0500",
    "TZOFFSETTO:-0400",
    "TZNAME:EDT",
    "DTSTART:19700308T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD",
    "TZOFFSETFROM:-0400",
    "TZOFFSETTO:-0500",
    "TZNAME:EST",
    "DTSTART:19701101T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
    "END:STANDARD",
    "END:VTIMEZONE",
]


def is_booked(collected_data: Optional[Dict[str, Any]], state: Optional[str]) -> bool:
    data = collected_data or {}
    return state == "BOOKED" and bool(data.get("booking_confirmed")) and bool(data.get("booked_slot"))


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold to 75 octets per line (RFC 5545 3.1), never splitting a UTF-8 character."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts = []
    limit = 75
    while raw:
        chunk = raw[:limit]
        while True:
            try:
                text = chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = chunk[:-1]
        parts.append(text)
        raw = raw[len(chunk):]
        limit = 74  # continuation lines start with one space
    return "\r\n ".join(parts)


def parse_slot(slot: Dict[str, str]) -> datetime:
    """Slot date 'YYYY-MM-DD' + time '09:00 AM' -> naive local datetime."""
    return datetime.strptime(f"{slot['date']} {slot['time']}", "%Y-%m-%d %I:%M %p")


def build_ics(session_id: str, collected_data: Dict[str, Any], now: Optional[datetime] = None) -> str:
    slot = collected_data["booked_slot"]
    start = parse_slot(slot)
    end = start + timedelta(minutes=APPOINTMENT_MINUTES)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")

    provider = collected_data.get("provider_name") or "your provider"
    specialty = collected_data.get("specialty") or ""
    body_part = collected_data.get("body_part") or ""
    clinic = PRACTICE_INFO.get("name", "Elara Health Clinic")
    address = PRACTICE_INFO.get("address", "")
    phone = PRACTICE_INFO.get("phone", "")

    summary = f"Appointment with {provider}" + (f" ({specialty})" if specialty else "")
    description_lines = [f"Provider: {provider}"]
    if specialty:
        description_lines.append(f"Specialty: {specialty}")
    if body_part:
        description_lines.append(f"Concern: {body_part}")
    description_lines.append(f"Location: {clinic}, {address}")
    if phone:
        description_lines.append(f"Questions? Call {phone}")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Elara.ai//Appointments//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        *VTIMEZONE,
        "BEGIN:VEVENT",
        f"UID:{session_id}@elara.ai",
        f"DTSTAMP:{stamp}",
        f"DTSTART;TZID={TZID}:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID={TZID}:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(chr(10).join(description_lines))}",
        f"LOCATION:{_escape(f'{clinic}, {address}')}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
