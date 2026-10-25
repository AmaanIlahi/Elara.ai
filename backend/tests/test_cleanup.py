from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app

client = TestClient(app)
BACKEND = Path(__file__).resolve().parent.parent


def test_health_requests_are_not_logged(capsys):
    client.get("/api/v1/health")
    assert "/api/v1/health" not in capsys.readouterr().out


def test_other_requests_are_still_logged(capsys):
    client.get("/api/v1/practice/info")
    out = capsys.readouterr().out
    assert "REQUEST: GET /api/v1/practice/info" in out
    assert "RESPONSE: 200 /api/v1/practice/info" in out


def test_unused_settings_are_gone():
    fields = Settings.model_fields
    for name in ("frontend_origin", "public_frontend_base_url", "resend_api_key", "resend_from_email"):
        assert name not in fields


def test_env_example_lists_every_setting_and_nothing_stale():
    text = (BACKEND / ".env.example").read_text(encoding="utf-8")
    declared = {line.split("=", 1)[0] for line in text.splitlines() if "=" in line and not line.startswith("#")}
    expected = {name.upper() for name in Settings.model_fields} | {"PORT"}
    assert declared == expected


def test_requirements_are_utf8_and_pinned():
    raw = (BACKEND / "requirements.txt").read_bytes()
    text = raw.decode("utf-8")  # raises on UTF-16
    assert not raw.startswith((b"\xff\xfe", b"\xfe\xff"))
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines and all("==" in line for line in lines)
    names = {line.split("==")[0].lower() for line in lines}
    for unused in ("boto3", "sqlalchemy", "alembic", "python-jose", "passlib", "bcrypt", "aiohttp", "email-validator", "python-multipart", "requests"):
        assert unused not in names
