from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_unknown_session_id_returns_session_expired():
    r = client.post("/api/v1/chat", json={"message": "hi", "session_id": "does-not-exist"})
    assert r.status_code == 404
    assert r.json() == {"error": "session_expired"}


def test_no_session_id_creates_new_session():
    r = client.post("/api/v1/chat", json={"message": "what are your hours?"})
    assert r.status_code == 200
    assert r.json()["session_id"]


def test_known_session_id_is_accepted():
    sid = client.post("/api/v1/chat", json={"message": "hi"}).json()["session_id"]
    r = client.post("/api/v1/chat", json={"message": "hi again", "session_id": sid})
    assert r.status_code == 200
    assert r.json()["session_id"] == sid
