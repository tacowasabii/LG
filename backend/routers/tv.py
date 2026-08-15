"""TV Router - TV Memory Journey"""

from fastapi import APIRouter, HTTPException

from backend.models.schemas import TVJourneyRequest, TVJourneyResponse, TVSlide
from backend.services.tv_curator import create_journey, get_journey

router = APIRouter()


@router.post("/journey", response_model=TVJourneyResponse)
async def create_tv_journey(request: TVJourneyRequest):
    """TV Journey 생성"""
    result = await create_journey(request.query, request.style)

    return TVJourneyResponse(
        id=result["id"],
        title=result["title"],
        slides=[
            TVSlide(
                type=s["type"],
                media_id=s.get("media_id"),
                file_path=s.get("file_path"),
                caption=s.get("caption", ""),
                event_id=s.get("event_id"),
                event_title=s.get("event_title"),
                date=s.get("date"),
            )
            for s in result["slides"]
        ],
        narration=result.get("narration", ""),
        total_duration_sec=result.get("total_duration_sec", 0),
    )


@router.get("/journey/{journey_id}", response_model=TVJourneyResponse)
async def get_tv_journey(journey_id: str):
    """저장된 Journey 조회"""
    result = get_journey(journey_id)
    if not result:
        raise HTTPException(status_code=404, detail="Journey를 찾을 수 없습니다.")

    return TVJourneyResponse(
        id=result["id"],
        title=result["title"],
        slides=[
            TVSlide(
                type=s["type"],
                media_id=s.get("media_id"),
                file_path=s.get("file_path"),
                caption=s.get("caption", ""),
                event_id=s.get("event_id"),
                event_title=s.get("event_title"),
                date=s.get("date"),
            )
            for s in result["slides"]
        ],
        narration=result.get("narration", ""),
        total_duration_sec=result.get("total_duration_sec", 0),
    )
