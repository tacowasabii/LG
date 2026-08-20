"""Family Router — 가족 공간, 역할, 공개 범위

구성원은 그래프의 인물 노드 그대로다 (backend/services/family.py 참고).
공개 범위는 저장만 하지 않고 실제로 목록·검색에서 가려진다
(backend/services/visibility.py).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.schemas import (
    FamilySpaceResponse,
    InviteRequest,
    InviteResponse,
    JoinRequest,
    JoinResponse,
    MemberUpdateRequest,
    VisibilityRequest,
)
from backend.models.graph_models import NodeType
from backend.services import family, permissions, visibility
from backend.services.permissions import current_actor
from backend.services.graph_manager import graph_manager

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
async def update_member(
    person_id: str,
    request: MemberUpdateRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """역할 변경 · 비공개 요청 토글

    역할은 가족 관리자가 정한다. 비공개 요청은 본인도 직접 바꿀 수 있다 —
    자기가 나온 기록을 감추는 것은 남이 대신 결정할 일이 아니다.
    """
    if request.role is not None:
        permissions.require_admin(actor)
    elif not (actor and actor["id"] == person_id):
        permissions.require_admin(actor)

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
async def create_invite(
    request: InviteRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """초대 링크 발급 (72시간 뒤 만료)"""
    permissions.require_admin(actor)

    invite = family.create_invite(person_id=request.person_id)
    return InviteResponse(**invite)


@router.get("/invite/{code}")
async def check_invite(code: str):
    """초대 코드가 아직 쓸 수 있는지 (참여 화면이 먼저 물어본다)

    누가 지목된 초대인지 알려 준다. 이름을 다시 입력하게 하면, 이미 그래프에
    있는 사람이 중복으로 생긴다.
    """
    invite = family.find_invite(code)
    if not invite:
        raise HTTPException(
            status_code=404,
            detail="쓸 수 없는 초대 코드입니다. 만료됐거나 이미 사용된 코드입니다.",
        )

    person = graph_manager.get_node(invite.get("person_id") or "")
    return {
        "code": invite["code"],
        "expires_at": invite["expires_at"],
        "person_id": invite.get("person_id"),
        "person_name": person.get("name") if person else None,
        "space_name": family.get_space()["space_name"],
    }


@router.post("/join", response_model=JoinResponse)
async def join_space(request: JoinRequest):
    """초대 코드로 참여한다

    역할 가드를 걸지 않는다. 들어오려는 사람은 아직 이 공간의 구성원이 아니고,
    관문은 초대 코드 자체다. 코드는 한 번 쓰면 소진된다.
    """
    try:
        result = family.join(
            request.code,
            person_id=request.person_id,
            name=request.name,
            relation=request.relation,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result.get("member"):
        raise HTTPException(status_code=404, detail="참여한 사람을 찾을 수 없습니다.")

    return JoinResponse(space_name=result["space_name"], member=result["member"])


@router.put("/media/{media_id}/visibility")
async def set_visibility(
    media_id: str,
    request: VisibilityRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """기록 하나의 공개 범위를 정한다 — 올린 사람이나 가족 관리자만"""
    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="그런 기록이 없습니다.")

    permissions.require_owner_of(node, actor, what="기록의 공개 범위")

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
