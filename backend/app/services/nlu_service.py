# app/services/nlu_service.py

from __future__ import annotations

from typing import Dict, List, Optional

from app.services.fallback_nlu import fallback_extract
from app.services.llm_service import LLMExtractionResult, LLMService

# If LLM confidence is below this threshold AND no clear intent was extracted,
# we surface a clarifying question rather than silently falling back to keywords.
CONFIDENCE_THRESHOLD = 0.55


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
            # Low-confidence + no actionable intent → flag so the chat route can
            # ask a clarifying question instead of guessing.
            if (
                result.confidence < CONFIDENCE_THRESHOLD
                and result.intent in (None, "unknown")
            ):
                result.needs_clarification = True
            return result

        # LLM unavailable — use keyword fallback (always low-confidence)
        fallback = fallback_extract(user_message)
        return fallback