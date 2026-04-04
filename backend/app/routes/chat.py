import asyncio
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import AsyncGenerator, Optional

limiter = Limiter(key_func=get_remote_address)

from app.schemas.chat import ChatRequest, ChatResponse, QuickReply
from app.services.chat_service import detect_workflow, get_workflow_response, get_services_overview
from app.services.intake_service import (
    build_intake_prompt,
    continue_intake_flow,
    extract_field_value,
    get_missing_intake_field,
    sanitize_text,
)
from app.services.llm_service import LLMService
from app.services.nlu_service import NLUService
from app.services.practice_service import answer_practice_question
from app.data.practice_data import PRACTICE_INFO
from app.services.refill_service import build_refill_response, continue_refill_flow, submit_refill_request
from app.services.scheduling_service import (
    UNSUPPORTED_CONCERN_KEYWORDS,
    build_scheduling_response,
    build_slot_list_message,
    build_slot_quick_replies,
    confirm_booking_from_session_data,
    extract_weekday_preference,
    filter_slots_by_weekday,
    format_slot_date,
    normalize_requested_day,
    parse_relative_slot_preference,
    parse_slot_choice,
    parse_time_choice,
    resolve_slot_preference,
)
from app.services.session_service import create_session, get_session, update_session

router = APIRouter(tags=["Chat"])

nlu_service = NLUService()
llm_service = LLMService()
print(f"[STARTUP] LLM Service enabled={llm_service.enabled}, client={llm_service.client is not None}, model={llm_service.model}")


def _build_quick_replies(state: str, metadata: dict) -> list:
    """Return QuickReply objects when the state presents choices to the user."""
    if state == "SCHEDULING_SHOWING_SLOTS":
        slots = metadata.get("slots", [])
        if slots:
            raw = build_slot_quick_replies(slots)
            return [QuickReply(**r) for r in raw]
    if state == "SCHEDULING_CONFIRMING":
        return [
            QuickReply(id="confirm_yes", label="Yes, confirm it", value="Yes, please confirm"),
            QuickReply(id="confirm_no", label="No, pick a different slot", value="No, I'd like a different slot"),
        ]
    if state == "REFILL_CONFIRMING":
        return [
            QuickReply(id="refill_yes", label="Yes, submit it", value="Yes, please submit"),
            QuickReply(id="refill_no", label="No, change details", value="No, I need to change the details"),
        ]
    if state == "PRACTICE_INFO_DONE":
        return [
            QuickReply(id="pi_schedule", label="Schedule an appointment", value="I'd like to schedule an appointment"),
            QuickReply(id="pi_refill", label="Request a refill", value="I need a prescription refill"),
            QuickReply(id="pi_more", label="Another question", value="I have another question"),
        ]
    return []


def _normalize_workflow(workflow_type: Optional[str]) -> Optional[str]:
    if not workflow_type:
        return workflow_type

    mapping = {
        "schedule": "scheduling",
        "scheduling": "scheduling",
        "appointment": "scheduling",
        "refill": "refill",
        "practice_info": "practice_info",
        "practice": "practice_info",
        "unknown": "unknown",
    }

    return mapping.get(workflow_type, workflow_type)


def _get_conversation_history(session):
    history = session.collected_data.get("history", [])
    if isinstance(history, list):
        return history
    return []


def _append_history(session, role: str, content: str):
    history = _get_conversation_history(session)
    history.append({"role": role, "content": content})
    return history


POLISHABLE_STATES = {
    "PRACTICE_INFO_STARTED",
    "PRACTICE_INFO_DONE",
    "REFILL_STARTED",
    "REFILL_NEEDS_MEDICATION",
    "REFILL_NEEDS_PHARMACY",
    "REFILL_CONFIRMING",
    "REFILL_SUBMITTED",
    "SCHEDULING_STARTED",
    # SCHEDULING_NEEDS_BODY_PART intentionally excluded — LLM polish causes an
    # infinite loop where it rephrases the same question with empathy indefinitely
    "SCHEDULING_UNSUPPORTED_BODY_PART",
    "SCHEDULING_SHOWING_SLOTS",
    "SCHEDULING_CONFIRMING",
    "SCHEDULING_INVALID_SLOT_CHOICE",
    "COLLECTING_INTAKE",
    "BOOKED",
    "GENERAL_CONVERSATION",
}


async def _maybe_append_booking_guidance(message: str, metadata: dict) -> str:
    """Enhancement 5: After booking confirmation, append LLM-generated
    preparation tips specific to the specialty and body part."""
    if not llm_service.is_enabled():
        return message
    if not metadata:
        return message

    booking_confirmed = metadata.get("booking_confirmed", False)
    print(f"Booking guidance check: booking_confirmed={booking_confirmed}, metadata_keys={list(metadata.keys())}")
    if not booking_confirmed:
        return message

    try:
        guidance = await asyncio.wait_for(
            llm_service.generate_post_booking_guidance(
                specialty=metadata.get("specialty", ""),
                body_part=metadata.get("body_part", ""),
                doctor_name=metadata.get("provider_name", ""),
                appointment_date=metadata.get("booked_slot", {}).get("date", ""),
                appointment_time=metadata.get("booked_slot", {}).get("time", ""),
            ),
            timeout=5,
        )
        if guidance:
            return f"{message}\n\n{guidance}"
    except Exception as e:
        print(f"Post-booking guidance failed: {e}")

    return message


