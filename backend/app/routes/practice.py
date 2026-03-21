from fastapi import APIRouter
from app.services.practice_service import get_full_practice_info

router = APIRouter(tags=["Practice Info"])


@router.get("/practice/info")
def get_practice_info():
    return get_full_practice_info()