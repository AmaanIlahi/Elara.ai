from fastapi import APIRouter, Request

from app.core.limiter import default_limit
from app.services.practice_service import get_full_practice_info

router = APIRouter(tags=["Practice Info"])


@router.get("/practice/info")
@default_limit
def get_practice_info(request: Request):
    return get_full_practice_info()