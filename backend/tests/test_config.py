from app.core.config import Settings


def _clean(monkeypatch):
    for k in ("DEBUG", "LLM_ENABLED", "GEMINI_API_KEY", "VAPI_API_KEY", "VAPI_PHONE_NUMBER_ID", "RESEND_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_debug_defaults_to_false(monkeypatch):
    _clean(monkeypatch)
    assert Settings(_env_file=None).debug is False


def test_startup_summary_reports_unconfigured(monkeypatch):
    _clean(monkeypatch)
    line = Settings(_env_file=None).startup_summary()
    assert "llm_configured=False" in line
    assert "vapi_configured=False" in line
    assert "resend_configured=False" in line


def test_startup_summary_never_leaks_values():
    s = Settings(
        _env_file=None,
        llm_enabled=True,
        gemini_api_key="SECRET-GEMINI",
        vapi_api_key="SECRET-VAPI",
        vapi_phone_number_id="PHONE-ID-123",
        resend_api_key="SECRET-RESEND",
    )
    line = s.startup_summary()
    assert "llm_configured=True" in line
    assert "vapi_configured=True" in line
    assert "resend_configured=True" in line
    for secret in ("SECRET-GEMINI", "SECRET-VAPI", "PHONE-ID-123", "SECRET-RESEND"):
        assert secret not in line


def test_vapi_needs_both_key_and_phone_id():
    assert "vapi_configured=False" in Settings(_env_file=None, vapi_api_key="k").startup_summary()


def test_llm_needs_enabled_flag_and_key():
    assert "llm_configured=False" in Settings(_env_file=None, gemini_api_key="k").startup_summary()
