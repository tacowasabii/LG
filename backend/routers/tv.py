"""TV Router - TV Memory Journey"""

from fastapi import APIRouter, HTTPException

from backend.models.schemas import TVJourneyRequest, TVJourneyResponse, TVSlide
from backend.services.tv_curator import create_journey, get_journey

router = APIRouter()


def _slide(raw: dict) -> TVSlide:
    """큐레이터가 만든 슬라이드를 응답 모델로 옮긴다

    필드를 하나씩 적는다. 예전에는 여기서 미세 모션 필드(motion_url·motion_poster
    ·subject_preserved·motion_label)를 빼먹어서, 큐레이터가 실어 보낸 클립이
    라우터에서 조용히 버려졌다 — 거실 화면은 만들어 둔 클립을 쓰지 못하고
    카메라 움직임만 걸었다. 필드를 늘릴 때 이 함수도 같이 늘어나야 한다.
    """
    return TVSlide(
        type=raw["type"],
        media_id=raw.get("media_id"),
        file_path=raw.get("file_path"),
        caption=raw.get("caption", ""),
        event_id=raw.get("event_id"),
        event_title=raw.get("event_title"),
        date=raw.get("date"),
        motion_url=raw.get("motion_url"),
        motion_poster=raw.get("motion_poster"),
        subject_preserved=bool(raw.get("subject_preserved")),
        motion_label=raw.get("motion_label"),
        # 가족이 더한 기억에서 온 맥락 (services/memory_context.py)
        context_caption=raw.get("context_caption", ""),
        context_contributor=raw.get("context_contributor"),
        context_source=raw.get("context_source", ""),
        context_media_ids=raw.get("context_media_ids") or [],
    )


def _journey(result: dict) -> TVJourneyResponse:
    return TVJourneyResponse(
        id=result["id"],
        title=result["title"],
        slides=[_slide(s) for s in result["slides"]],
        narration=result.get("narration", ""),
        # 큐레이터가 고른 배경 음악의 무드. 위 _slide와 같은 이유로 여기 적는다 —
        # 빼먹으면 서버가 정한 것이 라우터에서 조용히 버려진다.
        music=result.get("music"),
        total_duration_sec=result.get("total_duration_sec", 0),
    )


@router.post("/journey", response_model=TVJourneyResponse)
async def create_tv_journey(request: TVJourneyRequest):
    """TV Journey 생성

    TV는 미세 모션 클립을 만들지 않는다. Film이 만들어 둔 것을 쓰기만 한다 —
    리모컨으로 넘기는 자리라 40초를 기다릴 수 없고, 넘기는 것만으로 돈이
    나가면 안 된다.

    event_ids가 오면 그 추억들의 사진만 쓴다 (TV 메뉴의 타일). 없으면 예전처럼
    query를 규칙으로 해석한다 — 채팅·검색에서 문장으로 부르는 길이다.
    """
    return _journey(
        await create_journey(request.query, request.style, request.event_ids)
    )


@router.get("/journey/{journey_id}", response_model=TVJourneyResponse)
async def get_tv_journey(journey_id: str):
    """저장된 Journey 조회"""
    result = get_journey(journey_id)
    if not result:
        raise HTTPException(status_code=404, detail="Journey를 찾을 수 없습니다.")
    return _journey(result)
