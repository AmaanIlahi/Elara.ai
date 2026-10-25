import json

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import settings
from app.core.limiter import client_key
from app.main import app
from app.services.intake_service import normalize_us_phone
from app.services.session_service import create_session, update_session

client = TestClient(app)


def _request(headers: dict, client_host: str = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 1234),
    }
    return Request(scope)


# --- rate-limit keying -------------------------------------------------------


def test_client_key_prefers_fly_client_ip():
    assert client_key(_request({"Fly-Client-IP": "203.0.113.7"})) == "203.0.113.7"


def test_client_key_falls_back_to_socket_address():
    assert client_key(_request({}, client_host="198.51.100.9")) == "198.51.100.9"
    assert client_key(_request({"Fly-Client-IP": "  "}, client_host="198.51.100.9")) == "198.51.100.9"


def test_chat_limit_is_per_fly_client_ip():
    a = {"Fly-Client-IP": "203.0.113.1"}
    b = {"Fly-Client-IP": "203.0.113.2"}

    for _ in range(20):
        assert client.post("/api/v1/chat", json={"message": "hi"}, headers=a).status_code == 200

    # Same socket address (TestClient) but a different Fly-Client-IP has its own bucket.
    assert client.post("/api/v1/chat", json={"message": "hi"}, headers=a).status_code == 429
    assert client.post("/api/v1/chat", json={"message": "hi"}, headers=b).status_code == 200


def test_default_limit_applies_to_routes_without_their_own():
    h = {"Fly-Client-IP": "203.0.113.3"}
    codes = [client.get("/api/v1/practice/info", headers=h).status_code for _ in range(61)]
    assert codes[:60] == [200] * 60
    assert codes[60] == 429


def test_health_is_exempt_from_limits():
    h = {"Fly-Client-IP": "203.0.113.4"}
    assert all(client.get("/api/v1/health", headers=h).status_code == 200 for _ in range(70))


def test_voice_handoff_limited_to_3_per_hour_per_client():
    h = {"Fly-Client-IP": "203.0.113.5"}
    codes = [
        client.post("/api/v1/voice/handoff", json={"session_id": "nope"}, headers=h).status_code
        for _ in range(4)
    ]
    assert codes == [404, 404, 404, 429]
    other = client.post(
        "/api/v1/voice/handoff", json={"session_id": "nope"}, headers={"Fly-Client-IP": "203.0.113.6"}
    )
    assert other.status_code == 404


# --- voice handoff -----------------------------------------------------------


class FakeVapi:
    """Stands in for httpx.AsyncClient; records posts and returns a canned status."""

    calls: list = []
    status = 200
    raises = None
    body = None

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        FakeVapi.calls.append({"url": url, "json": json})
        if FakeVapi.raises:
            raise FakeVapi.raises
        status = FakeVapi.status
        body = FakeVapi.body

        class R:
            status_code = status
            text = "upstream secret detail"

            def json(self_inner):
                return body if body is not None else {"id": "call_123"}

        return R()


@pytest.fixture
def vapi(monkeypatch):
    FakeVapi.calls = []
    FakeVapi.status = 200
    FakeVapi.raises = None
    FakeVapi.body = None
    monkeypatch.setattr("app.routes.voice.httpx.AsyncClient", FakeVapi)
    monkeypatch.setattr(settings, "vapi_api_key", "k")
    monkeypatch.setattr(settings, "vapi_phone_number_id", "p")
    monkeypatch.setattr(settings, "vapi_webhook_secret", "s3cret")
    return FakeVapi


def _session_with_phone(phone="2125551234"):
    s = create_session()
    update_session(s.session_id, {"collected_data": {"phone_number": phone}})
    return s.session_id


def _handoff(sid, n=0):
    return client.post(
        "/api/v1/voice/handoff", json={"session_id": sid}, headers={"Fly-Client-IP": f"192.0.2.{n}"}
    )


