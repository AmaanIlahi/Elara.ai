from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes.health import router as health_router
from app.routes.session import router as session_router
from app.routes.chat import router as chat_router
from app.routes.practice import router as practice_router
from app.routes.scheduling import router as scheduling_router
from app.routes.booking import router as booking_router
from app.routes.refill import router as refill_router
from app.routes.voice import router as voice_router
from app.routes.email import router as email_router

# print("MAIN FILE LOADED", flush=True)
# print("EMAIL ROUTER IMPORTED:", email_router, flush=True)
# print("EMAIL ROUTER ROUTES COUNT:", len(email_router.routes), flush=True)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

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


@app.middleware("http")
async def log_requests(request: Request, call_next):
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
app.include_router(session_router, prefix=settings.api_v1_prefix)
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.include_router(practice_router, prefix=settings.api_v1_prefix)
app.include_router(scheduling_router, prefix=settings.api_v1_prefix)
app.include_router(booking_router, prefix=settings.api_v1_prefix)
app.include_router(refill_router, prefix=settings.api_v1_prefix)
app.include_router(voice_router, prefix=settings.api_v1_prefix)
app.include_router(email_router, prefix=settings.api_v1_prefix)

# print("=== REGISTERED ROUTES ===", flush=True)
# for route in app.routes:
#     methods = getattr(route, "methods", None)
#     path = getattr(route, "path", None)
#     name = getattr(route, "name", None)
#     print(f"{methods} {path} -> {name}", flush=True)
# print("=== END ROUTES ===", flush=True)