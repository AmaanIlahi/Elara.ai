"""One shared slowapi Limiter for the whole app."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

DEFAULT_LIMIT = "60/minute"


def client_key(request: Request) -> str:
    """Rate-limit key: the real client IP.

    Behind Fly's proxy, request.client.host is the proxy's address, so every
    visitor would share one bucket. Fly puts the caller's address in the
    Fly-Client-IP header (and overwrites any value the client sent). Fall back to
    the socket address for local development and tests.
    """
    forwarded = request.headers.get("fly-client-ip")
    if forwarded and forwarded.strip():
        return forwarded.strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_key, default_limits=[DEFAULT_LIMIT])

# SlowAPIMiddleware applies the default limit by looking up each request's handler
# in app.routes. FastAPI wraps routers added with include_router() in an object
# slowapi cannot see into, so for those routes the middleware silently skips the
# default limit. Every router endpoint therefore carries this decorator (or its
# own @limiter.limit / @limiter.exempt); tests/test_abuse_protection.py checks that.
default_limit = limiter.limit(DEFAULT_LIMIT)
