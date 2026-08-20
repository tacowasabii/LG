"""Chat Router - Memory Chat"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.models.schemas import ChatRequest, ChatResponse
from backend.services.chat_engine import process_chat, process_chat_stream

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
        llm_used=result["llm_used"],
        model=result.get("model"),
        provider=result.get("provider"),
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """같은 답변을 토큰 단위로 흘려보낸다 (SSE)

    답변 전체를 기다리면 화면이 10~20초 비어 있다. 근거는 모델을 부르기 전에
    정해지므로 meta로 먼저 보내고, 문장은 delta로 이어 보낸다.

    프록시가 중간에서 버퍼링하면 스트리밍이 의미를 잃는다 — X-Accel-Buffering을
    끄고 캐시도 막는다.
    """

    async def events():
        async for event in process_chat_stream(
            request.query, request.conversation_id, request.viewer_id
        ):
            kind = event.pop("type")
            body = json.dumps(event, ensure_ascii=False)
            yield f"event: {kind}\ndata: {body}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
