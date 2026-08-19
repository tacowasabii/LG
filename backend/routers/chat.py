"""Chat Router - Memory Chat"""

from fastapi import APIRouter

from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.chat_engine import process_chat

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """자연어 질의 → 답변 + 근거 미디어/이벤트"""
    result = await process_chat(request.query, request.conversation_id, request.viewer_id)

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        confidence=result["confidence"],
        conversation_id=result["conversation_id"],
    )
