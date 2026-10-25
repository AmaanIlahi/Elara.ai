from app.core.config import Settings


def _clean(monkeypatch):
    for k in ("DEBUG", "LLM_ENABLED", "GEMINI_API_KEY", "VAPI_API_KEY", "VAPI_PHONE_NUMBER_ID", "VAPI_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)


def test_debug_defaults_to_false(monkeypatch):
    _clean(monkeypatch)
    assert Settings(_env_file=None).debug is False


def test_startup_summary_reports_unconfigured(monkeypatch):
    _clean(monkeypatch)
    line = Settings(_env_file=None).startup_summary()
    assert "llm_configured=False" in line
    assert "vapi_configured=False" in line
    assert "resend" not in line


def test_startup_summary_never_leaks_values():
    s = Settings(
        _env_file=None,
        llm_enabled=True,
        gemini_api_key="SECRET-GEMINI",
        vapi_api_key="SECRET-VAPI",
        vapi_phone_number_id="PHONE-ID-123",
        vapi_webhook_secret="SECRET-WEBHOOK",
    )
    line = s.startup_summary()
    assert "llm_configured=True" in line
    assert "vapi_configured=True" in line
    for secret in ("SECRET-GEMINI", "SECRET-VAPI", "PHONE-ID-123", "SECRET-WEBHOOK"):
        assert secret not in line


def test_vapi_needs_key_phone_id_and_webhook_secret():
    assert "vapi_configured=False" in Settings(_env_file=None, vapi_api_key="k").startup_summary()
    both = Settings(_env_file=None, vapi_api_key="k", vapi_phone_number_id="p")
    assert "vapi_configured=False" in both.startup_summary()
    assert "vapi_configured=True" in Settings(
        _env_file=None, vapi_api_key="k", vapi_phone_number_id="p", vapi_webhook_secret="s"
    ).startup_summary()


def test_llm_needs_enabled_flag_and_key():
    assert "llm_configured=False" in Settings(_env_file=None, gemini_api_key="k").startup_summary()
