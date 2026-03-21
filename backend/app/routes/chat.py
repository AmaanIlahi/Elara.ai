import asyncio
from fastapi import APIRouter, HTTPException
from typing import Optional

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import detect_workflow, get_workflow_response
from app.services.intake_service import (
    build_intake_prompt,
    continue_intake_flow,
    extract_field_value,
    get_missing_intake_field,
)
from app.services.llm_service import LLMService
from app.services.nlu_service import NLUService
from app.services.practice_service import answer_practice_question
from app.services.refill_service import build_refill_response, continue_refill_flow
from app.services.scheduling_service import (
    build_scheduling_response,
    confirm_booking_from_session_data,
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
    "REFILL_STARTED",
    "REFILL_NEEDS_MEDICATION",
    "REFILL_NEEDS_PHARMACY",
    "SCHEDULING_STARTED",
    "SCHEDULING_NEEDS_BODY_PART",
    "SCHEDULING_UNSUPPORTED_BODY_PART",
    "SCHEDULING_SHOWING_SLOTS",
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
async def handle_chat(request: ChatRequest):
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
                            ack_message = f"Got it, I captured {filled_count} details. {build_intake_prompt(next_missing)}"

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
                        # All fields captured via LLM — go straight to booking
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
                            booking_success, booking_result = confirm_booking_from_session_data(
                                multi_collected, selected_slot,
                            )
                            booking_metadata = booking_result.get("metadata", {})
                            multi_collected.update(booking_metadata)

                            updated_history = list(history)
                            updated_history.append({"role": "user", "content": request.message})
                            updated_history.append({"role": "assistant", "content": booking_result["message"]})
                            multi_collected["history"] = updated_history

                            final_session = update_session(
                                updated_session.session_id,
                                {
                                    "last_message": request.message,
                                    "state": booking_result["state"],
                                    "status": "completed" if booking_success else updated_session.status,
                                    "collected_data": multi_collected,
                                    **multi_session_updates,
                                },
                            )

                            final_msg = await _maybe_polish_reply(
                                final_session, booking_result["message"],
                                booking_result["state"], final_session.workflow_type, booking_metadata,
                            )
                            final_msg = await _maybe_append_booking_guidance(final_msg, booking_metadata)

                            return ChatResponse(
                                session_id=final_session.session_id,
                                workflow_type=final_session.workflow_type,
                                state=final_session.state,
                                message=final_msg,
                                next_step=final_session.state,
                                metadata=booking_metadata,
                            )

                        # No slot selected yet, acknowledge and continue
                        ack = f"Got it, I captured all your details. Thank you!"
                        updated_history = list(history)
                        updated_history.append({"role": "user", "content": request.message})
                        updated_history.append({"role": "assistant", "content": ack})
                        multi_collected["history"] = updated_history

                        final_session = update_session(
                            updated_session.session_id,
                            {
                                "last_message": request.message,
                                "state": "INTAKE_COMPLETE",
                                "collected_data": multi_collected,
                            },
                        )

                        return ChatResponse(
                            session_id=final_session.session_id,
                            workflow_type=final_session.workflow_type,
                            state=final_session.state,
                            message=ack,
                            next_step=final_session.state,
                            metadata={},
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
                booking_success, booking_result = confirm_booking_from_session_data(
                    updated_collected_data,
                    selected_slot,
                )

                booking_metadata = booking_result.get("metadata", {})
                updated_collected_data.update(booking_metadata)
                updated_collected_data.pop("pending_intake_field", None)

                updated_history = list(history)
                updated_history.append({"role": "user", "content": request.message})
                updated_history.append({"role": "assistant", "content": booking_result["message"]})
                updated_collected_data["history"] = updated_history

                updated_session_payload = {
                    "last_message": request.message,
                    "workflow_type": session.workflow_type,
                    "state": booking_result["state"],
                    "status": "completed" if booking_success else session.status,
                    "collected_data": updated_collected_data,
                }
                updated_session_payload.update(intake_result.get("session_updates", {}))

                updated_session = update_session(session.session_id, updated_session_payload)

                final_message = await _maybe_polish_reply(
                    updated_session,
                    booking_result["message"],
                    booking_result["state"],
                    updated_session.workflow_type,
                    booking_metadata,
                )
                final_message = await _maybe_append_booking_guidance(final_message, booking_metadata)

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
                    metadata=booking_metadata,
                )

        updated_history = list(history)
        updated_history.append({"role": "user", "content": request.message})
        updated_history.append({"role": "assistant", "content": intake_result["message"]})

        updated_collected_data["history"] = updated_history

        updated_session_payload = {
            "last_message": request.message,
            "state": intake_result["state"],
            "collected_data": updated_collected_data,
        }
        updated_session_payload.update(intake_result.get("session_updates", {}))

        updated_session = update_session(session.session_id, updated_session_payload)

        final_message = await _maybe_polish_reply(
            updated_session,
            intake_result["message"],
            intake_result["state"],
            updated_session.workflow_type,
            intake_result.get("metadata", {}),
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
            metadata=intake_result.get("metadata", {}),
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

    if extracted.refill_medication and not prefill_collected_data.get("medication"):
        prefill_collected_data["medication"] = extracted.refill_medication

    if prefill_collected_data != dict(session.collected_data):
        session = update_session(
            session.session_id,
            {"collected_data": prefill_collected_data},
        )

    if workflow_type == "practice_info":
        state = "PRACTICE_INFO_STARTED"
        practice_question = request.message

        if extracted.practice_info_topic and extracted.practice_info_topic != "general":
            practice_question = extracted.practice_info_topic

        assistant_message = answer_practice_question(practice_question)

    elif workflow_type == "scheduling":
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
                            )
                    except Exception as e:
                        print(f"LLM mid-flow reply failed: {e}")

                return ChatResponse(
                    session_id=session.session_id,
                    workflow_type=session.workflow_type,
                    state=session.state,
                    message="Please choose one of the available slots by number, time, or preference like 'early one'.",
                    next_step=session.state,
                    metadata={"slots": slots},
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

            success, result = confirm_booking_from_session_data(
                session.collected_data,
                slot_choice,
            )
            state = result["state"]
            assistant_message = result["message"]
            metadata = result["metadata"]

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
                    "status": "completed" if success else session.status,
                    "collected_data": updated_collected_data,
                },
            )

            final_message = await _maybe_polish_reply(
                updated_session,
                assistant_message,
                state,
                workflow_type,
                metadata,
            )
            final_message = await _maybe_append_booking_guidance(final_message, metadata)

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

    elif workflow_type == "refill":
        refill_input = request.message

        if extracted.refill_medication and not session.collected_data.get("medication"):
            refill_input = f"{request.message}\nmedication: {extracted.refill_medication}"

        if session.state in ["REFILL_NEEDS_MEDICATION", "REFILL_NEEDS_PHARMACY"]:
            refill_result = continue_refill_flow(refill_input, session.collected_data)
        else:
            refill_result = build_refill_response(refill_input)

        state = refill_result["state"]
        assistant_message = refill_result["message"]
        metadata = refill_result["metadata"]

    else:
        detected_workflow = _normalize_workflow(extracted.intent or detect_workflow(request.message))
        workflow_type = detected_workflow
        state, assistant_message = get_workflow_response(detected_workflow)

        # Enhancement 1: Free-form LLM conversation for unknown intents
        if state == "GENERAL_CONVERSATION" and llm_service.is_enabled():
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
    )