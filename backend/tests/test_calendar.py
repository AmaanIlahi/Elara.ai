from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.services import calendar_service
from app.services.session_service import create_session, update_session

client = TestClient(app)

BOOKED = {
    "provider_name": "Dr. Sarah Chen",
    "specialty": "Orthopedics",
    "body_part": "knee",
    "booked_slot": {"date": "2026-11-06", "time": "02:00 PM"},
    "booking_confirmed": True,
}


def _booked_session():
    s = create_session()
    update_session(s.session_id, {"state": "BOOKED", "status": "completed", "collected_data": dict(BOOKED)})
    return s.session_id


def _unfold(text: str) -> list[str]:
    return text.replace("\r\n ", "").split("\r\n")


def test_ics_for_booked_session():
    sid = _booked_session()
    r = client.get(f"/api/v1/appointments/{sid}/calendar.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "attachment" in r.headers["content-disposition"]

    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n") and body.endswith("END:VCALENDAR\r\n")
    lines = _unfold(body)
    assert "VERSION:2.0" in lines
    assert "BEGIN:VEVENT" in lines and "END:VEVENT" in lines
    assert f"UID:{sid}@elara.ai" in lines
    assert any(l.startswith("DTSTAMP:") and l.endswith("Z") for l in lines)
    assert "DTSTART;TZID=America/New_York:20261106T140000" in lines
    assert "DTEND;TZID=America/New_York:20261106T143000" in lines
    assert "TZID:America/New_York" in lines  # VTIMEZONE embedded, no tz database needed
    assert "SUMMARY:Appointment with Dr. Sarah Chen (Orthopedics)" in lines
    # address contains commas, which must be escaped in text values
    assert "LOCATION:Elara Health Clinic\\, 245 Park Avenue\\, New York\\, NY 10167" in lines
    assert any("Specialty: Orthopedics" in l for l in lines)


def test_ics_404_for_unknown_session():
    assert client.get("/api/v1/appointments/nope/calendar.ics").status_code == 404


def test_ics_404_for_session_not_booked():
    s = create_session()
    assert client.get(f"/api/v1/appointments/{s.session_id}/calendar.ics").status_code == 404

    update_session(s.session_id, {"state": "SCHEDULING_CONFIRMING", "collected_data": dict(BOOKED)})
    assert client.get(f"/api/v1/appointments/{s.session_id}/calendar.ics").status_code == 404


def test_long_lines_are_folded_to_75_octets():
    data = dict(BOOKED, provider_name="Dr. " + "Ünïcödé " * 20)
    text = calendar_service.build_ics("abc", data, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert "DTSTAMP:20260101T000000Z" in text
    for physical in text.split("\r\n"):
        assert len(physical.encode("utf-8")) <= 75
    # unfolding restores the full SUMMARY with no broken characters
    unfolded = _unfold(text)
    assert any(l.startswith("SUMMARY:Appointment with Dr. Ünïcödé") for l in unfolded)


def test_text_escaping():
    assert calendar_service._escape("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"


def test_booking_message_no_longer_promises_an_email():
    from app.services.scheduling_service import confirm_booking_from_session_data

    data = dict(BOOKED, slots=[BOOKED["booked_slot"]], provider_id="prov_ortho_1")
    ok, result = confirm_booking_from_session_data(data, 1)
    assert ok
    assert "email" not in result["message"].lower()
