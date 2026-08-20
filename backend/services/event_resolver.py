"""사진·영상을 사람·장소에 잇는다

예전 이름 그대로 두었지만, 이 파일이 하던 가장 큰 일 — EXIF를 읽어 사건을
자동으로 찾거나 없으면 새로 만드는 일 — 은 없앴다.

    자동으로 기억을 병합하지 않는다.

올린 기록이 어느 추억에 속하는지는 사람이 고른다. AI는 "이 사진은 기존
'부산 가족여행'과 관련 있어 보여요"까지만 말하고(services/memory_drafter.py),
붙이는 것은 사용자가 누른 결과로만 일어난다(services/memories.attach_media).

남은 것은 잇는 일뿐이다 — 인물·장소 연결과, 사진에 누가 있는지 지목받는 일.
"""

from __future__ import annotations

import math
from typing import Optional

from backend.models.graph_models import (
    PlaceNode, Edge, MediaType, RelationType, SourceType, NodeType,
)
from backend.services import geocoder
from backend.services.graph_manager import graph_manager


# 같은 장소로 인식할 거리 (km)
PLACE_DISTANCE_THRESHOLD_KM = 5.0


def resolve_place(lat: float, lng: float, event_id: Optional[str] = None) -> Optional[str]:
    """GPS 좌표로 기존 장소를 찾거나 새로 만든다

    event_id를 주면 그 사건에도 잇는다. 같은 이름의 장소가 둘 생기면 지도에
    점이 겹치므로, 가까운 기존 장소를 먼저 찾는다.
    """
    existing_places = graph_manager.get_places()

    for place in existing_places:
        if place.get("lat") and place.get("lng"):
            dist = _haversine_km(lat, lng, place["lat"], place["lng"])
            if dist <= PLACE_DISTANCE_THRESHOLD_KM:
                # 기존 장소 재사용, 사건에도 연결
                if event_id:
                    _ensure_event_place_edge(event_id, place["id"])
                return place["id"]

    # 새 Place 생성. 이름은 좌표에서 짐작한 지명으로 둔다 — "위치 (35.1587,
    # 129.1604)"라는 장소는 지도 옆 목록에서 읽을 수 없고, 사용자가 나중에
    # 고칠 실마리도 주지 않는다. 짐작조차 못 하면(해외·바다) 좌표를 남긴다.
    place = PlaceNode(
        name=geocoder.coarse_name(lat, lng) or f"위치 ({lat:.4f}, {lng:.4f})",
        lat=lat,
        lng=lng,
    )
    graph_manager.add_place(place)
    if event_id:
        _ensure_event_place_edge(event_id, place.id)
    return place.id


