from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Elara AI Backend"
    app_version: str = "0.1.0"
    debug: bool = True

    frontend_origin: str = "http://localhost:3000"
    api_v1_prefix: str = "/api/v1"

    llm_provider: str = "gemini"
    llm_enabled: bool = False
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash-lite"
    llm_timeout_seconds: int = 15

    vapi_api_key: Optional[str] = None
    vapi_phone_number_id: Optional[str] = None
    public_backend_base_url: str = "http://localhost:8000"
    public_frontend_base_url: str = "http://localhost:3000"
    vapi_assistant_name: str = "Elara Voice Scheduler"

    resend_api_key: Optional[str] = None
    resend_from_email: str = "Elara <onboarding@resend.dev>"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()