"""Family Router — 가족 공간, 역할, 공개 범위

구성원은 그래프의 인물 노드 그대로다 (backend/services/family.py 참고).
공개 범위는 저장만 하지 않고 실제로 목록·검색에서 가려진다
(backend/services/visibility.py).
"""

from fastapi import APIRouter, HTTPException, Query

from backend.models.schemas import (
    FamilySpaceResponse,
    InviteRequest,
    InviteResponse,
    MemberUpdateRequest,
    VisibilityRequest,
)
from backend.services import family, visibility

router = APIRouter()


@router.get("", response_model=FamilySpaceResponse)
async def get_space(viewer_id: str = Query(None, description="지금 보는 사람")):
    """가족 공간 — 구성원·역할·초대, 그리고 이 사람에게 몇 개가 가려지는지"""
    space = family.get_space()
    return FamilySpaceResponse(
        space_name=space["space_name"],
        members=space["members"],
        invites=space["invites"],
        ownership=family.ownership_summary(),
        visibility=visibility.summary(viewer_id),
    )


@router.put("/member/{person_id}")
async def update_member(person_id: str, request: MemberUpdateRequest):
    """역할 변경 · 비공개 요청 토글"""
    try:
        member = family.update_member(
            person_id,
            role=request.role,
            private_request=request.private_request,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not member:
        raise HTTPException(status_code=404, detail="그런 인물이 없습니다.")

    return member


@router.post("/invite", response_model=InviteResponse)
async def create_invite(request: InviteRequest):
    """초대 링크 발급 (72시간 뒤 만료)"""
    invite = family.create_invite(person_id=request.person_id)
    return InviteResponse(**invite)


@router.put("/media/{media_id}/visibility")
async def set_visibility(media_id: str, request: VisibilityRequest):
    """기록 하나의 공개 범위를 정한다"""
    try:
        node = family.set_media_visibility(
            media_id,
            visibility=request.visibility,
            allowed_ids=request.allowed_ids,
            owner_id=request.owner_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not node:
        raise HTTPException(status_code=404, detail="그런 기록이 없습니다.")

    return {
        "media_id": media_id,
        "visibility": node.get("visibility"),
        "allowed_ids": node.get("allowed_ids", []),
        "owner_id": node.get("owner_id"),
    }


@router.get("/media/{media_id}/cascade")
async def delete_cascade(media_id: str):
    """이 원본을 지우면 무엇이 함께 사라지는지 (지우기 전에 보여준다)"""
    preview = family.delete_cascade_preview(media_id)
    if not preview:
        raise HTTPException(status_code=404, detail="그런 기록이 없습니다.")
    return preview