async def _maybe_polish_reply(session, assistant_message: str, state: str, workflow_type: str, metadata: dict):
    if state not in POLISHABLE_STATES:
        return assistant_message

    if metadata and metadata.get("slots"):
        return assistant_message

    if not llm_service.is_enabled():
        return assistant_message

    try:
        system_facts = {
            "workflow_type": workflow_type or "unknown",
            "state": state or "",
            "final_message": assistant_message,
            "provider_name": str(metadata.get("provider_name", "")) if metadata else "",
            "selected_slot": str(metadata.get("selected_slot", "")) if metadata else "",
            "pending_intake_field": str(
                session.collected_data.get("pending_intake_field", "")
            ),
        }

        polished = await asyncio.wait_for(
            llm_service.generate_chat_reply(
                system_facts=system_facts,
                conversation_history=_get_conversation_history(session),
            ),
            timeout=3,
        )

        if polished:
            return polished

    except Exception as e:
        print("LLM polish failed:", str(e))

    return assistant_message


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def handle_chat(body: ChatRequest, request: Request):
    # Sanitize raw input at the system boundary before any processing
    request_data = body.model_copy(update={"message": sanitize_text(body.message)})
    # Rebind to the name the rest of the function uses
    request = request_data  # type: ignore[assignment]

    session = None

    if request.session_id:
        session = get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    if not session:
        session = create_session(phone_number=request.phone_number)

    if session.status == "completed":
        session = create_session(phone_number=session.phone_number)

    metadata = {}
    workflow_type = session.workflow_type

    history = _get_conversation_history(session)

    extracted = await nlu_service.extract(
        user_message=request.message,
        conversation_history=history,
        current_state=session.state,
    )

    pending_intake_field = session.collected_data.get("pending_intake_field")
    if pending_intake_field:
        # Check if the user is asking a question instead of providing intake data
        msg_lower = request.message.strip().lower()
        question_words = ("what", "which", "where", "when", "how", "why", "who", "can", "do", "does", "is", "should", "could", "would")
        is_question = "?" in request.message or msg_lower.startswith(question_words)

        if is_question and llm_service.is_enabled():
            try:
                llm_reply = await asyncio.wait_for(
                    llm_service.generate_general_reply(
                        user_message=request.message,
                        conversation_history=history,
                    ),
                    timeout=8,
                )
                if llm_reply:
                    reminder = build_intake_prompt(pending_intake_field)
                    full_reply = f"{llm_reply}\n\nTo continue, {reminder.lower()}"

                    updated_history = list(history)
                    updated_history.append({"role": "user", "content": request.message})
                    updated_history.append({"role": "assistant", "content": full_reply})
                    updated_collected = dict(session.collected_data)
                    updated_collected["history"] = updated_history

                    updated_session = update_session(
                        session.session_id,
                        {"collected_data": updated_collected, "last_message": request.message},
                    )

                    return ChatResponse(
                        session_id=updated_session.session_id,
                        workflow_type=updated_session.workflow_type,
                        state=updated_session.state,
                        message=full_reply,
                        next_step=updated_session.state,
                        metadata={"pending_intake_field": pending_intake_field},
                    )
            except Exception as e:
                print(f"LLM intake question reply failed: {e}")

        # Enhancement 2: Try LLM multi-field extraction first
        # If user says "I'm John Smith, born July 30 1998, john@gmail.com",
        # extract all fields at once instead of asking one by one
        if llm_service.is_enabled():
            try:
                llm_fields = await asyncio.wait_for(
                    llm_service.extract_intake_fields(
                        user_message=request.message,
                        conversation_history=history,
                    ),
                    timeout=5,
                )
                if llm_fields and len(llm_fields) >= 1:
                    # Validate each extracted field before accepting
                    validated_fields = {}
                    for fn, fv in llm_fields.items():
                        if fn in ["first_name", "last_name", "dob", "phone_number", "email"]:
                            checked = extract_field_value(fn, str(fv))
                            if checked:
                                validated_fields[fn] = checked
                    llm_fields = validated_fields

                    if len(llm_fields) >= 1:
                        # Apply all validated fields to session
                        multi_collected = dict(session.collected_data)
                        multi_session_updates = {}
                        for field_name, field_value in llm_fields.items():
                            multi_collected[field_name] = field_value
                            multi_session_updates[field_name] = field_value

                        # Check what's still missing after bulk extraction
                        next_missing = get_missing_intake_field(
                            multi_collected,
                            {**{
                                "first_name": session.first_name,
                                "last_name": session.last_name,
                                "dob": session.dob,
                                "phone_number": session.phone_number,
                                "email": session.email,
                            }, **multi_session_updates},
                        )

                        if next_missing:
                            multi_collected["pending_intake_field"] = next_missing
                            filled_count = len(llm_fields)
                            if filled_count == 1:
                                ack_message = f"Thanks! {build_intake_prompt(next_missing)}"
                            else:
                                ack_message = f"Perfect, got those! {build_intake_prompt(next_missing)}"

                            updated_history = list(history)
                            updated_history.append({"role": "user", "content": request.message})
                            updated_history.append({"role": "assistant", "content": ack_message})
                            multi_collected["history"] = updated_history
                            multi_collected["last_nlu"] = extracted.model_dump()

                            updated_session = update_session(
                                session.session_id,
                                {
                                    "last_message": request.message,
                                    "state": "COLLECTING_INTAKE",
                                    "collected_data": multi_collected,
                                    **multi_session_updates,
                                },
                            )

                            return ChatResponse(
                                session_id=updated_session.session_id,
                                workflow_type=updated_session.workflow_type,
                                state=updated_session.state,
                                message=ack_message,
                                next_step=updated_session.state,
                                metadata={"pending_intake_field": next_missing},
                            )
                        else:
                            # All fields captured via LLM — show slots or ask for confirmation
                            multi_collected.pop("pending_intake_field", None)
                            multi_collected["last_nlu"] = extracted.model_dump()
                            selected_slot = multi_collected.get("selected_slot")

                            updated_session = update_session(
                                session.session_id,
                                {
                                    "collected_data": multi_collected,
                                    **multi_session_updates,
                                },
                            )

                            if selected_slot is not None:
                                # Don't auto-book — ask for confirmation
                                slots = multi_collected.get("slots", [])
                                if slots and 1 <= selected_slot <= len(slots):
                                    pending_slot_obj = slots[selected_slot - 1]
                                    slot_label = format_slot_date(pending_slot_obj["date"], pending_slot_obj["time"])
                                    provider_name_c = multi_collected.get("provider_name", "")
                                    specialty_c = multi_collected.get("specialty", "")
                                    body_part_c = multi_collected.get("body_part", "")
                                    confirm_msg = (
                                        f"Great news — I have everything I need! Just to confirm, "
                                        f"you'd like to book an appointment with {provider_name_c} ({specialty_c}) "
                                        f"for your {body_part_c} on {slot_label}. Shall I go ahead and confirm this?"
                                    )
                                    multi_collected["pending_slot_choice"] = selected_slot
                                    multi_collected.pop("selected_slot", None)

                                    updated_history = list(history)
                                    updated_history.append({"role": "user", "content": request.message})
                                    updated_history.append({"role": "assistant", "content": confirm_msg})
                                    multi_collected["history"] = updated_history

                                    final_session = update_session(
                                        updated_session.session_id,
                                        {
                                            "last_message": request.message,
                                            "state": "SCHEDULING_CONFIRMING",
                                            "collected_data": multi_collected,
                                        },
                                    )

                                    return ChatResponse(
                                        session_id=final_session.session_id,
                                        workflow_type=final_session.workflow_type,
                                        state=final_session.state,
                                        message=confirm_msg,
                                        next_step=final_session.state,
                                        metadata={},
                                        quick_replies=_build_quick_replies("SCHEDULING_CONFIRMING", {}),
                                    )

                            # No slot selected yet — show slots immediately
                            stored_slots = multi_collected.get("slots", [])
                            body_part_val = multi_collected.get("body_part", "")
                            provider_name_val = multi_collected.get("provider_name", "")
                            specialty_val = multi_collected.get("specialty", "")
                            display_slots = stored_slots[:5]
                            intro = (
                                f"Great, I have all your information! Here are the available slots with "
                                f"{provider_name_val} ({specialty_val}) for your {body_part_val} concern."
                            )
                            slot_msg = build_slot_list_message(
                                provider_name_val, specialty_val, body_part_val, display_slots, intro=intro
                            )
                            slot_metadata = {
                                "slots": display_slots,
                                "provider_name": provider_name_val,
                                "specialty": specialty_val,
                                "body_part": body_part_val,
                            }
                            multi_collected.update(slot_metadata)

                            updated_history = list(history)
                            updated_history.append({"role": "user", "content": request.message})
                            updated_history.append({"role": "assistant", "content": slot_msg})
                            multi_collected["history"] = updated_history

                            final_session = update_session(
                                updated_session.session_id,
                                {
                                    "last_message": request.message,
                                    "state": "SCHEDULING_SHOWING_SLOTS",
                                    "collected_data": multi_collected,
                                },
                            )

                            return ChatResponse(
                                session_id=final_session.session_id,
                                workflow_type=final_session.workflow_type,
                                state=final_session.state,
                                message=slot_msg,
                                next_step=final_session.state,
                                metadata=slot_metadata,
                                quick_replies=_build_quick_replies("SCHEDULING_SHOWING_SLOTS", slot_metadata),
                            )

            except Exception as e:
                print(f"LLM multi-field extraction failed: {e}")
                pass  # fall back to single-field extraction

        success, intake_result = continue_intake_flow(
            request.message,
            pending_intake_field,
            session.collected_data,
            {
                "first_name": session.first_name,
                "last_name": session.last_name,
                "dob": session.dob,
                "phone_number": session.phone_number,
                "email": session.email,
            },
        )

        updated_collected_data = intake_result.get("collected_data", dict(session.collected_data))
        updated_collected_data["last_nlu"] = extracted.model_dump()

        if intake_result["state"] == "INTAKE_COMPLETE":
            selected_slot = updated_collected_data.get("selected_slot")

            if selected_slot is not None:
                # Don't auto-book — ask for confirmation first
                slots = updated_collected_data.get("slots", [])
                updated_collected_data.pop("pending_intake_field", None)
                updated_collected_data.update(intake_result.get("session_updates", {}))

                if slots and 1 <= selected_slot <= len(slots):
                    pending_slot_obj = slots[selected_slot - 1]
                    slot_label = format_slot_date(pending_slot_obj["date"], pending_slot_obj["time"])
                    provider_name_c = updated_collected_data.get("provider_name", "")
                    specialty_c = updated_collected_data.get("specialty", "")
                    body_part_c = updated_collected_data.get("body_part", "")

                    confirm_msg = (
                        f"Great, I have all your details! Just to confirm — you'd like to book "
                        f"an appointment with {provider_name_c} ({specialty_c}) for your {body_part_c} "
                        f"on {slot_label}. Shall I go ahead and confirm this?"
                    )
                    updated_collected_data["pending_slot_choice"] = selected_slot
                    updated_collected_data.pop("selected_slot", None)

                    updated_history = list(history)
                    updated_history.append({"role": "user", "content": request.message})
                    updated_history.append({"role": "assistant", "content": confirm_msg})
                    updated_collected_data["history"] = updated_history

                    updated_session_payload = {
                        "last_message": request.message,
                        "workflow_type": session.workflow_type,
                        "state": "SCHEDULING_CONFIRMING",
                        "collected_data": updated_collected_data,
                    }
                    updated_session_payload.update(intake_result.get("session_updates", {}))
                    updated_session = update_session(session.session_id, updated_session_payload)

                    return ChatResponse(
                        session_id=updated_session.session_id,
                        workflow_type=updated_session.workflow_type,
                        state=updated_session.state,
                        message=confirm_msg,
                        next_step=updated_session.state,
                        metadata={},
                        quick_replies=_build_quick_replies("SCHEDULING_CONFIRMING", {}),
                    )

        # When intake completes in a scheduling flow, show stored slots instead of the generic ack
        resp_message = intake_result["message"]
        resp_state = intake_result["state"]
        resp_metadata = intake_result.get("metadata", {})

        if intake_result["state"] == "INTAKE_COMPLETE" and session.workflow_type == "scheduling":
            stored_slots = updated_collected_data.get("slots", [])
            if stored_slots:
                body_part_val = updated_collected_data.get("body_part", "")
                provider_name_val = updated_collected_data.get("provider_name", "")
                specialty_val = updated_collected_data.get("specialty", "")
                display_slots = stored_slots[:5]
                intro = (
                    f"Great, I have all your information! Here are the available slots with "
                    f"{provider_name_val} ({specialty_val}) for your {body_part_val} concern."
                )
                resp_message = build_slot_list_message(provider_name_val, specialty_val, body_part_val, display_slots, intro=intro)
                resp_state = "SCHEDULING_SHOWING_SLOTS"
                resp_metadata = {
                    "slots": display_slots,
                    "provider_name": provider_name_val,
                    "specialty": specialty_val,
                    "body_part": body_part_val,
                }
                updated_collected_data.update(resp_metadata)

        updated_history = list(history)
        updated_history.append({"role": "user", "content": request.message})
        updated_history.append({"role": "assistant", "content": resp_message})

        updated_collected_data["history"] = updated_history

        updated_session_payload = {
            "last_message": request.message,
            "state": resp_state,
            "collected_data": updated_collected_data,
        }
        updated_session_payload.update(intake_result.get("session_updates", {}))

        updated_session = update_session(session.session_id, updated_session_payload)

        final_message = await _maybe_polish_reply(
            updated_session,
            resp_message,
            resp_state,
            updated_session.workflow_type,
            resp_metadata,
        )

        updated_collected_data = dict(updated_session.collected_data)
        history_after = updated_collected_data.get("history", [])
        if history_after and history_after[-1]["role"] == "assistant":
            history_after[-1]["content"] = final_message
            updated_collected_data["history"] = history_after
            updated_collected_data["last_nlu"] = extracted.model_dump()
            updated_session = update_session(
                updated_session.session_id,
                {"collected_data": updated_collected_data},
            )

        return ChatResponse(
            session_id=updated_session.session_id,
            workflow_type=updated_session.workflow_type,
            state=updated_session.state,
            message=final_message,
            next_step=updated_session.state,
            metadata=resp_metadata,
            quick_replies=_build_quick_replies(resp_state, resp_metadata),
        )

    # Always re-evaluate intent — the user may switch workflows mid-conversation
    # (e.g. ask about address, then want to schedule an appointment)
    new_intent = _normalize_workflow(extracted.intent or detect_workflow(request.message))

    # Workflows that are single-turn and should not persist
    single_turn_workflows = {"practice_info", "unknown"}

    if not workflow_type or workflow_type in single_turn_workflows:
        # No active workflow or previous one was single-turn — use new intent
        # If LLM said "unknown", double-check with keyword fallback
        if new_intent == "unknown":
            keyword_intent = detect_workflow(request.message)
            if keyword_intent != "unknown":
                new_intent = keyword_intent
        workflow_type = new_intent
    elif new_intent and new_intent not in ("unknown", workflow_type):
        # User explicitly switched to a different workflow
        workflow_type = new_intent

    prefill_collected_data = dict(session.collected_data)
    prefill_collected_data["last_nlu"] = extracted.model_dump()

    if extracted.body_part and not prefill_collected_data.get("body_part"):
        prefill_collected_data["body_part"] = extracted.body_part

    if extracted.reason and not prefill_collected_data.get("reason"):
        prefill_collected_data["reason"] = extracted.reason

    if extracted.requested_day and not prefill_collected_data.get("requested_day"):
        prefill_collected_data["requested_day"] = extracted.requested_day

    if extracted.requested_time_pref and not prefill_collected_data.get("requested_time_pref"):
        prefill_collected_data["requested_time_pref"] = extracted.requested_time_pref

    if extracted.refill_medication and not prefill_collected_data.get("medication_name"):
        prefill_collected_data["medication_name"] = extracted.refill_medication

    if prefill_collected_data != dict(session.collected_data):
        session = update_session(
            session.session_id,
            {"collected_data": prefill_collected_data},
        )

    if workflow_type == "services":
        state = "PRACTICE_INFO_DONE"
        assistant_message = get_services_overview()

    elif workflow_type == "practice_info":
        state = "PRACTICE_INFO_DONE"
        practice_question = request.message

        if extracted.practice_info_topic and extracted.practice_info_topic != "general":
            practice_question = extracted.practice_info_topic

        assistant_message = answer_practice_question(practice_question)

    elif workflow_type == "scheduling":
        if session.state == "SCHEDULING_CONFIRMING":
            msg_lower = request.message.lower().strip()
            confirmed = any(w in msg_lower for w in ["yes", "yeah", "confirm", "go ahead", "sure", "ok", "correct", "book", "please"])
            declined = any(w in msg_lower for w in ["no", "nope", "cancel", "change", "different", "back", "another"])

            if confirmed:
                pending_slot_choice = session.collected_data.get("pending_slot_choice")
                if pending_slot_choice is not None:
                    booking_success, booking_result = confirm_booking_from_session_data(
                        session.collected_data, pending_slot_choice
                    )
                    booking_metadata = booking_result.get("metadata", {})
                    updated_collected_data = dict(session.collected_data)
                    updated_collected_data.update(booking_metadata)
                    updated_collected_data.pop("pending_slot_choice", None)
                    updated_collected_data["last_nlu"] = extracted.model_dump()

                    updated_history = list(_get_conversation_history(session))
                    updated_history.append({"role": "user", "content": request.message})
                    updated_history.append({"role": "assistant", "content": booking_result["message"]})
                    updated_collected_data["history"] = updated_history

                    updated_session = update_session(
                        session.session_id,
                        {
                            "last_message": request.message,
                            "workflow_type": workflow_type,
                            "state": booking_result["state"],
                            "status": "completed" if booking_success else session.status,
                            "collected_data": updated_collected_data,
                        },
                    )

                    final_message = await _maybe_polish_reply(
                        updated_session, booking_result["message"],
                        booking_result["state"], workflow_type, booking_metadata,
                    )
                    final_message = await _maybe_append_booking_guidance(final_message, booking_metadata)

                    updated_collected_data = dict(updated_session.collected_data)
                    history_after = updated_collected_data.get("history", [])
                    if history_after and history_after[-1]["role"] == "assistant":
                        history_after[-1]["content"] = final_message
                        updated_collected_data["history"] = history_after
                        updated_session = update_session(
                            updated_session.session_id, {"collected_data": updated_collected_data}
                        )

                    return ChatResponse(
                        session_id=updated_session.session_id,
                        workflow_type=updated_session.workflow_type,
                        state=updated_session.state,
                        message=final_message,
                        next_step=updated_session.state,
                        metadata=booking_metadata,
                    )

            if declined:
                # Re-show the stored slots
                stored_slots = session.collected_data.get("slots", [])
                body_part_val = session.collected_data.get("body_part", "")
                provider_name_val = session.collected_data.get("provider_name", "")
                specialty_val = session.collected_data.get("specialty", "")
                intro = f"No problem! Here are the available slots again — take your time:"
                slot_msg = build_slot_list_message(provider_name_val, specialty_val, body_part_val, stored_slots[:5], intro=intro)
                slot_meta = {"slots": stored_slots[:5], "provider_name": provider_name_val, "specialty": specialty_val, "body_part": body_part_val}

                updated_collected_data = dict(session.collected_data)
                updated_collected_data.pop("pending_slot_choice", None)
                updated_collected_data.update(slot_meta)
                updated_collected_data["last_nlu"] = extracted.model_dump()
                updated_history = list(_get_conversation_history(session))
                updated_history.append({"role": "user", "content": request.message})
                updated_history.append({"role": "assistant", "content": slot_msg})
                updated_collected_data["history"] = updated_history

                updated_session = update_session(
                    session.session_id,
                    {"last_message": request.message, "workflow_type": workflow_type, "state": "SCHEDULING_SHOWING_SLOTS", "collected_data": updated_collected_data},
                )

                return ChatResponse(
                    session_id=updated_session.session_id,
                    workflow_type=updated_session.workflow_type,
                    state=updated_session.state,
                    message=slot_msg,
                    next_step=updated_session.state,
                    metadata=slot_meta,
                    quick_replies=_build_quick_replies("SCHEDULING_SHOWING_SLOTS", slot_meta),
                )

            # Ambiguous — ask again
            pending_slot_choice = session.collected_data.get("pending_slot_choice")
            slots = session.collected_data.get("slots", [])
            slot_label = ""
            if pending_slot_choice and slots and 1 <= pending_slot_choice <= len(slots):
                s = slots[pending_slot_choice - 1]
                slot_label = format_slot_date(s["date"], s["time"])
            re_ask = f"Just to check — shall I go ahead and confirm your appointment for {slot_label}? Tap Yes to confirm or No to pick a different slot."
            return ChatResponse(
                session_id=session.session_id,
                workflow_type=session.workflow_type,
                state=session.state,
                message=re_ask,
                next_step=session.state,
                metadata={},
                quick_replies=_build_quick_replies("SCHEDULING_CONFIRMING", {}),
            )

        if session.state == "SCHEDULING_SHOWING_SLOTS":
            slots = session.collected_data.get("slots", [])
            provider_name = session.collected_data.get("provider_name", "")
            specialty = session.collected_data.get("specialty", "")
            body_part = session.collected_data.get("body_part", "")

            relative_choice = parse_relative_slot_preference(request.message, slots)
            if relative_choice is not None:
                slot_choice = relative_choice
            else:
                time_choice = parse_time_choice(request.message, slots)
                if time_choice is not None:
                    slot_choice = time_choice
                else:
                    slot_choice = parse_slot_choice(request.message)

            if slot_choice is None:
                preference_result = resolve_slot_preference(
                    user_message=request.message,
                    slots=slots,
                    provider_name=provider_name,
                    specialty=specialty,
                    body_part=body_part,
                    requested_day=extracted.requested_day,
                )

                if preference_result:
                    preference_metadata = preference_result.get("metadata", {})
                    updated_collected_data = dict(session.collected_data)
                    updated_collected_data.update(preference_metadata)
                    updated_collected_data["last_nlu"] = extracted.model_dump()

                    updated_history = list(_get_conversation_history(session))
                    updated_history.append({"role": "user", "content": request.message})
                    updated_history.append({"role": "assistant", "content": preference_result["message"]})
                    updated_collected_data["history"] = updated_history

                    updated_session = update_session(
                        session.session_id,
                        {
                            "last_message": request.message,
                            "workflow_type": workflow_type,
                            "state": preference_result["state"],
                            "collected_data": updated_collected_data,
                        },
                    )

                    return ChatResponse(
                        session_id=updated_session.session_id,
                        workflow_type=updated_session.workflow_type,
                        state=updated_session.state,
                        message=preference_result["message"],
                        next_step=updated_session.state,
                        metadata=preference_metadata,
                        quick_replies=_build_quick_replies(preference_result["state"], preference_metadata),
                    )

                # If the user asked a question mid-flow (not a slot choice),
                # answer it with the LLM and remind them to pick a slot
                if llm_service.is_enabled():
                    try:
                        llm_reply = await asyncio.wait_for(
                            llm_service.generate_general_reply(
                                user_message=request.message,
                                conversation_history=history,
                            ),
                            timeout=8,
                        )
                        if llm_reply:
                            mid_flow_message = f"{llm_reply}\n\nWhenever you're ready, just pick one of the available slots above by number, time, or preference like 'early one'."

                            updated_history = list(_get_conversation_history(session))
                            updated_history.append({"role": "user", "content": request.message})
                            updated_history.append({"role": "assistant", "content": mid_flow_message})
                            updated_collected = dict(session.collected_data)
                            updated_collected["history"] = updated_history

                            updated_session = update_session(
                                session.session_id,
                                {"collected_data": updated_collected, "last_message": request.message},
                            )

                            return ChatResponse(
                                session_id=updated_session.session_id,
                                workflow_type=updated_session.workflow_type,
                                state=updated_session.state,
                                message=mid_flow_message,
                                next_step=updated_session.state,
                                metadata={"slots": slots},
                                quick_replies=_build_quick_replies(updated_session.state, {"slots": slots}),
                            )
                    except Exception as e:
                        print(f"LLM mid-flow reply failed: {e}")

                return ChatResponse(
                    session_id=session.session_id,
                    workflow_type=session.workflow_type,
                    state=session.state,
                    message="Just pick one of the slots above — tap a button or type the number.",
                    next_step=session.state,
                    metadata={"slots": slots},
                    quick_replies=_build_quick_replies(session.state, {"slots": slots}),
                )

            missing_field = get_missing_intake_field(
                session.collected_data,
                {
                    "first_name": session.first_name,
                    "last_name": session.last_name,
                    "dob": session.dob,
                    "phone_number": session.phone_number,
                    "email": session.email,
                },
            )

            if missing_field:
                updated_collected_data = dict(session.collected_data)
                updated_collected_data["pending_intake_field"] = missing_field
                updated_collected_data["selected_slot"] = slot_choice
                updated_collected_data["last_nlu"] = extracted.model_dump()

                updated_history = list(_get_conversation_history(session))
                updated_history.append({"role": "user", "content": request.message})
                updated_history.append(
                    {"role": "assistant", "content": build_intake_prompt(missing_field)}
                )
                updated_collected_data["history"] = updated_history

                updated_session = update_session(
                    session.session_id,
                    {
                        "last_message": request.message,
                        "workflow_type": workflow_type,
                        "state": "COLLECTING_INTAKE",
                        "collected_data": updated_collected_data,
                    },
                )

                final_message = await _maybe_polish_reply(
                    updated_session,
                    build_intake_prompt(missing_field),
                    updated_session.state,
                    updated_session.workflow_type,
                    {"pending_intake_field": missing_field},
                )

                updated_collected_data = dict(updated_session.collected_data)
                history_after = updated_collected_data.get("history", [])
                if history_after and history_after[-1]["role"] == "assistant":
                    history_after[-1]["content"] = final_message
                    updated_collected_data["history"] = history_after
                    updated_session = update_session(
                        updated_session.session_id,
                        {"collected_data": updated_collected_data},
                    )

                return ChatResponse(
                    session_id=updated_session.session_id,
                    workflow_type=updated_session.workflow_type,
                    state=updated_session.state,
                    message=final_message,
                    next_step=updated_session.state,
                    metadata={"pending_intake_field": missing_field},
                )

            # Validate slot index before asking for confirmation
            all_slots = session.collected_data.get("slots", [])
            if not all_slots or slot_choice < 1 or slot_choice > len(all_slots):
                return ChatResponse(
                    session_id=session.session_id,
                    workflow_type=session.workflow_type,
                    state=session.state,
                    message=f"I didn't quite catch that — please pick a slot between 1 and {len(all_slots)}.",
                    next_step=session.state,
                    metadata={"slots": all_slots},
                    quick_replies=_build_quick_replies("SCHEDULING_SHOWING_SLOTS", {"slots": all_slots}),
                )

            pending_slot_obj = all_slots[slot_choice - 1]
            slot_label = format_slot_date(pending_slot_obj["date"], pending_slot_obj["time"])
            provider_name_c = session.collected_data.get("provider_name", "")
            specialty_c = session.collected_data.get("specialty", "")
            body_part_c = session.collected_data.get("body_part", "")

            confirm_msg = (
                f"Great choice! Just to confirm — you'd like to book an appointment with "
                f"{provider_name_c} ({specialty_c}) for your {body_part_c} on {slot_label}. "
                f"Shall I go ahead and confirm this?"
            )

            updated_collected_data = dict(session.collected_data)
            updated_collected_data["pending_slot_choice"] = slot_choice
            updated_collected_data["last_nlu"] = extracted.model_dump()

            updated_history = list(_get_conversation_history(session))
            updated_history.append({"role": "user", "content": request.message})
            updated_history.append({"role": "assistant", "content": confirm_msg})
            updated_collected_data["history"] = updated_history

            updated_session = update_session(
                session.session_id,
                {
                    "last_message": request.message,
                    "workflow_type": workflow_type,
                    "state": "SCHEDULING_CONFIRMING",
                    "collected_data": updated_collected_data,
                },
            )

            return ChatResponse(
                session_id=updated_session.session_id,
                workflow_type=updated_session.workflow_type,
                state=updated_session.state,
                message=confirm_msg,
                next_step=updated_session.state,
                metadata={},
                quick_replies=_build_quick_replies("SCHEDULING_CONFIRMING", {}),
            )

        # If intake is done but slots haven't been shown yet, show them now
        if session.state == "INTAKE_COMPLETE" and session.collected_data.get("slots"):
            stored_slots = session.collected_data.get("slots", [])
            body_part_val = session.collected_data.get("body_part", "")
            provider_name_val = session.collected_data.get("provider_name", "")
            specialty_val = session.collected_data.get("specialty", "")

            weekday = extract_weekday_preference(request.message) or normalize_requested_day(extracted.requested_day)
            display_slots = stored_slots
            if weekday:
                filtered = filter_slots_by_weekday(stored_slots, weekday)
                if filtered:
                    display_slots = filtered
            display_slots = display_slots[:5]

            intro = (
                f"Here are the available slots with {provider_name_val} ({specialty_val}) "
                f"for your {body_part_val} concern."
            )
            slot_message = build_slot_list_message(provider_name_val, specialty_val, body_part_val, display_slots, intro=intro)
            slot_metadata = {
                "slots": display_slots,
                "provider_name": provider_name_val,
                "specialty": specialty_val,
                "body_part": body_part_val,
            }

            updated_collected_data = dict(session.collected_data)
            updated_collected_data.update(slot_metadata)
            updated_collected_data["last_nlu"] = extracted.model_dump()

            updated_history = list(_get_conversation_history(session))
            updated_history.append({"role": "user", "content": request.message})
            updated_history.append({"role": "assistant", "content": slot_message})
            updated_collected_data["history"] = updated_history

            updated_session = update_session(
                session.session_id,
                {
                    "last_message": request.message,
                    "workflow_type": workflow_type,
                    "state": "SCHEDULING_SHOWING_SLOTS",
                    "collected_data": updated_collected_data,
                },
            )

            return ChatResponse(
                session_id=updated_session.session_id,
                workflow_type=updated_session.workflow_type,
                state=updated_session.state,
                message=slot_message,
                next_step=updated_session.state,
                metadata=slot_metadata,
                quick_replies=_build_quick_replies("SCHEDULING_SHOWING_SLOTS", slot_metadata),
            )

        scheduling_input = request.message

        if extracted.body_part or extracted.reason or extracted.requested_day or extracted.requested_time_pref:
            parts = []
            if extracted.reason:
                parts.append(f"reason: {extracted.reason}")
            if extracted.body_part:
                parts.append(f"body_part: {extracted.body_part}")
            if extracted.requested_day:
                parts.append(f"requested_day: {extracted.requested_day}")
            if extracted.requested_time_pref:
                parts.append(f"requested_time_pref: {extracted.requested_time_pref}")

            if parts:
                scheduling_input = f"{request.message}\n" + "\n".join(parts)

        scheduling_result = build_scheduling_response(scheduling_input)
        state = scheduling_result["state"]
        assistant_message = scheduling_result["message"]
        metadata = scheduling_result["metadata"]

        # If the NLU extracted a specific body_part that isn't in any provider's list,
        # treat it as unsupported rather than looping with the same "what's your concern?" question.
        # Only trigger on body_part (not reason) — reason is set to the full message by fallback NLU
        # and would fire even on generic scheduling phrases like "I'd like an appointment".
        if state == "SCHEDULING_NEEDS_BODY_PART" and extracted.body_part:
            body_part_lower = extracted.body_part.lower()
            is_known_unsupported = any(
                kw in body_part_lower for kw in UNSUPPORTED_CONCERN_KEYWORDS
            )
            if is_known_unsupported:
                described = extracted.body_part
                state = "SCHEDULING_UNSUPPORTED_BODY_PART"
                assistant_message = (
                    f"I'm sorry to hear you're dealing with that. Unfortunately we don't currently "
                    f"have a specialist for {described} through this system. "
                    f"Please give the office a call at {PRACTICE_INFO['phone']} "
                    f"and they'll make sure you get the right care. Is there anything else I can help with?"
                )
                metadata = {"unsupported_concern": described}
            # If body_part was extracted but isn't a known unsupported term, it's likely
            # something the provider list simply doesn't cover yet — ask normally.

        # If provider was found, collect intake BEFORE showing slots
        if state == "SCHEDULING_SHOWING_SLOTS":
            session_dict_check = {
                "first_name": session.first_name,
                "last_name": session.last_name,
                "dob": session.dob,
                "phone_number": session.phone_number,
                "email": session.email,
            }
            missing_field = get_missing_intake_field(prefill_collected_data, session_dict_check)
            if missing_field:
                provider_name_val = metadata.get("provider_name", "")
                specialty_val = metadata.get("specialty", "")
                body_part_val = metadata.get("body_part", "")
                intake_prompt = build_intake_prompt(missing_field)
                assistant_message = (
                    f"I'm sorry to hear about your {body_part_val} — I'll make sure we get you seen quickly. "
                    f"I found availability with {provider_name_val} ({specialty_val}). "
                    f"Before I pull up the slots, I just need a few quick details.\n\n{intake_prompt}"
                )
                state = "COLLECTING_INTAKE"
                metadata = {
                    **metadata,
                    "pending_intake_field": missing_field,
                }

    elif workflow_type == "refill":
        if session.state == "REFILL_CONFIRMING":
            msg_lower = request.message.lower().strip()
            confirmed = any(w in msg_lower for w in ["yes", "yeah", "confirm", "go ahead", "sure", "ok", "submit", "please", "correct"])
            declined = any(w in msg_lower for w in ["no", "nope", "cancel", "change", "different", "back", "update"])

            med_name = session.collected_data.get("medication_name", "")
            pharm_name = session.collected_data.get("pharmacy_name", "")

            if confirmed:
                refill_record = submit_refill_request(
                    session_id=session.session_id,
                    medication_name=med_name,
                    pharmacy_name=pharm_name,
                )
                state = "REFILL_SUBMITTED"
                assistant_message = (
                    f"Your refill request for **{med_name}** has been sent to **{pharm_name}**. "
                    f"The pharmacy typically processes requests within 24–48 hours. "
                    f"Is there anything else I can help you with?"
                )
                metadata = {
                    "medication_name": med_name,
                    "pharmacy_name": pharm_name,
                    "refill_request_id": refill_record.get("refill_request_id"),
                    "refill_submitted": True,
                }

                updated_collected_data = dict(session.collected_data)
                updated_collected_data.update(metadata)
                updated_collected_data["last_nlu"] = extracted.model_dump()
                updated_history = list(_get_conversation_history(session))
                updated_history.append({"role": "user", "content": request.message})
                updated_history.append({"role": "assistant", "content": assistant_message})
                updated_collected_data["history"] = updated_history

                updated_session = update_session(
                    session.session_id,
                    {
                        "last_message": request.message,
                        "workflow_type": workflow_type,
                        "state": state,
                        "status": "completed",
                        "collected_data": updated_collected_data,
                    },
                )

                final_message = await _maybe_polish_reply(
                    updated_session, assistant_message, state, workflow_type, metadata,
                )

                updated_collected_data = dict(updated_session.collected_data)
                history_after = updated_collected_data.get("history", [])
                if history_after and history_after[-1]["role"] == "assistant":
                    history_after[-1]["content"] = final_message
                    updated_collected_data["history"] = history_after
                    updated_session = update_session(
                        updated_session.session_id, {"collected_data": updated_collected_data}
                    )

                return ChatResponse(
                    session_id=updated_session.session_id,
                    workflow_type=updated_session.workflow_type,
                    state=updated_session.state,
                    message=final_message,
                    next_step=updated_session.state,
                    metadata=metadata,
                    quick_replies=_build_quick_replies("PRACTICE_INFO_DONE", {}),
                )

            if declined:
                # Reset pharmacy so user can re-enter details
                updated_collected_data = dict(session.collected_data)
                updated_collected_data.pop("pharmacy_name", None)
                update_session(session.session_id, {
                    "state": "REFILL_NEEDS_PHARMACY",
                    "collected_data": updated_collected_data,
                })
                state = "REFILL_NEEDS_PHARMACY"
                assistant_message = f"No problem! Which pharmacy would you like your {med_name} refill sent to?"
                metadata = {"medication_name": med_name}
            else:
                # Ambiguous — re-ask
                state = "REFILL_CONFIRMING"
                assistant_message = (
                    f"Just to check — shall I go ahead and submit a refill for **{med_name}** "
                    f"to **{pharm_name}**?"
                )
                metadata = {"medication_name": med_name, "pharmacy_name": pharm_name}

                updated_collected_data = dict(session.collected_data)
                updated_collected_data["last_nlu"] = extracted.model_dump()
                updated_history = list(_get_conversation_history(session))
                updated_history.append({"role": "user", "content": request.message})
                updated_history.append({"role": "assistant", "content": assistant_message})
                updated_collected_data["history"] = updated_history
                updated_session = update_session(
                    session.session_id,
                    {"last_message": request.message, "collected_data": updated_collected_data},
                )
                return ChatResponse(
                    session_id=updated_session.session_id,
                    workflow_type=updated_session.workflow_type,
                    state=updated_session.state,
                    message=assistant_message,
                    next_step=updated_session.state,
                    metadata=metadata,
                    quick_replies=_build_quick_replies("REFILL_CONFIRMING", {}),
                )

        else:
            refill_input = request.message

            if extracted.refill_medication and not session.collected_data.get("medication_name"):
                refill_input = f"{request.message}\nmedication: {extracted.refill_medication}"

            if session.state in ["REFILL_NEEDS_MEDICATION", "REFILL_NEEDS_PHARMACY"]:
                refill_result = continue_refill_flow(refill_input, session.collected_data)
            else:
                refill_result = build_refill_response(refill_input)

            state = refill_result["state"]
            assistant_message = refill_result["message"]
            metadata = refill_result["metadata"]

            # Guard: service redirected away from refill (e.g. medical advice request)
            if refill_result.get("workflow_type") in ("unknown", "GENERAL_CONVERSATION"):
                workflow_type = "unknown"
                state = "GENERAL_CONVERSATION"
                # Clear refill state so next message starts fresh
                update_session(session.session_id, {
                    "workflow_type": None,
                    "state": "GENERAL_CONVERSATION",
                })

    else:
        detected_workflow = _normalize_workflow(extracted.intent or detect_workflow(request.message))
        workflow_type = detected_workflow
        state, assistant_message = get_workflow_response(detected_workflow)

        # Low-confidence NLU: ask a clarifying question instead of guessing
        if extracted.needs_clarification and state == "GENERAL_CONVERSATION":
            assistant_message = (
                "I want to make sure I help you with the right thing — "
                "could you tell me a bit more? For example, are you looking to "
                "schedule an appointment, request a prescription refill, or find out "
                "something about our office?"
            )
            state = "GENERAL_CONVERSATION"

        # Enhancement 1: Free-form LLM conversation for unknown intents
        if state == "GENERAL_CONVERSATION" and not extracted.needs_clarification and llm_service.is_enabled():
            try:
                llm_reply = await asyncio.wait_for(
                    llm_service.generate_general_reply(
                        user_message=request.message,
                        conversation_history=history,
                    ),
                    timeout=8,
                )
                if llm_reply:
                    assistant_message = llm_reply
            except Exception as e:
                print(f"LLM general reply failed: {e}")
                pass  # fall back to hardcoded message

    collected_data = dict(session.collected_data)
    if metadata:
        collected_data.update(metadata)

    collected_data["last_nlu"] = extracted.model_dump()

    updated_history = list(_get_conversation_history(session))
    updated_history.append({"role": "user", "content": request.message})
    updated_history.append({"role": "assistant", "content": assistant_message})
    collected_data["history"] = updated_history
    normalized_workflow = _normalize_workflow(workflow_type)

    updated_session = update_session(
        session.session_id,
        {
            "last_message": request.message,
            "workflow_type": normalized_workflow if normalized_workflow != "unknown" else session.workflow_type,
            "state": state,
            "collected_data": collected_data,
        },
    )

    final_message = await _maybe_polish_reply(
        updated_session,
        assistant_message,
        state,
        workflow_type,
        metadata,
    )

    updated_collected_data = dict(updated_session.collected_data)
    history_after = updated_collected_data.get("history", [])
    if history_after and history_after[-1]["role"] == "assistant":
        history_after[-1]["content"] = final_message
        updated_collected_data["history"] = history_after
        updated_session = update_session(
            updated_session.session_id,
            {"collected_data": updated_collected_data},
        )

    return ChatResponse(
        session_id=updated_session.session_id,
        workflow_type=updated_session.workflow_type,
        state=updated_session.state,
        message=final_message,
        next_step=updated_session.state,
        metadata=metadata,
        quick_replies=_build_quick_replies(updated_session.state, metadata),
    )


async def _stream_tokens(text: str) -> AsyncGenerator[str, None]:
    """Yield each word as an SSE data event, simulating token streaming."""
    words = text.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == 0 else " " + word
        yield f"data: {json.dumps({'token': chunk})}\n\n"
        await asyncio.sleep(0.03)


@router.post("/chat/stream")
@limiter.limit("20/minute")
async def handle_chat_stream(body: ChatRequest, request: Request):
    """SSE streaming variant of /chat.
    Calls handle_chat internally and streams the final message word-by-word,
    then sends a final 'done' event with the full ChatResponse payload."""
    response: ChatResponse = await handle_chat(body, request)

    async def event_stream() -> AsyncGenerator[str, None]:
        async for token_event in _stream_tokens(response.message):
            yield token_event
        payload = response.model_dump()
        yield f"data: {json.dumps({'done': True, 'response': payload})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")