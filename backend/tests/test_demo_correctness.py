from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data.provider_data import BOOKED_SLOTS, PROVIDERS
from app.main import app
from app.services.confirmation import classify_reply
from app.services.intake_service import extract_field_value, normalize_dob, validate_dob
from app.services.session_service import create_session, get_session, update_session

client = TestClient(app)


# --- date of birth -----------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("03/04/1990", "1990-03-04"),  # US order: March 4, not April 3
        ("3/4/1990", "1990-03-04"),
        ("12/25/1985", "1985-12-25"),
        ("03-04-1990", "1990-03-04"),
        ("25/12/1985", "1985-12-25"),  # only valid day-first, so the fallback is unambiguous
        ("25-12-1985", "1985-12-25"),
        ("1990-03-04", "1990-03-04"),
        ("July 30 1998", "1998-07-30"),
        ("30 July 1998", "1998-07-30"),
    ],
)
def test_dob_parsing_is_us_first(text, expected):
    assert extract_field_value("dob", text) == expected


def test_ambiguous_slash_date_never_flips_to_day_first():
    assert normalize_dob("01/02/2000") == "2000-01-02"
    assert normalize_dob("02/01/2000") == "2000-02-01"


def test_future_dob_rejected():
    tomorrow = date.today() + timedelta(days=1)
    assert extract_field_value("dob", tomorrow.strftime("%m/%d/%Y")) is None
    assert extract_field_value("dob", "01/01/2999") is None
    assert not validate_dob(tomorrow.isoformat())
    assert validate_dob(date.today().isoformat())


def test_age_over_120_rejected():
    today = date.today()
    just_ok = date(today.year - 120, today.month, 1)  # exactly 120 once the 1st has passed
    too_old = date(today.year - 121, today.month, 1)
    assert validate_dob(just_ok.isoformat())
    assert not validate_dob(too_old.isoformat())
    assert extract_field_value("dob", too_old.strftime("%m/%d/%Y")) is None


def test_age_120_boundary_uses_the_birthday():
    today = date(2026, 6, 15)
    assert validate_dob("1906-06-15", today=today)  # turns 120 today
    assert validate_dob("1906-06-14", today=today)  # 120
    assert validate_dob("1905-06-16", today=today)  # still 120: turns 121 tomorrow
    assert not validate_dob("1905-06-15", today=today)  # turned 121 today
    assert not validate_dob("1900-01-01", today=today)


def test_impossible_dates_rejected():
    assert extract_field_value("dob", "02/30/1990") is None
    assert extract_field_value("dob", "13/13/1990") is None
    assert extract_field_value("dob", "not a date") is None


# --- confirm / decline wording -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "yes", "Yes", "YES!", "yes please", "Yes, please confirm", "Yes, please submit", "yeah", "yep",
        "sure", "ok", "okay", "confirm", "go ahead", "yes go ahead", "book it", "correct", "that's right",
        "Yes, confirm it", "yes thanks", "sounds good", "of course",
    ],
)
def test_clear_yes(text):
    assert classify_reply(text) == "yes"


@pytest.mark.parametrize(
    "text",
    [
        "no", "No.", "nope", "cancel", "change", "go back", "No, I'd like a different slot",
        "No, I need to change the details", "different", "another one", "No, I’d like a different slot",
    ],
)
def test_clear_no(text):
    assert classify_reply(text) == "no"


@pytest.mark.parametrize(
    "text",
    [
        "not sure", "no thanks", "no thanks, yes", "yes and no", "yes but on friday", "maybe", "i guess",
        "hmm", "ok so what's the address", "sure, what time is that?", "not really", "nothing", "know",
        "okay no", "yes, I'd like a different slot", "yesterday", "booking", "notable", "okie", "",
        "   ", "what is this for", "please", "thanks",
    ],
)
def test_ambiguous_replies_are_neither(text):
    assert classify_reply(text) is None


def test_substrings_do_not_match():
    # The old code matched "no" inside "know" / "nothing" and "ok" inside "book".
    assert classify_reply("i know") is None
    assert classify_reply("nothing") is None
    assert classify_reply("bookmark") is None


# --- through the chat endpoint ----------------------------------------------

PROVIDER = PROVIDERS[0]


def _confirming_session(workflow="scheduling"):
    s = create_session()
    update_session(
        s.session_id,
        {
            "workflow_type": "scheduling",
            "state": "SCHEDULING_CONFIRMING",
            "collected_data": {
                "provider_id": PROVIDER["provider_id"],
                "provider_name": PROVIDER["name"],
                "specialty": PROVIDER["specialty"],
                "body_part": "knee",
                "slots": PROVIDER["slots"][:5],
                "pending_slot_choice": 1,
            },
        },
    )
    return s.session_id


def _say(sid, text):
    r = client.post("/api/v1/chat", json={"message": text, "session_id": sid})
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize("text", ["not sure", "no thanks", "no thanks, yes", "maybe", "ok what time is it?"])
def test_ambiguous_reply_never_books_or_cancels(text):
    sid = _confirming_session()
    body = _say(sid, text)
    assert body["state"] == "SCHEDULING_CONFIRMING"
    assert "Just to check" in body["message"]
    assert not BOOKED_SLOTS
    assert get_session(sid).collected_data.get("pending_slot_choice") == 1  # still pending, not cancelled


def test_yes_please_books():
    sid = _confirming_session()
    assert _say(sid, "yes please")["state"] == "BOOKED"
    assert len(BOOKED_SLOTS) == 1


def test_plain_no_goes_back_to_slots_without_booking():
    sid = _confirming_session()
    body = _say(sid, "no")
    assert body["state"] == "SCHEDULING_SHOWING_SLOTS"
    assert not BOOKED_SLOTS


def _refill_confirming_session():
    s = create_session()
    update_session(
        s.session_id,
        {
            "workflow_type": "refill",
            "state": "REFILL_CONFIRMING",
            "collected_data": {"medication_name": "Lisinopril", "pharmacy_name": "CVS"},
        },
    )
    return s.session_id


@pytest.mark.parametrize("text", ["not sure", "no thanks, yes", "ok but which pharmacy?"])
def test_refill_ambiguous_reply_does_not_submit(text):
    from app.data import refill_data

    before = len(refill_data.REFILL_REQUESTS) if hasattr(refill_data, "REFILL_REQUESTS") else 0
    sid = _refill_confirming_session()
    body = _say(sid, text)
    assert body["state"] == "REFILL_CONFIRMING"
    assert "Just to check" in body["message"]
    after = len(refill_data.REFILL_REQUESTS) if hasattr(refill_data, "REFILL_REQUESTS") else 0
    assert after == before


def test_refill_yes_submits_and_no_asks_for_pharmacy():
    assert _say(_refill_confirming_session(), "yes")["state"] == "REFILL_SUBMITTED"
    assert _say(_refill_confirming_session(), "no")["state"] == "REFILL_NEEDS_PHARMACY"
