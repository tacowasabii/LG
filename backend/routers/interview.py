"""Interview Router - AI Memory Interview"""

from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    InterviewStartRequest, InterviewStartResponse,
    InterviewAnswerRequest, InterviewAnswerResponse,
)
from backend.services.interview_engine import start_interview, process_answer, get_session_status

router = APIRouter()


@router.post("/start", response_model=InterviewStartResponse)
async def interview_start(request: InterviewStartRequest):
    """인터뷰 세션 시작"""
    result = await start_interview(request.target_type, request.target_id)

    return InterviewStartResponse(
        session_id=result["session_id"],
        question=result["question"],
        context=result["context"],
    )


@router.post("/answer", response_model=InterviewAnswerResponse)
async def interview_answer(request: InterviewAnswerRequest):
    """사용자 답변 제출"""
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
        message=result["message"],
    )


@router.get("/status/{session_id}")
async def interview_status(session_id: str):
    """인터뷰 세션 상태"""
    status = get_session_status(session_id)
    if not status:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return status
