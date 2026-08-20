"""Graph Router - Graph 조회, Person/Event CRUD"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.schemas import (
    GraphResponse, PersonCreate, PersonResponse,
    EventResponse, EventListItem, PersonRef, PlaceRef,
)
from backend.models.graph_models import (
    PersonNode, NodeType, MediaType, MemoryState,
)
from backend.services import memories, permissions, visibility
from backend.services.permissions import current_actor
from backend.services.graph_manager import graph_manager

router = APIRouter()


@router.get("", response_model=GraphResponse)
async def get_full_graph():
    """전체 Graph 반환 (노드 + 엣지)"""
    data = graph_manager.get_full_graph()
    return GraphResponse(nodes=data["nodes"], edges=data["edges"])


@router.get("/events", response_model=list[EventListItem])
async def list_events(
    viewer_id: str = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
):
    """이벤트 목록 (타임라인 · 지도 · TV 공용)

    장소 좌표, 참여자, 썸네일, 기억·음성 개수, 기억이 쌓인 정도까지 한 번에 내려준다.
    화면이 사건마다 상세를 다시 부르거나 목데이터로 메우지 않게 하는 것이 목적이다.
    """
    events = graph_manager.get_events()

    result = []
    for event in sorted(events, key=lambda e: e.get("date_start", "") or "", reverse=True):
        connected = graph_manager.get_connected_nodes(event["id"])
        participants = [n for n in connected if n.get("node_type") == NodeType.PERSON]
        # 볼 수 없는 원본은 썸네일·개수에서 모두 빠진다 (기획안 08장)
        media = visibility.filter_media(
            [n for n in connected if n.get("node_type") == NodeType.MEDIA], viewer_id
        )
        # 기억 문장도 공개 범위를 지난다 (원본만 가리고 문장을 그대로 세면
        # 개수로 존재가 드러난다)
        memory_nodes = visibility.filter_memories(
            [n for n in connected if n.get("node_type") == NodeType.MEMORY], viewer_id
        )
        places = [n for n in connected if n.get("node_type") == NodeType.PLACE]

        # 사건의 대표 장소. location_id가 있으면 그것을 우선한다
        # (엣지로만 이어진 장소가 여러 개일 수 있다).
        place_node = graph_manager.get_node(event.get("location_id") or "") or (
            places[0] if places else None
        )

        photos = [m for m in media if m.get("media_type") != MediaType.AUDIO]
        audios = [m for m in media if m.get("media_type") == MediaType.AUDIO]

        state = memories.state_of(event["id"], viewer_id) or {}

        result.append(EventListItem(
            id=event["id"],
            title=event.get("title", ""),
            date_start=event.get("date_start"),
            date_end=event.get("date_end"),
            location_name=place_node.get("name") if place_node else None,
            participant_count=len(participants),
            media_count=len(media),
            place=PlaceRef(
                id=place_node["id"],
                name=place_node.get("name", ""),
                lat=place_node.get("lat"),
                lng=place_node.get("lng"),
            ) if place_node else None,
            participants=[
                PersonRef(
                    id=p["id"],
                    name=p.get("name", ""),
                    relation=p.get("relation"),
                    thumbnail_url=p.get("thumbnail_url"),
                )
                for p in participants
            ],
            media_thumbs=[
                m.get("thumbnail_path") or m.get("file_path", "")
                for m in photos[:3]
                if m.get("thumbnail_path") or m.get("file_path")
            ],
            memory_count=len(memory_nodes),
            voice_count=len(audios),
            state=state.get("state", MemoryState.ALONE.value),
            echo_count=state.get("echo_count", 0),
        ))

    return result


@router.get("/event/{event_id}", response_model=EventResponse)
async def get_event_detail(
    event_id: str,
    viewer_id: str = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
    actor: Optional[dict] = Depends(current_actor),
):
    """이벤트 상세

    이 화면이 사건의 사진을 펼쳐 보여주므로, 목록과 같은 판정을 지나야 한다.
    예전에는 여기만 걸러지지 않아서 비공개로 바꾼 사진이 사건을 펼치면 보였다.
    """
    detail = graph_manager.get_event_detail(event_id)
    if not detail:
        raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다.")

    viewer = viewer_id or (actor["id"] if actor else None)
    detail["media"] = visibility.filter_media(detail.get("media", []), viewer)
    detail["memories"] = visibility.filter_memories(detail.get("memories", []), viewer)

    return EventResponse(
        id=detail["id"],
        title=detail.get("title", ""),
        description=detail.get("description", ""),
        date_start=detail.get("date_start"),
        date_end=detail.get("date_end"),
        location=detail.get("location"),
        confidence=detail.get("confidence", "user_unverified"),
        participants=[
            {"id": p["id"], "name": p.get("name", ""), "relation": p.get("relation", "")}
            for p in detail.get("participants", [])
        ],
        media=[
            {"id": m["id"], "file_path": m.get("file_path", ""), "thumbnail_path": m.get("thumbnail_path"), "media_type": m.get("media_type", "")}
            for m in detail.get("media", [])
        ],
        memories=[
            {"id": m["id"], "content": m.get("content", ""), "contributor_id": m.get("contributor_id")}
            for m in detail.get("memories", [])
        ],
        memory_state=memories.state_of(event_id, viewer),
    )


@router.put("/event/{event_id}")
async def update_event(
    event_id: str,
    updates: dict,
    actor: Optional[dict] = Depends(current_actor),
):
    """이벤트 정보 수정"""
    permissions.require_writer(actor)

    node = graph_manager.get_node(event_id)
    if not node or node.get("node_type") != NodeType.EVENT:
        raise HTTPException(status_code=404, detail="이벤트를 찾을 수 없습니다.")

    # 허용된 필드만 업데이트
    allowed = {"title", "description", "date_start", "date_end", "confidence"}
    filtered = {k: v for k, v in updates.items() if k in allowed}

    result = graph_manager.update_node(event_id, filtered)
    return result


@router.get("/person/{person_id}", response_model=PersonResponse)
async def get_person_detail(
    person_id: str,
    viewer_id: str = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
):
    """인물 상세"""
    detail = graph_manager.get_person_detail(person_id)
    if not detail:
        raise HTTPException(status_code=404, detail="인물을 찾을 수 없습니다.")

    # 이 사람이 나온 사진이라도 열람 범위 밖이면 보이지 않는다
    detail["media"] = visibility.filter_media(detail.get("media", []), viewer_id)
    detail["memories"] = visibility.filter_memories(detail.get("memories", []), viewer_id)

    return PersonResponse(
        id=detail["id"],
        name=detail.get("name", ""),
        relation=detail.get("relation", ""),
        birth_year=detail.get("birth_year"),
        thumbnail_url=detail.get("thumbnail_url"),
        events=[
            {"id": e["id"], "title": e.get("title", ""), "date_start": e.get("date_start")}
            for e in detail.get("events", [])
        ],
        media=[
            {"id": m["id"], "file_path": m.get("file_path", ""), "thumbnail_path": m.get("thumbnail_path")}
            for m in detail.get("media", [])
        ],
        memories=[
            {"id": m["id"], "content": m.get("content", ""), "source_type": m.get("source_type")}
            for m in detail.get("memories", [])
        ],
    )


@router.post("/person", response_model=PersonResponse)
async def create_person(
    data: PersonCreate,
    actor: Optional[dict] = Depends(current_actor),
):
    """가족 구성원 추가"""
    permissions.require_writer(actor)

    person = PersonNode(
        name=data.name,
        relation=data.relation,
        birth_year=data.birth_year,
        thumbnail_url=data.thumbnail_url,
    )
    graph_manager.add_person(person)

    return PersonResponse(
        id=person.id,
        name=person.name,
        relation=person.relation,
        birth_year=person.birth_year,
        thumbnail_url=person.thumbnail_url,
        events=[],
        media=[],
    )


@router.get("/persons")
async def list_persons():
    """가족 구성원 목록"""
    return graph_manager.get_persons()
