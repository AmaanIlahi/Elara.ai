from fastapi.testclient import TestClient

from app.data.provider_data import BOOKED_SLOTS, PROVIDERS, is_slot_booked
from app.main import app
from app.services.scheduling_service import confirm_booking_from_session_data
from app.services.session_service import create_session, get_session, update_session

client = TestClient(app)
PROVIDER = PROVIDERS[0]


def _collected(slots=None):
    slots = slots if slots is not None else PROVIDER["slots"][:5]
    return {
        "provider_id": PROVIDER["provider_id"],
        "provider_name": PROVIDER["name"],
        "specialty": PROVIDER["specialty"],
        "body_part": "knee",
        "slots": slots,
    }


def test_first_booking_succeeds_and_marks_slot():
    data = _collected()
    ok, result = confirm_booking_from_session_data(data, 1)
    assert ok and result["state"] == "BOOKED"
    s = data["slots"][0]
    assert is_slot_booked(PROVIDER["provider_id"], s["date"], s["time"])


def test_second_booking_of_same_slot_is_a_conflict_with_remaining_slots():
    a, b = _collected(), _collected()
    assert confirm_booking_from_session_data(a, 1)[0] is True

    ok, result = confirm_booking_from_session_data(b, 1)
    assert ok is False
    assert result["state"] == "SCHEDULING_SHOWING_SLOTS"
    assert result["metadata"]["slot_conflict"] is True
    assert "just booked by someone else" in result["message"]

    taken = b["slots"][0]
    remaining = result["metadata"]["slots"]
    assert remaining, "should offer other slots"
    assert all((s["date"], s["time"]) != (taken["date"], taken["time"]) for s in remaining)
    assert len(BOOKED_SLOTS) == 1  # the loser did not book anything


def test_conflict_refills_from_provider_when_all_shown_slots_are_taken():
    shown = PROVIDER["slots"][:2]
    a = _collected(shown)
    confirm_booking_from_session_data(a, 1)
    confirm_booking_from_session_data(_collected(shown), 2)

    ok, result = confirm_booking_from_session_data(_collected(shown), 1)
    assert ok is False
    remaining = result["metadata"]["slots"]
    assert remaining and all(not is_slot_booked(PROVIDER["provider_id"], s["date"], s["time"]) for s in remaining)


def _confirming_session():
    session = create_session()
    data = _collected()
    data["pending_slot_choice"] = 1
    update_session(session.session_id, {
        "workflow_type": "scheduling",
        "state": "SCHEDULING_CONFIRMING",
        "collected_data": data,
    })
    return session.session_id


def test_chat_endpoint_second_patient_gets_conflict_and_quick_replies():
    first, second = _confirming_session(), _confirming_session()

    r1 = client.post("/api/v1/chat", json={"message": "Yes, please confirm", "session_id": first})
    assert r1.status_code == 200 and r1.json()["state"] == "BOOKED"

    r2 = client.post("/api/v1/chat", json={"message": "Yes, please confirm", "session_id": second})
    body = r2.json()
    assert r2.status_code == 200
    assert body["state"] == "SCHEDULING_SHOWING_SLOTS"
    assert "just booked by someone else" in body["message"]
    assert body["metadata"].get("booking_confirmed") is None
    assert body["quick_replies"], "remaining slots should come back as quick replies"
    # and the loser is not marked completed
    assert get_session(second).status == "in_progress"
