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
        properties={"confidence": confidence},
    )
    graph_manager.add_edge(edge)
