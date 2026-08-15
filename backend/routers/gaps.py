"""Gaps Router - Memory Gap 탐지"""

from fastapi import APIRouter, HTTPException

from backend.models.schemas import GapsResponse, GapItem
from backend.services.gap_detector import detect_gaps, get_gap_detail

router = APIRouter()


@router.get("", response_model=GapsResponse)
async def list_gaps():
    """탐지된 Memory Gap 목록"""
    gaps = detect_gaps()

    return GapsResponse(
        gaps=[
            GapItem(
                id=g["id"],
                event_id=g.get("event_id"),
                event_title=g.get("event_title"),
                gap_type=g["gap_type"],
                description=g["description"],
                suggested_question=g["suggested_question"],
                target_person=g.get("target_person"),
                priority=g.get("priority", 1),
            )
            for g in gaps
        ],
        total=len(gaps),
    )


@router.get("/{gap_id}")
async def gap_detail(gap_id: str):
    """Gap 상세"""
    gap = get_gap_detail(gap_id)
    if not gap:
        raise HTTPException(status_code=404, detail="Gap을 찾을 수 없습니다.")
    return gap
