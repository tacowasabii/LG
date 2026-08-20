"""Memories Router — 추억 만들기 · 기억 이어가기

예전 `/api/graph/verify` 와 `/api/gaps` 가 하던 자리를 대신한다. 그 둘은
"가족이 처리해야 할 일"을 목록으로 내려줬다. 여기는 처리할 일이 없다.

    POST /api/memories/draft        올린 사진·영상으로 AI 초안
    POST /api/memories             추억 만들기 (즉시 게시)
    GET  /api/memories/feed        기억 이어가기 목록
    GET  /api/memories/{id}        추억 상세
    POST /api/memories/{id}/echo   나도 기억나요 (토글)
    POST /api/memories/{id}/memory 내 기억 더하기
    DEL  /api/memories/{id}/memory/{memory_id}  내가 남긴 기억 지우기
    POST /api/memories/{id}/media  기존 추억에 사진·영상 추가
    POST /api/memories/{id}/story  함께 기억한 이야기 만들기
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.graph_models import SourceType
from backend.models.schemas import (
    ContributionRequest,
    MemoryCreateRequest,
    MemoryDraftRequest,
    MemoryMediaRequest,
)
from backend.services import memories, memory_drafter, permissions, visibility
from backend.services.permissions import current_actor

router = APIRouter()


def _viewer(viewer_id: Optional[str], actor: Optional[dict]) -> Optional[str]:
    return viewer_id or (actor["id"] if actor else None)


@router.post("/draft")
async def draft_memory(
    request: MemoryDraftRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """올린 사진·영상에서 추억 초안을 만든다

    촬영 시점·좌표·등장인물·기존 가족 기록을 읽어 제목·날짜·장소·설명을 채운다.
    확정이 아니다 — 사용자가 고치고 저장할 때 비로소 추억이 된다.

    여러 사건에 걸친 사진이면 날짜·장소로 갈라 묶음마다 초안 하나를 돌려준다.
    "같은 사건인 사진만 골라 올리세요"를 사용자에게 요구하지 않기 위한 것이다.
    """
    permissions.require_writer(actor)
    groups = await memory_drafter.draft_groups(
        request.media_ids, _viewer(None, actor), merge=request.merge
    )
    return {
        "groups": groups,
        "total": len(groups),
        # 갈랐는가. 화면이 "2개 묶음으로 갈랐어요"를 말할 수 있게.
        "grouped": len(groups) > 1,
    }


@router.post("")
async def create_memory(
    request: MemoryCreateRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """추억을 만든다 (다른 가족의 확인을 기다리지 않는다)"""
    permissions.require_writer(actor)

    author_id = request.author_id or (actor["id"] if actor else None)
    if not author_id:
        raise HTTPException(status_code=400, detail="누가 만드는 추억인지 알 수 없습니다.")

    event = memories.create_memory(
        author_id=author_id,
        title=request.title,
        description=request.description or "",
        date_start=request.date_start,
        place_id=request.place_id,
        place_name=request.place_name,
        person_ids=request.person_ids,
        media_ids=request.media_ids,
        lat=request.lat,
        lng=request.lng,
    )
    if not event:
        raise HTTPException(status_code=400, detail="추억을 만들지 못했습니다.")

    detail = memories.detail(event["id"], author_id)
    return {
        "event_id": event["id"],
        "memory": detail,
        "message": "가족 공간에 올라갔어요. 다른 가족의 확인을 기다리지 않습니다.",
    }


@router.get("/feed")
async def memory_feed(
    viewer_id: str = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
    actor: Optional[dict] = Depends(current_actor),
):
    """기억 이어가기 목록

    확인 요청 목록이 아니다. 아무 행동을 하지 않아도 된다.
    """
    viewer = _viewer(viewer_id, actor)
    items = memories.feed(viewer)
    return {
        "items": items,
        "total": len(items),
        # 내가 아직 아무 말도 얹지 않은 남의 추억 (강요가 아니라 안내다)
        "open_count": len([i for i in items if not i["mine"] and not i["i_added"]]),
    }


@router.get("/{event_id}")
async def memory_detail(
    event_id: str,
    viewer_id: str = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
    actor: Optional[dict] = Depends(current_actor),
):
    """추억 상세 (사진 · 정보 · 최초 기억 · 가족이 더한 기억 · 함께 기억한 이야기)"""
    detail = memories.detail(event_id, _viewer(viewer_id, actor))
    if not detail:
        raise HTTPException(status_code=404, detail="추억을 찾을 수 없습니다.")
    return detail


@router.post("/{event_id}/echo")
async def echo_memory(
    event_id: str,
    person_id: str = Query(None, description="누가 눌렀는지 (없으면 지금 쓰는 사람)"),
    actor: Optional[dict] = Depends(current_actor),
):
    """나도 기억나요 (다시 누르면 취소된다)"""
    permissions.require_writer(actor)

    who = person_id or (actor["id"] if actor else None)
    if not who:
        raise HTTPException(status_code=400, detail="누가 누른 것인지 알 수 없습니다.")

    result = memories.toggle_echo(event_id, who)
    if not result:
        raise HTTPException(status_code=404, detail="추억 또는 인물을 찾을 수 없습니다.")

    result["message"] = (
        "함께 기억한다고 남겼어요." if result["echoed"] else "기억나요 표시를 지웠어요."
    )
    return result


@router.post("/{event_id}/memory")
async def add_memory(
    event_id: str,
    request: ContributionRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """내 기억 더하기

    원본을 고치지 않는다. 사진·영상·음성을 함께 올렸으면 그 기록도 이 기억의
    근거로 이어진다.

    음성으로 남긴 경우(source_type=ai_stt) AI가 읽기 좋은 문장으로 정리하지만
    원문은 그대로 보존한다 (기획안 07).
    """
    permissions.require_writer(actor)

    person_id = request.person_id or (actor["id"] if actor else None)
    if not person_id:
        raise HTTPException(status_code=400, detail="누구의 기억인지 알 수 없습니다.")

    content = (request.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="기억할 내용을 적어주세요.")

    polished = None
    polished_by_ai = False
    if request.source_type == SourceType.AI_STT.value:
        polished, polished_by_ai = await memories.polish(content)
        if polished == content:
            polished = None

    memory = memories.add_contribution(
        event_id,
        person_id,
        content,
        media_ids=request.media_ids,
        differs=bool(request.differs),
        source_type=request.source_type or SourceType.USER_INPUT.value,
        polished=polished,
        audio_media_id=request.audio_media_id,
    )
    if not memory:
        raise HTTPException(status_code=404, detail="추억 또는 인물을 찾을 수 없습니다.")

    return {
        "event_id": event_id,
        "memory_id": memory["id"],
        "polished": memory.get("polished"),
        "polished_by_ai": polished_by_ai,
        "state": memories.state_of(event_id, person_id),
        "message": "기억을 더했어요. 원래 기록은 그대로 있습니다.",
    }


@router.delete("/{event_id}/memory/{memory_id}")
async def delete_memory(
    event_id: str,
    memory_id: str,
    actor: Optional[dict] = Depends(current_actor),
):
    """내가 남긴 기억 지우기 (남긴 사람이나 가족 관리자만)

    지우는 것은 문장이다. 함께 올린 사진·영상·목소리는 이 추억에 남는다 — 원본은
    사진첩에서 지운다. 그래서 응답이 몇 개가 남았는지 밝힌다. "지웠습니다" 한
    마디로 끝내면 사용자는 목소리까지 사라진 줄 안다.

    남의 기억을 지우려 하면 서버가 그 이유를 밝히며 막는다(403). 화면은 단추를
    미리 감추지 않는다 — 왜 못 지우는지가 단추가 없는 것보다 쓸모 있고, 권한
    규칙을 두 곳에 두면 어긋난다 (미디어 삭제와 같은 방식이다).
    """
    memory = memories.attached_memory(event_id, memory_id)
    # 볼 수 없는 기억의 존재를 삭제 응답으로 알려주지 않는다 (media.py와 같다)
    if not memory or not visibility.can_view(memory, actor["id"] if actor else None):
        raise HTTPException(status_code=404, detail="이 추억에 그 기억이 없습니다.")

    permissions.require_owner_of(memory, actor, what="기억")

    result = memories.delete_memory(event_id, memory_id)
    if not result:
        raise HTTPException(status_code=404, detail="이 추억에 그 기억이 없습니다.")

    message = "기억을 지웠습니다."
    if result["kept_media"]:
        message += f" 함께 올린 기록 {len(result['kept_media'])}개는 이 추억에 남아 있습니다."
    if result["story_cleared"]:
        message += " 함께 기억한 이야기는 이 기억을 담고 있어 함께 지웠습니다."

    return {
        **result,
        "state": memories.state_of(event_id, actor["id"] if actor else None),
        "message": message,
    }


@router.post("/{event_id}/media")
async def add_media_to_memory(
    event_id: str,
    request: MemoryMediaRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """기존 추억에 사진·영상을 추가한다 (사용자가 고른 경우에만)

    AI가 관련 있어 보인다고 알려 주더라도 자동으로 붙이지 않는다. 이 요청이
    "기존 추억에 추가"를 누른 결과다.
    """
    permissions.require_writer(actor)

    attached = memories.attach_media(event_id, request.media_ids)
    if not attached:
        raise HTTPException(status_code=404, detail="추억 또는 기록을 찾을 수 없습니다.")

    return {
        "event_id": event_id,
        "attached": attached,
        "message": f"기록 {len(attached)}개를 이 추억에 더했어요.",
    }


@router.post("/{event_id}/story")
async def compose_story(
    event_id: str,
    viewer_id: str = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
    actor: Optional[dict] = Depends(current_actor),
):
    """함께 기억한 이야기 만들기

    여러 사람의 기억에서 공통된 내용과 서로 다른 관점을 함께 서술한다.
    AI는 누가 맞는지 판단하지 않는다.
    """
    permissions.require_writer(actor)

    result = await memories.compose_together_story(event_id, _viewer(viewer_id, actor))
    if not result:
        raise HTTPException(
            status_code=400,
            detail="아직 엮을 기억이 없습니다. 가족이 기억을 더하면 이야기를 만들 수 있어요.",
        )
    return result
