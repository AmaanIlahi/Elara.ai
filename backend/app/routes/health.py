from fastapi import APIRouter

from app.core.limiter import limiter

router = APIRouter(tags=["Health"])


@router.get("/health")
@limiter.exempt
def health_check():
    return {
        "status": "ok",
        "service": "elara.ai backend",
        "message": "Backend is running successfully",
    }