def _ensure_event_place_edge(event_id: str, place_id: str):
    """이벤트 → 장소 엣지가 없으면 생성"""
    edges = graph_manager.get_all_edges()
    for edge in edges:
        if edge["source"] == event_id and edge["target"] == place_id:
            return
    graph_manager.add_edge(Edge(
        source=event_id,
        target=place_id,
        relation=RelationType.LOCATED_AT,
    ))


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 GPS 좌표 간 거리 (km)"""
    R = 6371.0  # 지구 반지름 km

    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def link_media_to_person(media_id: str, person_id: str, confidence: float = 1.0):
    """미디어에 인물 태그"""
    edge = Edge(
        source=media_id,
        target=person_id,
        relation=RelationType.DEPICTS,
        properties={"confidence": confidence, "source": SourceType.USER_INPUT.value},
    )
    graph_manager.add_edge(edge)


def set_media_persons(media_id: str, person_ids: list[str]) -> list[str]:
    """사진·영상에 누가 있는지 사람이 직접 지목한다 (최종 목록으로 맞춘다)

    얼굴 인식이 없으므로 detected_faces를 채울 다른 길이 없다. 자동으로 못 하는
    일을 아예 안 하는 것으로 두면 새로 올린 사진은 인물과 영원히 끊긴다 —
    인물별 조회(routers/media.list_media)도, 등장 인물의 비공개 요청도
    시드 데이터에만 걸린다.

    더하기만 두지 않고 빼기까지 두는 이유: 잘못 지목한 사람을 뗄 수 없으면,
    남의 사진에 자기가 영구히 붙는다. 등장 인물이 비공개 판정에 쓰이는 제품에서
    그건 설정이 아니라 사고다 (기획안 08장).

    detected_faces와 DEPICTS 엣지를 함께 맞춘다. 공개 범위 판정이 둘을 모두
    읽기 때문이다 (visibility.ConsentIndex.blocks). 한쪽만 쓰면 비공개로 돌린
    사람이 다른 경로에서 새어 나온다.

    없는 id, 인물이 아닌 id, 중복은 조용히 버린다. 화면이 보낸 값이므로 여기서
    막아야 하고, 태그 하나가 틀렸다고 요청 전체를 되돌릴 이유는 없다.

    Returns: 맞춰진 뒤의 최종 person_id 목록
    """
    media = graph_manager.get_node(media_id)
    if not media or media.get("node_type") != NodeType.MEDIA:
        return []

    wanted: list[str] = []
    for person_id in person_ids:
        person_id = (person_id or "").strip()
        if not person_id or person_id in wanted:
            continue
        person = graph_manager.get_node(person_id)
        if person and person.get("node_type") == NodeType.PERSON:
            wanted.append(person_id)

    current = list(media.get("detected_faces") or [])

    for person_id in wanted:
        if person_id not in current:
            link_media_to_person(media_id, person_id)

    for person_id in current:
        if person_id not in wanted:
            _unlink_media_from_person(media_id, person_id)

    if set(current) != set(wanted):
        graph_manager.update_node(media_id, {
            "detected_faces": wanted,
            # 사람이 손을 댄 순간부터 이 목록은 추정이 아니다
            "faces_source": SourceType.USER_INPUT.value,
        })

    return wanted


def autotag_media_persons(media_id: str) -> list[str]:
    """얼굴 인식으로 이 기록에 있는 사람을 채운다 (services/faces.py)

    사람이 이미 지목한 것이 있으면 손대지 않는다. 자동 인식은 추정이고, 사람이
    누른 것을 추정으로 덮으면 지목의 뜻이 없어진다. 비어 있을 때만 채운다.

    자격증명이 없거나 등록된 얼굴이 없으면 조용히 지나간다 — 그때도 화면에서
    직접 지목하는 길은 그대로 동작한다.

    Returns: 자동으로 붙은 person_id 목록
    """
    from backend.services import faces

    if not faces.enabled():
        return []

    media = graph_manager.get_node(media_id)
    if not media or media.get("node_type") != NodeType.MEDIA:
        return []
    if media.get("media_type") != MediaType.PHOTO:
        return []
    if media.get("detected_faces"):
        return []  # 사람이 이미 정했다

    # 위치까지 저장한다 — 상세 화면이 사진 위에 이름을 얹는 근거다
    boxes = faces.identify_and_store(media_id)
    found = [b["person_id"] for b in boxes if b.get("person_id")]
    if not found:
        return []

    set_media_persons(media_id, found)
    # 자동으로 붙인 것은 추정이다. 사람이 지목한 것과 구분되어야 한다.
    graph_manager.update_node(media_id, {"faces_source": SourceType.AI_VISION.value})
    return found


def _unlink_media_from_person(media_id: str, person_id: str) -> None:
    """DEPICTS 하나만 떼어낸다

    remove_edge는 두 노드 사이의 관계를 모두 지운다 (JSON·Postgres 양쪽 다).
    영상에 찍힌 사람이 동시에 말하는 사람이기도 하면(NARRATED_BY) 태그를 떼는
    순간 목소리의 주인까지 사라진다. 그래서 남겨야 할 관계를 먼저 읽어 두고
    지운 뒤 되돌려 놓는다.
    """
    survivors = [
        edge
        for edge in graph_manager.get_all_edges()
        if edge["source"] == media_id
        and edge["target"] == person_id
        and edge["relation"] != RelationType.DEPICTS
    ]

    graph_manager.remove_edge(media_id, person_id)

    for edge in survivors:
        graph_manager.add_edge(Edge(
            source=edge["source"],
            target=edge["target"],
            relation=edge["relation"],
            properties=edge.get("properties") or {},
        ))
