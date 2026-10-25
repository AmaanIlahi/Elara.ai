import os
import sys

# Make `app` importable and keep tests hermetic: no real LLM/VAPI config.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LLM_ENABLED"] = "false"
os.environ.pop("GEMINI_API_KEY", None)

import pytest

from app.services import session_service


@pytest.fixture(autouse=True)
def clean_state():
    from app.core.limiter import limiter
    from app.data import provider_data

    session_service.SESSION_STORE.clear()
    provider_data.BOOKED_SLOTS.clear()
    limiter.reset()
    yield
    session_service.SESSION_STORE.clear()
    provider_data.BOOKED_SLOTS.clear()
