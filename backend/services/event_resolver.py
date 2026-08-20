"""Event Resolver - 미디어를 기존/신규 이벤트에 매칭"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from backend.models.graph_models import (
    EventNode, PlaceNode, Edge, MediaNode,
    RelationType, Confidence, SourceType, NodeType,
)
from backend.services.graph_manager import graph_manager


# 같은 이벤트로 묶을 시간 범위 (일)
EVENT_TIME_THRESHOLD_DAYS = 3
# 같은 장소로 인식할 거리 (km)
PLACE_DISTANCE_THRESHOLD_KM = 5.0


def resolve_event_for_media(media_node: MediaNode) -> Optional[str]:
    """업로드된 미디어를 적절한 Event에 연결하거나, 새 Event 생성

    매칭 우선순위:
    1. 같은 날짜(±3일) + 같은 장소 → 기존 이벤트
    2. 같은 날짜(±3일) → 기존 이벤트 (장소 없을 때)
    3. 매칭 없음 → 새 이벤트 생성

    Returns: event_id
    """
    media_date = media_node.exif_date or media_node.created_at
    media_lat = media_node.exif_lat
    media_lng = media_node.exif_lng

    # 기존 이벤트에서 매칭 시도
    existing_events = graph_manager.get_events()
    best_match = None
    best_score = 0

    for event in existing_events:
        score = _calculate_match_score(event, media_date, media_lat, media_lng)
        if score > best_score:
            best_score = score
            best_match = event

    if best_match and best_score >= 2:
        event_id = best_match["id"]
    else:
        # 새 이벤트 생성
        event_id = _create_event_from_media(media_node, media_date, media_lat, media_lng)

    # 미디어 → 이벤트 엣지 생성
    edge = Edge(
        source=media_node.id,
        target=event_id,
        relation=RelationType.CAPTURED_DURING,
    )
    graph_manager.add_edge(edge)

    # 장소 연결
    if media_lat and media_lng:
        place_id = _resolve_place(media_lat, media_lng, event_id)
        if place_id:
            # 미디어 → 장소
            graph_manager.add_edge(Edge(
                source=media_node.id,
                target=place_id,
                relation=RelationType.TAKEN_AT,
            ))

    return event_id


def _calculate_match_score(event: dict, media_date: Optional[str], lat: Optional[float], lng: Optional[float]) -> int:
    """이벤트와 미디어 간 매칭 점수 계산 (0~4)"""
    score = 0

    # 날짜 매칭
    event_date = event.get("date_start")
    if event_date and media_date:
        try:
            ed = datetime.fromisoformat(event_date[:10])
            md = datetime.fromisoformat(media_date[:10])
            diff = abs((ed - md).days)
            if diff <= EVENT_TIME_THRESHOLD_DAYS:
                score += 2
            elif diff <= 7:
                score += 1
        except (ValueError, TypeError):
            pass

    # 장소 매칭
    if lat and lng and event.get("location_id"):
        place = graph_manager.get_node(event["location_id"])
        if place and place.get("lat") and place.get("lng"):
            dist = _haversine_km(lat, lng, place["lat"], place["lng"])
            if dist <= PLACE_DISTANCE_THRESHOLD_KM:
                score += 2
            elif dist <= 20:
                score += 1

    return score


def _create_event_from_media(media: MediaNode, date_str: Optional[str], lat: Optional[float], lng: Optional[float]) -> str:
    """미디어 정보로 새 이벤트 생성"""
    title = _generate_event_title(date_str, lat, lng)

    event = EventNode(
        title=title,
        description="자동 생성된 이벤트",
        date_start=date_str[:10] if date_str else None,
        confidence=Confidence.AI_INFERRED,
        source=SourceType.EXIF,
    )

    # 사건 노드를 먼저 넣는다.
    # _resolve_place가 이벤트→장소 엣지를 만드는데, NetworkX의 add_edge는 없는
    # 노드를 속성 없이 만들어 버린다. 그 상태로 save()가 돌면 graph.json에
    # 속성이 텅 빈 노드가 남고, 그 틈에 프로세스가 죽으면 다음 부팅 때
    # _load의 node["id"]가 KeyError로 터진다.
    graph_manager.add_event(event)

    # 장소가 있으면 Place 노드 연결
    if lat and lng:
        place_id = _resolve_place(lat, lng, event.id)
        if place_id:
            event.location_id = place_id
            graph_manager.update_node(event.id, {"location_id": place_id})

    return event.id


def _resolve_place(lat: float, lng: float, event_id: str) -> Optional[str]:
    """GPS 좌표로 기존 Place 찾거나 새로 생성"""
    existing_places = graph_manager.get_places()

    for place in existing_places:
        if place.get("lat") and place.get("lng"):
            dist = _haversine_km(lat, lng, place["lat"], place["lng"])
            if dist <= PLACE_DISTANCE_THRESHOLD_KM:
                # 기존 장소 재사용, 이벤트에 연결
                _ensure_event_place_edge(event_id, place["id"])
                return place["id"]

    # 새 Place 생성
    place = PlaceNode(
        name=f"위치 ({lat:.4f}, {lng:.4f})",
        lat=lat,
        lng=lng,
    )
    graph_manager.add_place(place)
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


def _generate_event_title(date_str: Optional[str], lat: Optional[float], lng: Optional[float]) -> str:
    """이벤트 제목 자동 생성"""
    parts = []

    if date_str:
        try:
            dt = datetime.fromisoformat(date_str[:10])
            parts.append(dt.strftime("%Y년 %m월"))
        except ValueError:
            pass

    if lat and lng:
        parts.append("기록")
    else:
        parts.append("기록")

    return " ".join(parts) if parts else "새 기록"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 GPS 좌표 간 거리 (km)"""
    import math
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


def link_person_to_event(person_id: str, event_id: str, role: str = "참여자"):
    """인물을 이벤트에 연결"""
    edge = Edge(
        source=person_id,
        target=event_id,
        relation=RelationType.PARTICIPATED_IN,
        properties={"role": role},
    )
    graph_manager.add_edge(edge)


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
        graph_manager.update_node(media_id, {"detected_faces": wanted})

    return wanted


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
