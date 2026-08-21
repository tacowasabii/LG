"""사진·영상을 사람·장소에 잇는다

예전 이름 그대로 두었지만, 이 파일이 하던 가장 큰 일 — EXIF를 읽어 추억을
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

# 사진 지목에서 따라온 참여자라는 표시 (PARTICIPATED_IN.properties.via).
# 사람이 직접 적어 넣은 참여자와 구분해야, 사진 태그를 뗄 때 그쪽까지 지우지
# 않는다 (sync_participants_of_event).
PARTICIPANT_VIA_MEDIA = "media"


def resolve_place(lat: float, lng: float, event_id: Optional[str] = None) -> Optional[str]:
    """GPS 좌표로 기존 장소를 찾거나 새로 만든다

    event_id를 주면 그 추억에도 잇는다. 같은 이름의 장소가 둘 생기면 지도에
    점이 겹치므로, 가까운 기존 장소를 먼저 찾는다.
    """
    existing_places = graph_manager.get_places()

    for place in existing_places:
        if place.get("lat") and place.get("lng"):
            dist = _haversine_km(lat, lng, place["lat"], place["lng"])
            if dist <= PLACE_DISTANCE_THRESHOLD_KM:
                # 기존 장소 재사용, 추억에도 연결
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


def place_is_orphan(place_id: str, referenced: Optional[set] = None) -> bool:
    """이 장소를 가리키는 것이 하나도 없는가

    장소는 파생 노드다. 사진의 EXIF 좌표에서 짐작한 지명이 추억의 장소 칸에
    채워지고(routers/media.py의 place_guess -> memories._resolve_place_by_name),
    그 추억이 가리키는 동안만 존재할 이유가 있다. 스스로 열리는 화면이 없다 —
    지도는 추억을 그리고 사진첩은 원본을 그린다.

    가리키는 것을 두 가지로 본다. 엣지(LOCATED_AT · TAKEN_AT)와 추억의
    location_id다. 둘째를 빠뜨리면 엣지 없이 location_id로만 이어진 장소를
    "아무도 안 쓴다"고 읽어 지운다 — 지우는 판정이므로 넓게 잡는 편이 맞다.

    Args:
        referenced: 미리 모아 둔 location_id 집합. 여러 장소를 볼 때 추억 목록을
            매번 다시 읽지 않게 한다. 없으면 여기서 읽는다.
    """
    node = graph_manager.get_node(place_id)
    if not node or node.get("node_type") != NodeType.PLACE:
        return False
    if graph_manager.get_connected_nodes(place_id):
        return False
    if referenced is None:
        referenced = _referenced_place_ids()
    return place_id not in referenced


def _referenced_place_ids() -> set:
    """추억이 대표 장소로 지목한 장소 id"""
    return {
        event.get("location_id")
        for event in graph_manager.get_events()
        if event.get("location_id")
    }


def orphan_places() -> list[dict]:
    """아무것도 걸리지 않은 장소 전부

    이미 남아 있는 것을 찾는 자리다 (scripts/prune_orphan_places.py). 배포된
    그래프에 "강원 홍천"과 "경기 수원"이 아무것도 걸리지 않은 점으로 떠 있었다 —
    그 추억을 지웠는데 장소만 남은 것이다.
    """
    referenced = _referenced_place_ids()
    return [
        place
        for place in graph_manager.get_places()
        if place_is_orphan(place["id"], referenced)
    ]


def prune_orphan_places(place_ids: list[str]) -> list[str]:
    """이 중 아무것도 걸리지 않게 된 장소를 거둔다

    추억·원본을 지운 자리에서 그 뒤에 부른다 (memories.delete_event). 아직
    가리키는 것이 있으면 손대지 않는다 — 장소는 한 추억만의 것이 아니다.

    Returns:
        실제로 지운 장소 id
    """
    referenced = _referenced_place_ids()
    pruned = []
    for place_id in place_ids:
        if not place_is_orphan(place_id, referenced):
            continue
        if graph_manager.delete_node(place_id):
            pruned.append(place_id)
    return pruned


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

    # 지목이 바뀌면 이 기록이 붙은 추억의 "함께한 사람"도 바뀐다
    sync_event_participants(media_id)

    return wanted


def sync_event_participants(media_id: str) -> list[str]:
    """이 기록이 붙은 추억의 참여자를 사진에 지목된 사람과 맞춘다

    사진에 지목된 사람은 그 추억에 함께 있던 사람이다. 붙이는 순간에만 그것을
    옮기면(memories.attach_media), 나중에 지목한 사람은 추억에 닿지 않는다 —
    얼굴 인식이 할머니를 놓쳐서 화면에서 직접 지목했는데도 추억 상세의 "함께한
    사람"과 Film·TV 이야기에는 할머니가 없다. 이야기는 추억에 이어진 인물을
    읽어 쓰기 때문이다 (film_composer._narration의 "참여").

    Returns: 이번에 새로 이어진 person_id 목록
    """
    media = graph_manager.get_node(media_id)
    if not media or media.get("node_type") != NodeType.MEDIA:
        return []

    linked: list[str] = []
    for event_id in events_of_media(media_id):
        linked.extend(sync_participants_of_event(event_id))
    return linked


def events_of_media(media_id: str) -> list[str]:
    """이 기록이 붙은 추억 id

    기록을 지우기 전에 미리 읽어 두는 자리이기도 하다 — 지운 뒤에는 어느 추억의
    참여자를 다시 세야 하는지 알 수 없다 (routers/media.py의 삭제 경로).
    """
    return [
        node["id"]
        for node in graph_manager.get_connected_nodes(
            media_id, relation=RelationType.CAPTURED_DURING
        )
        if node.get("node_type") == NodeType.EVENT
    ]


def depicted_in_event(event_id: str, edges: Optional[list[dict]] = None) -> set[str]:
    """이 추억의 사진·영상에 지목된 사람

    detected_faces와 DEPICTS 엣지를 함께 읽는다. 둘은 함께 맞춰지지만
    (set_media_persons) 시드·이전 데이터에는 한쪽만 있는 경우가 있다
    (album.person_ids_of와 같은 이유).

    읽는 자리가 둘이라 함수로 떼어 두었다. 참여자를 다시 세는 근거이고
    (sync_participants_of_event), 사람이 손으로 참여자를 뗄 때 "이 사람은 사진에
    남아 있어 되돌아옵니다"를 밝히는 근거이기도 하다 (memories.update_memory).
    같은 질문에 답이 두 벌이면 화면이 약속한 것과 실제가 어긋난다.

    Args:
        edges: 미리 읽어 둔 엣지 전체. 없으면 여기서 읽는다.
    """
    if edges is None:
        edges = graph_manager.get_all_edges()

    media_ids = {
        node["id"]
        for node in graph_manager.get_connected_nodes(
            event_id, relation=RelationType.CAPTURED_DURING
        )
        if node.get("node_type") == NodeType.MEDIA
    }

    depicted: set[str] = set()
    for media_id in media_ids:
        node = graph_manager.get_node(media_id) or {}
        depicted.update(node.get("detected_faces") or [])
    for edge in edges:
        if edge["source"] in media_ids and edge["relation"] == RelationType.DEPICTS:
            depicted.add(edge["target"])

    return {
        person_id
        for person_id in depicted
        if (graph_manager.get_node(person_id) or {}).get("node_type") == NodeType.PERSON
    }


def sync_participants_of_event(event_id: str) -> list[str]:
    """추억 하나의 참여자를 그 추억에 붙은 사진·영상의 지목에서 다시 센다

    한 장만 보고 더하지 않는다. 사진 하나에서 뗀 사람이 같은 추억의 다른 사진에
    아직 남아 있으면 그 사람은 여전히 그 자리에 있던 사람이다.

    뗄 때는 이 경로로 붙은 참여자만 뗀다 (properties.via == "media"). 추억을
    만들 때 고른 사람과 기억을 남긴 사람은 사진과 무관하게 참여자다 — 사진 태그
    하나를 지웠다고 그것까지 지우면, 사람이 적어 넣은 것을 자동 정리가 덮는다
    (autotag_media_persons와 같은 판단).

    Returns: 이번에 새로 이어진 person_id 목록
    """
    edges = graph_manager.get_all_edges()
    depicted = depicted_in_event(event_id, edges)

    current = {
        edge["source"]: (edge.get("properties") or {})
        for edge in edges
        if edge["target"] == event_id and edge["relation"] == RelationType.PARTICIPATED_IN
    }

    linked: list[str] = []
    for person_id in depicted:
        if person_id in current:
            continue  # 이미 참여자다. properties를 덮어쓰지 않는다
        graph_manager.add_edge(Edge(
            source=person_id,
            target=event_id,
            relation=RelationType.PARTICIPATED_IN,
            properties={"role": "참여자", "via": PARTICIPANT_VIA_MEDIA},
        ))
        linked.append(person_id)

    for person_id, properties in current.items():
        if person_id not in depicted and properties.get("via") == PARTICIPANT_VIA_MEDIA:
            unlink(person_id, event_id, RelationType.PARTICIPATED_IN)

    return linked


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
    """DEPICTS 하나만 떼어낸다"""
    unlink(media_id, person_id, RelationType.DEPICTS)


def unlink(source: str, target: str, relation: str) -> None:
    """두 노드 사이에서 관계 하나만 떼어낸다

    remove_edge는 두 노드 사이의 관계를 모두 지운다 (JSON·Postgres 양쪽 다).
    영상에 찍힌 사람이 동시에 말하는 사람이기도 하면(NARRATED_BY) 태그를 떼는
    순간 목소리의 주인까지 사라진다. 그래서 남겨야 할 관계를 먼저 읽어 두고
    지운 뒤 되돌려 놓는다.
    """
    survivors = [
        edge
        for edge in graph_manager.get_all_edges()
        if edge["source"] == source
        and edge["target"] == target
        and edge["relation"] != relation
    ]

    graph_manager.remove_edge(source, target)

    for edge in survivors:
        graph_manager.add_edge(Edge(
            source=edge["source"],
            target=edge["target"],
            relation=edge["relation"],
            properties=edge.get("properties") or {},
        ))
