import asyncio
import logging
import time
from types import SimpleNamespace

import pytest

from app.services import llm_service as llm_module
from app.services.llm_service import LLMExtractionResult, LLMService


class FakeAioModels:
    """Only exposes the async API: a sync `client.models` would raise AttributeError."""

    def __init__(self, text="hello", delay=0.0, error=None, parsed=None):
        self.text, self.delay, self.error, self.parsed = text, delay, error, parsed
        self.calls = 0

    async def generate_content(self, model, contents, config):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text, parsed=self.parsed)


def make_service(**kw):
    models = FakeAioModels(**kw)
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return LLMService(client=client, timeout_seconds=0.2), models


async def test_slow_call_times_out_and_returns_none():
    svc, _ = make_service(delay=5)
    started = time.monotonic()
    result = await svc.generate_general_reply("what should I bring?")
    assert result is None
    assert time.monotonic() - started < 1.5


async def test_slow_call_does_not_block_the_event_loop():
    svc, _ = make_service(delay=5)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    t = asyncio.create_task(ticker())
    await svc.generate_general_reply("hi")
    t.cancel()
    assert ticks >= 5  # loop kept running while Gemini was "slow"


async def test_outer_wait_for_now_cancels_a_slow_call():
    # chat.py wraps calls in asyncio.wait_for(..., 3/5/8s); that must work too.
    svc, _ = make_service(delay=5)
    svc.timeout_seconds = 30
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(svc.generate_general_reply("hi"), timeout=0.1)


async def test_explicit_timeout_overrides_default():
    svc, _ = make_service(delay=0.5)
    svc.timeout_seconds = 30
    assert await svc.generate_general_reply("hi", timeout=0.05) is None


async def test_errors_are_logged_not_swallowed_silently(caplog):
    svc, _ = make_service(error=RuntimeError("boom"))
    with caplog.at_level(logging.WARNING, logger="elara.llm"):
        assert await svc.generate_chat_reply({"state": "X"}) is None
    assert any("generate_chat_reply" in r.getMessage() and r.exc_info for r in caplog.records)


async def test_timeout_is_logged(caplog):
    svc, _ = make_service(delay=5)
    with caplog.at_level(logging.WARNING, logger="elara.llm"):
        await svc.generate_post_booking_guidance("Ortho", "knee", "Dr X", "2026-01-01", "9:00 AM")
    assert any("timed out" in r.getMessage() for r in caplog.records)


async def test_all_five_functions_use_the_async_client():
    parsed = LLMExtractionResult(intent="scheduling", confidence=0.9)
    svc, models = make_service(text='{"first_name": "Ann"}', parsed=parsed)

    assert (await svc.extract_structured_intent("book knee")).intent == "scheduling"
    assert await svc.generate_chat_reply({"state": "X"}) == '{"first_name": "Ann"}'
    assert await svc.generate_general_reply("hi") == '{"first_name": "Ann"}'
    assert await svc.extract_intake_fields("I'm Ann") == {"first_name": "Ann"}
    assert await svc.generate_post_booking_guidance("Ortho", "knee", "Dr X", "d", "t")
    assert models.calls == 5


async def test_intake_fields_non_json_returns_none():
    svc, _ = make_service(text="not json")
    assert await svc.extract_intake_fields("hello") is None


def test_one_shared_client_across_services(monkeypatch):
    from app.core.config import settings

    created = []
    monkeypatch.setattr(llm_module.genai, "Client", lambda api_key: created.append(api_key) or object())
    monkeypatch.setattr(llm_module, "_shared_client", None)
    monkeypatch.setattr(llm_module, "_shared_client_key", None)
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    a, b = LLMService(), LLMService()
    assert a.client is b.client
    assert len(created) == 1


def test_disabled_without_key():
    assert LLMService().is_enabled() is False
