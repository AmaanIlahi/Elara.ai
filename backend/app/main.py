from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.limiter import limiter
from app.services.session_service import SessionExpired
from app.routes.health import router as health_router
from app.routes.chat import router as chat_router
from app.routes.practice import router as practice_router
from app.routes.voice import router as voice_router
from app.routes.appointments import router as appointments_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

print(settings.startup_summary(), flush=True)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Applies the default limit to every route without its own. Added before CORS so
# CORS stays outermost and 429 responses still carry the CORS headers.
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(SessionExpired)
async def session_expired_handler(request: Request, exc: SessionExpired):
    return JSONResponse(status_code=404, content={"error": "session_expired"})

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://elara-ai-frontend.vercel.app",
    "https://elara-ai-frontend-5hst.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Fly's check and the browser warm-up hit this every few seconds; keep it out of the logs.
LOG_SKIP_PATHS = {f"{settings.api_v1_prefix}/health"}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    if request.url.path in LOG_SKIP_PATHS:
        return await call_next(request)

    print(f"REQUEST: {request.method} {request.url.path}", flush=True)
    response = await call_next(request)
    print(f"RESPONSE: {response.status_code} {request.url.path}", flush=True)
    return response


@app.get("/", tags=["Root"])
def root():
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
    }


app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.include_router(practice_router, prefix=settings.api_v1_prefix)
app.include_router(voice_router, prefix=settings.api_v1_prefix)
app.include_router(appointments_router, prefix=settings.api_v1_prefix)