def test_handoff_allowed_once_per_session(vapi):
    sid = _session_with_phone()
    first = _handoff(sid, 1)
    assert first.status_code == 200 and first.json()["call_id"] == "call_123"

    second = _handoff(sid, 2)  # different client, same session
    assert second.status_code == 409
    assert "already started" in second.json()["detail"]
    assert len(vapi.calls) == 1
    assert vapi.calls[0]["json"]["customer"]["number"] == "+12125551234"


def test_handoff_assistant_carries_webhook_secret(vapi):
    _handoff(_session_with_phone(), 1)
    assistant = vapi.calls[0]["json"]["assistant"]
    expected = {"X-Vapi-Secret": "s3cret"}
    assert assistant["server"]["headers"] == expected
    assert len(assistant["model"]["tools"]) == 2
    assert all(t["server"]["headers"] == expected for t in assistant["model"]["tools"])
    # The legacy field is no longer used anywhere.
    assert "secret" not in assistant["server"]
    assert all("secret" not in t["server"] for t in assistant["model"]["tools"])


def test_handoff_claim_released_when_vapi_rejects(vapi):
    sid = _session_with_phone()
    vapi.status = 500
    r = _handoff(sid, 1)
    assert r.status_code == 502
    assert "upstream secret detail" not in r.text  # no raw upstream body to the browser

    vapi.status = 200
    assert _handoff(sid, 2).status_code == 200
    assert len(vapi.calls) == 2


def test_handoff_claim_kept_when_outcome_is_unknown(vapi):
    import httpx

    sid = _session_with_phone()
    vapi.raises = httpx.ReadTimeout("slow")
    assert _handoff(sid, 1).status_code == 502

    vapi.raises = None
    assert _handoff(sid, 2).status_code == 409  # might have rung already; never risk a second call
    assert len(vapi.calls) == 1


# --- VAPI failure logging ----------------------------------------------------


def _failed_handoff(vapi, caplog, body, status=400):
    sid = _session_with_phone("2125559876")
    vapi.status = status
    vapi.body = body
    with caplog.at_level("WARNING", logger="elara.voice"):
        r = _handoff(sid, 1)
    return r, [rec.getMessage() for rec in caplog.records if rec.name == "elara.voice"]


def test_vapi_failure_logs_one_line_with_status_and_message(vapi, caplog):
    r, lines = _failed_handoff(vapi, caplog, {"message": "Couldn't find phone number", "statusCode": 400})
    assert lines == ["[VAPI] call failed status=400 message=Couldn't find phone number"]
    # Browser response is unchanged.
    assert r.status_code == 502
    assert r.json() == {"detail": "The phone service couldn't start the call right now. Please try again in a moment."}


def test_vapi_failure_message_list_is_joined(vapi, caplog):
    _, lines = _failed_handoff(vapi, caplog, {"message": ["customer.number must be E.164", "assistant is invalid"]})
    assert lines == ["[VAPI] call failed status=400 message=customer.number must be E.164; assistant is invalid"]


def test_vapi_failure_message_truncated_to_500(vapi, caplog):
    _, lines = _failed_handoff(vapi, caplog, {"message": "x" * 900})
    assert lines == ["[VAPI] call failed status=400 message=" + "x" * 500]


def test_vapi_failure_without_message_still_logs(vapi, caplog):
    _, lines = _failed_handoff(vapi, caplog, {"error": "Bad Request"}, status=401)
    assert lines == ["[VAPI] call failed status=401 message=(no message)"]


def test_vapi_failure_log_never_contains_sensitive_data(vapi, caplog):
    _, lines = _failed_handoff(vapi, caplog, {"message": "nope"})
    text = " ".join(lines) + caplog.text
    for secret in ("2125559876", "+12125559876", "s3cret", "phone_number", "Bearer"):
        assert secret not in text


# --- uvicorn access log ------------------------------------------------------


def test_access_log_filter_skips_health_only():
    import logging

    from app.core.access_log import SkipPathsFilter

    f = SkipPathsFilter({"/api/v1/health"})

    def rec(path):
        return logging.LogRecord(
            "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5", "GET", path, "1.1", 200), None
        )

    assert f.filter(rec("/api/v1/health")) is False
    assert f.filter(rec("/api/v1/health?x=1")) is False
    assert f.filter(rec("/api/v1/chat")) is True


