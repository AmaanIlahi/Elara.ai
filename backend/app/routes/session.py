from fastapi import APIRouter, HTTPException
from app.services.session_service import create_session, get_session

router = APIRouter(tags=["Session"])


@router.post("/session/create")
def create_new_session():
    session = create_session()
    return {
        "session_id": session.session_id,
        "message": "Session created successfully"
    }


@router.get("/session/{session_id}")
def fetch_session(session_id: str):
    session = get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session