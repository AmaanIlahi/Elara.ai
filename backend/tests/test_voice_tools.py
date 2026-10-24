from app.services.session_service import create_session, get_session, update_session
from app.services.voice_tools import execute_voice_tool

PATIENT = {
    "first_name": "Ann",
    "last_name": "Lee",
    "dob": "1990-05-01",
    "phone_number": "2125550100",
    "email": "ann@example.com",
    "history": [{"role": "user", "content": "hi"}],
}


def _session_with_patient(**extra):
    session = create_session()
    update_session(session.session_id, {"collected_data": {**PATIENT, **extra}})
    return session.session_id


def _assert_patient_kept(session_id):
    data = get_session(session_id).collected_data
    for key, value in PATIENT.items():
        assert data[key] == value, f"{key} was lost"
    return data


async def test_start_scheduling_keeps_patient_data():
    sid = _session_with_patient()
    out = await execute_voice_tool("continue_scheduling", {"session_id": sid, "message": "my knee hurts"})
    assert out["success"] is True
    data = _assert_patient_kept(sid)
    assert data["slots"] and data["provider_name"]  # new metadata merged in


async def test_slot_preference_keeps_patient_data():
    sid = _session_with_patient()
    await execute_voice_tool("continue_scheduling", {"session_id": sid, "message": "my knee hurts"})
    slots = get_session(sid).collected_data["slots"]
    weekday = __import__("datetime").datetime.strptime(slots[0]["date"], "%Y-%m-%d").strftime("%A")

    out = await execute_voice_tool("continue_scheduling", {"session_id": sid, "message": f"how about {weekday}"})
    assert out["success"] is True
    data = _assert_patient_kept(sid)
    assert data["provider_name"] and data["slots"]


async def test_slot_selection_keeps_patient_data():
    sid = _session_with_patient()
    await execute_voice_tool("continue_scheduling", {"session_id": sid, "message": "my knee hurts"})
    out = await execute_voice_tool("continue_scheduling", {"session_id": sid, "message": "1"})
    assert out["success"] is True
    data = _assert_patient_kept(sid)
    assert data["booking_confirmed"] is True
    assert data["booked_slot"]


async def test_get_session_context_unchanged():
    sid = _session_with_patient()
    out = await execute_voice_tool("get_session_context", {"session_id": sid})
    assert out["collected_data"]["first_name"] == "Ann"
