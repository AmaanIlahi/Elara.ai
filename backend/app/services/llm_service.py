# app/services/llm_service.py

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional, List, Dict

import google.genai as genai
import google.genai.types as types
from pydantic import BaseModel, Field

logger = logging.getLogger("elara.llm")

_shared_client: Any = None
_shared_client_key: Optional[str] = None


def get_shared_client(api_key: str) -> Any:
    """One genai.Client per process (per API key), shared by every LLMService."""
    global _shared_client, _shared_client_key
    if _shared_client is None or _shared_client_key != api_key:
        _shared_client = genai.Client(api_key=api_key)
        _shared_client_key = api_key
    return _shared_client


class LLMExtractionResult(BaseModel):
    intent: Optional[str] = Field(default=None)
    body_part: Optional[str] = Field(default=None)
    reason: Optional[str] = Field(default=None)
    requested_day: Optional[str] = Field(default=None)
    requested_time_pref: Optional[str] = Field(default=None)
    refill_medication: Optional[str] = Field(default=None)
    practice_info_topic: Optional[str] = Field(default=None)
    confidence: float = Field(default=0.0)
    # Set by NLUService post-processing, not by the LLM itself
    needs_clarification: bool = Field(default=False)


class LLMReplyResult(BaseModel):
    reply: str


