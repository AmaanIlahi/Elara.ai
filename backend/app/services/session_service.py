from typing import Dict, Optional
from datetime import datetime

from app.schemas.session import Session


SESSION_STORE: Dict[str, Session] = {}


def create_session(phone_number: Optional[str] = None) -> Session:
    session = Session(phone_number=phone_number)
    SESSION_STORE[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[Session]:
    return SESSION_STORE.get(session_id)


def update_session(session_id: str, data: dict) -> Optional[Session]:
    session = SESSION_STORE.get(session_id)
    if not session:
        return None

    for key, value in data.items():
        setattr(session, key, value)

    session.updated_at = datetime.utcnow()
    SESSION_STORE[session_id] = session
    return session


def delete_session(session_id: str):
    SESSION_STORE.pop(session_id, None)