def test_access_log_filter_is_installed_on_uvicorn():
    import logging

    from app.core.access_log import SkipPathsFilter

    assert any(isinstance(f, SkipPathsFilter) for f in logging.getLogger("uvicorn.access").filters)


@pytest.mark.parametrize(
    "bad",
    ["+12125551234", "12125551234", "212555123", "212-555-12345", "1125551234", "2121551234", "212555abcd", "212555123; x", ""],
)
def test_handoff_rejects_non_us_10_digit_phone(vapi, bad):
    sid = _session_with_phone(bad)
    r = _handoff(sid, 1)
    assert r.status_code == 400
    assert vapi.calls == []


@pytest.mark.parametrize("good", ["2125551234", "(212) 555-1234", "212-555-1234", "212.555.1234", "212 555 1234"])
def test_handoff_accepts_formatted_us_numbers(vapi, good):
    r = _handoff(_session_with_phone(good), 1)
    assert r.status_code == 200
    assert vapi.calls[0]["json"]["customer"]["number"] == "+12125551234"


def test_normalize_us_phone():
    assert normalize_us_phone("(212) 555-1234") == "2125551234"
    assert normalize_us_phone(None) is None
    assert normalize_us_phone("+1 212 555 1234") is None


def test_handoff_refuses_when_webhook_secret_not_configured(vapi, monkeypatch):
    monkeypatch.setattr(settings, "vapi_webhook_secret", None)
    r = _handoff(_session_with_phone(), 1)
    assert r.status_code == 500
    assert vapi.calls == []


# --- webhook secret ----------------------------------------------------------

TOOL_CALL = {
    "message": {
        "type": "tool-calls",
        "toolCallList": [{"id": "t1", "name": "get_session_context", "parameters": {"session_id": "nope"}}],
    }
}


def test_webhook_without_secret_is_401(monkeypatch):
    monkeypatch.setattr(settings, "vapi_webhook_secret", "s3cret")
    r = client.post("/api/v1/voice/webhook", json=TOOL_CALL)
    assert r.status_code == 401


def test_webhook_with_wrong_secret_is_401(monkeypatch):
    monkeypatch.setattr(settings, "vapi_webhook_secret", "s3cret")
    r = client.post("/api/v1/voice/webhook", json=TOOL_CALL, headers={"X-Vapi-Secret": "wrong"})
    assert r.status_code == 401


def test_webhook_with_correct_secret_is_processed(monkeypatch):
    monkeypatch.setattr(settings, "vapi_webhook_secret", "s3cret")
    r = client.post("/api/v1/voice/webhook", json=TOOL_CALL, headers={"X-Vapi-Secret": "s3cret"})
    assert r.status_code == 200
    result = json.loads(r.json()["results"][0]["result"])
    assert result["success"] is False  # unknown session, but the request got through


def test_webhook_fails_closed_when_no_secret_configured(monkeypatch):
    monkeypatch.setattr(settings, "vapi_webhook_secret", None)
    for headers in ({}, {"X-Vapi-Secret": ""}, {"X-Vapi-Secret": "anything"}):
        assert client.post("/api/v1/voice/webhook", json=TOOL_CALL, headers=headers).status_code == 401


def test_webhook_lifecycle_messages_also_need_the_secret(monkeypatch):
    monkeypatch.setattr(settings, "vapi_webhook_secret", "s3cret")
    body = {"message": {"type": "status-update"}}
    assert client.post("/api/v1/voice/webhook", json=body).status_code == 401
    assert client.post("/api/v1/voice/webhook", json=body, headers={"X-Vapi-Secret": "s3cret"}).status_code == 200


def test_default_limit_applies_to_the_flat_root_route_via_middleware():
    h = {"Fly-Client-IP": "203.0.113.10"}
    codes = [client.get("/", headers=h).status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429


def test_calendar_route_is_rate_limited_too():
    h = {"Fly-Client-IP": "203.0.113.11"}
    codes = [client.get("/api/v1/appointments/x/calendar.ics", headers=h).status_code for _ in range(61)]
    assert codes[:60] == [404] * 60 and codes[60] == 429
