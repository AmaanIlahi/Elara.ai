# app/services/nlu_service.py

from __future__ import annotations

from typing import Dict, List, Optional

from app.services.fallback_nlu import fallback_extract
from app.services.llm_service import LLMExtractionResult, LLMService


class NLUService:
    def __init__(self) -> None:
        self.llm = LLMService()

    async def extract(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        current_state: Optional[str] = None,
    ) -> LLMExtractionResult:
        result = await self.llm.extract_structured_intent(
            user_message=user_message,
            conversation_history=conversation_history,
            current_state=current_state,
        )
        if result:
            return result

        return fallback_extract(user_message)