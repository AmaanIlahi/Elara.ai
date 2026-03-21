from fastapi import APIRouter, Query

from app.services.scheduling_service import build_scheduling_response

router = APIRouter(tags=["Scheduling"])


@router.get("/scheduling/availability")
def get_availability(message: str = Query(..., description="Example: I need an appointment for knee pain")):
    return build_scheduling_response(message)