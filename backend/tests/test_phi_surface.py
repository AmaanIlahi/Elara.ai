import importlib
import pkgutil

import pytest
from fastapi.testclient import TestClient

import app.routes as routes_pkg
from app.core.limiter import limiter
from app.main import app

client = TestClient(app)

REMOVED = [
    ("GET", "/api/v1/session/abc"),
    ("POST", "/api/v1/session/create"),
    ("POST", "/api/v1/scheduling/book"),
    ("POST", "/api/v1/refill/submit"),
    ("GET", "/api/v1/scheduling/availability"),
    ("POST", "/api/v1/chat/stream"),
    ("POST", "/api/v1/send-confirmation-email"),
    ("GET", "/api/v1/ping"),
]


@pytest.mark.parametrize("method,path", REMOVED)
def test_removed_endpoints_are_gone(method, path):
    r = client.request(method, path, json={"session_id": "x", "message": "hi"})
    assert r.status_code in (404, 405)


def test_session_phi_is_not_readable_by_id():
    sid = client.post("/api/v1/chat", json={"message": "hi"}).json()["session_id"]
    assert client.get(f"/api/v1/session/{sid}").status_code == 404


def test_chat_message_max_length_is_1000():
    ok = client.post("/api/v1/chat", json={"message": "a" * 1000})
    assert ok.status_code == 200
    too_long = client.post("/api/v1/chat", json={"message": "a" * 1001})
    assert too_long.status_code == 422


def test_every_router_endpoint_has_a_rate_limit_or_is_exempt():
    """Guards the slowapi/FastAPI gap described in app/core/limiter.py."""
    covered = set(limiter._route_limits) | set(limiter._exempt_routes)
    missing = []
    for mod in pkgutil.iter_modules(routes_pkg.__path__):
        router = getattr(importlib.import_module(f"app.routes.{mod.name}"), "router", None)
        for route in getattr(router, "routes", []):
            name = f"{route.endpoint.__module__}.{route.endpoint.__name__}"
            if name not in covered:
                missing.append(f"{sorted(route.methods)} {route.path} ({name})")
    assert missing == []