class LLMService:
    def __init__(self, client: Any = None, timeout_seconds: Optional[float] = None) -> None:
        from app.core.config import settings

        self.enabled = settings.llm_enabled
        self.provider = settings.llm_provider
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds
        )

        # `client` is injectable for tests; otherwise reuse the process-wide client.
        self.client = client
        if self.client is None and self.enabled and self.provider == "gemini" and self.api_key:
            self.client = get_shared_client(self.api_key)

    def is_enabled(self) -> bool:
        return self.client is not None

    async def _generate(
        self,
        label: str,
        prompt: str,
        config: "types.GenerateContentConfig",
        timeout: Optional[float] = None,
    ) -> Any:
        """Async Gemini call with a real timeout. Returns the response, or None on
        timeout/error (logged with the function label, never the prompt or reply,
        since both can contain patient data)."""
        limit = timeout if timeout is not None else self.timeout_seconds
        started_at = time.monotonic()
        try:
            return await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model, contents=prompt, config=config
                ),
                timeout=limit,
            )
        except asyncio.TimeoutError:
            logger.warning("[LLM] %s timed out after %.1fs", label, limit)
        except Exception:
            logger.exception(
                "[LLM] %s failed after %dms", label, int((time.monotonic() - started_at) * 1000)
            )
        return None

    async def extract_structured_intent(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        current_state: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[LLMExtractionResult]:
        if not self.is_enabled():
            return None

        history_text = self._format_history(conversation_history)

        prompt = f"""
You are an AI workflow extraction engine for a medical practice front-desk assistant.

Your job is ONLY to extract structured workflow information.
Do NOT provide medical advice.
Do NOT diagnose.
Do NOT invent missing facts.

Current workflow state: {current_state or "unknown"}

Valid intent values:
- scheduling
- refill
- practice_info
- unknown

Valid practice_info_topic values:
- hours
- address
- phone
- general

Extraction rules:
- Use "scheduling" if the patient wants to book, schedule, see a provider, or asks for appointment times
- Use "refill" if the patient explicitly wants to refill or renew an existing prescription they already have — NOT if they are asking for medical advice, recommendations, or new medications
- Use "practice_info" if the patient asks about office hours, address, phone, location, or general office information
- Use "unknown" if unclear

Other rules:
- body_part should capture things like knee, shoulder, back, neck, skin, eye, ear, throat, ankle, wrist, head, headache, migraine, stomach, chest, heart, and any other body part or symptom the user mentions
- reason should be a short factual summary of why the patient wants help
- requested_day should capture phrases like Tuesday, next Monday, tomorrow, Friday afternoon
- requested_time_pref should capture simple preferences like morning, afternoon, evening
- refill_medication should capture medication if explicitly mentioned
- confidence should be between 0.0 and 1.0
- If not present, use null
- Keep extraction conservative

Conversation history:
{history_text}

Latest user message:
{user_message}
""".strip()

        response = await self._generate(
            "extract_structured_intent",
            prompt,
            types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=LLMExtractionResult,
            ),
            timeout,
        )
        if response is None or not response.parsed:
            return None

        parsed = response.parsed
        parsed.confidence = float(parsed.confidence or 0.0)
        return parsed

    async def generate_chat_reply(
        self,
        system_facts: Dict[str, str],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        if not self.is_enabled():
            return None

        history_text = self._format_history(conversation_history)

        facts_text = "\n".join(
            f"{key}: {value}" for key, value in system_facts.items() if value is not None
        )

        prompt = f"""
You are Elara, a warm and caring AI front-desk assistant for a medical practice.

Important rules:
- Do not provide medical advice or diagnose
- Do not invent appointment slots, office details, or patient data
- Only use the provided facts
- Be empathetic, human, and conversational — patients may be anxious or in discomfort
- Acknowledge the patient's situation warmly before delivering information
- Keep the response to 1-3 sentences
- Never sound robotic or formulaic

Provided facts:
{facts_text}

Conversation history:
{history_text}

Generate only the assistant reply text.
""".strip()

        response = await self._generate(
            "generate_chat_reply",
            prompt,
            types.GenerateContentConfig(temperature=0.4),
            timeout,
        )
        if response is None:
            return None

        text = getattr(response, "text", None)
        if not text:
            return None

        return text.strip()

    async def generate_general_reply(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Enhancement 1: Free-form conversation — lets the LLM answer general
        patient questions (e.g. 'what should I bring to my first visit?')
        instead of returning a generic 'I don't understand' message."""
        if not self.is_enabled():
            return None

        history_text = self._format_history(conversation_history)

        prompt = f"""
You are Elara, a warm, empathetic AI front-desk assistant for a medical practice. Patients come to you when they're worried, in pain, or just need help navigating their care.

You can help with:
- General questions about visiting a doctor's office
- What to expect during appointments
- How to prepare for visits
- Insurance and billing questions (give general guidance, not specific advice)

Important rules:
- Lead with empathy — acknowledge the patient's feelings or situation before answering
- Do NOT provide medical advice or diagnose conditions
- Do NOT prescribe or recommend specific medications
- Do NOT invent specific details about this practice (hours, doctors, etc.)
- If asked something outside your scope, kindly redirect them to call the office or speak with their doctor
- Be conversational and human — avoid clinical or robotic language
- Keep responses to 2-4 sentences
- If the user seems to want to schedule, refill, or ask about office info, gently suggest those options

Conversation history:
{history_text}

User message:
{user_message}

Generate only the assistant reply text.
""".strip()

        response = await self._generate(
            "generate_general_reply",
            prompt,
            types.GenerateContentConfig(temperature=0.7),
            timeout,
        )
        if response is None:
            return None

        text = getattr(response, "text", None)
        if not text:
            return None

        return text.strip()

    async def extract_intake_fields(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, str]]:
        """Enhancement 2: Natural intake — lets users provide multiple fields
        in one message (e.g. 'I'm John Smith, born July 30 1998, email john@gmail.com')
        and the LLM extracts all of them at once."""
        if not self.is_enabled():
            return None

        history_text = self._format_history(conversation_history)

        prompt = f"""
You are extracting patient intake information from a conversational message.

Extract any of these fields if present in the user's message:
- first_name: the patient's first/given name
- last_name: the patient's last/family name
- dob: date of birth in YYYY-MM-DD format (convert from any format the user provides)
- phone_number: 10-digit US phone number (digits only, no dashes or spaces)
- email: email address

Rules:
- Only extract fields that are clearly and explicitly stated as personal data
- Do NOT guess or invent values
- If the message is conversational (e.g. "yes", "ok", "no go back", "sure", "I will give you details", "go back"), return an empty JSON object {{}}. These are NOT intake data.
- Words like "yes", "no", "ok", "sure", "go", "back" are NEVER valid names. Do not extract them as first_name or last_name.
- For dob, convert any date format to YYYY-MM-DD (e.g., "January 1 2000" → "2000-01-01"). The date must be a valid calendar date (month 1-12, day 1-31) and must be in the past (not a future date).
- For phone_number, strip all non-digit characters and return 10 digits only
- If a field is not mentioned, do not include it
- Return ONLY the fields found, as a JSON object. Return {{}} if no real data is found.

Conversation history:
{history_text}

User message:
{user_message}
""".strip()

        response = await self._generate(
            "extract_intake_fields",
            prompt,
            types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
            timeout,
        )
        if response is None:
            return None

        text = getattr(response, "text", None)
        if not text:
            return None

        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError:
            logger.warning("[LLM] extract_intake_fields returned non-JSON output")
            return None
        if isinstance(parsed, dict) and len(parsed) > 0:
            return parsed

        return None

    async def generate_post_booking_guidance(
        self,
        specialty: str,
        body_part: str,
        doctor_name: str,
        appointment_date: str,
        appointment_time: str,
        timeout: Optional[float] = None,
    ) -> Optional[str]:
        """Enhancement 5: Post-booking guidance — generates personalized
        preparation tips after an appointment is booked, based on the
        specialty and body part."""
        if not self.is_enabled():
            return None

        prompt = f"""
You are Elara, a warm and caring AI front-desk assistant for a medical practice.

A patient has just confirmed their appointment:
- Doctor: {doctor_name}
- Specialty: {specialty}
- Concern: {body_part}
- Date: {appointment_date}
- Time: {appointment_time}

Generate a short, friendly, personalized preparation guide. Include:
1. What to bring (documents, insurance, imaging if relevant)
2. How to prepare (clothing, fasting if relevant)
3. One reassuring, specific tip for their concern

Rules:
- Keep it to 3-4 bullet points
- Open with a single warm sentence, e.g. "To help make your visit as smooth as possible, here are a few things to keep in mind:"
- Be warm and reassuring — the patient may be nervous
- Do NOT diagnose or give medical advice
- Use simple, friendly language — no jargon

Generate only the guidance text.
""".strip()

        response = await self._generate(
            "generate_post_booking_guidance",
            prompt,
            types.GenerateContentConfig(temperature=0.6),
            timeout,
        )
        if response is None:
            return None

        text = getattr(response, "text", None)
        if not text:
            return None

        return text.strip()

    def _format_history(
        self,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        if not conversation_history:
            return "No prior conversation."

        trimmed = conversation_history[-8:]
        lines = []
        for msg in trimmed:
            role = msg.get("role", "user")
            content = msg.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")

        return "\n".join(lines) if lines else "No prior conversation."