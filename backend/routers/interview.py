"""Interview Router - AI Memory Interview"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.models.schemas import (
    InterviewStartRequest, InterviewStartResponse,
    InterviewAnswerRequest, InterviewAnswerResponse,
)
from backend.services import permissions
from backend.services.permissions import current_actor
from backend.services.interview_engine import start_interview, process_answer, get_session_status

router = APIRouter()


@router.post("/start", response_model=InterviewStartResponse)
async def interview_start(
    request: InterviewStartRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """인터뷰 세션 시작

    누가 답할지를 시작하는 자리에서 정한다. 이것을 넘기지 않던 동안 인터뷰는
    기억을 남기지 않은 아무 참여자를 대상으로 골랐고, 아빠로 로그인한 화면이
    "서연님, 기억나세요?"라고 물었다.
    """
    speaker_id = request.speaker_id or (actor or {}).get("id")
    result = await start_interview(request.target_type, request.target_id, speaker_id)

    return InterviewStartResponse(
        session_id=result["session_id"],
        question=result["question"],
        context=result["context"],
    )


@router.post("/answer", response_model=InterviewAnswerResponse)
async def interview_answer(
    request: InterviewAnswerRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """사용자 답변 제출"""
    permissions.require_writer(actor)

    result = await process_answer(
        request.session_id,
        request.answer,
        speaker_id=request.speaker_id,
        audio_media_id=request.audio_media_id,
    )

    return InterviewAnswerResponse(
        session_id=result["session_id"],
        next_question=result["next_question"],
        is_complete=result["is_complete"],
        updated_nodes=result["updated_nodes"],
        extracted=result.get("extracted"),
        message=result["message"],
    )


@router.get("/status/{session_id}")
async def interview_status(session_id: str):
    """인터뷰 세션 상태"""
    status = get_session_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return status
