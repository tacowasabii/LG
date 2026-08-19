"""Film Router — Memory Film 구성과 기념일 큐레이션"""

from fastapi import APIRouter, HTTPException

from backend.models.schemas import (
    AnniversaryItem,
    FilmRequest,
    FilmResponse,
)
from backend.services import film_composer

router = APIRouter()


@router.post("", response_model=FilmResponse)
async def compose_film(request: FilmRequest):
    """사건 하나를 30~60초 이야기로 구성

    장면마다 원본 기록과 적용된 효과를 함께 내려보낸다. 화면이 그것을 감추지
    않고 표시하는 것이 기획안의 진정성 원칙이다.
    """
    board = await film_composer.compose(
        request.event_id,
        length_sec=request.length_sec,
        audience=request.audience,
    )

    if not board:
        raise HTTPException(
            status_code=404,
            detail="이 사건으로는 아직 이야기를 만들 수 없습니다. 사진이나 영상을 먼저 연결해주세요.",
        )

    return FilmResponse(**board)


@router.get("/anniversaries", response_model=list[AnniversaryItem])
async def list_anniversaries(limit: int = 4):
    """다가오는 기념일 — TV 대기화면이 먼저 말을 걸 근거"""
    return [AnniversaryItem(**item) for item in film_composer.anniversaries(limit=limit)]
