"""추억과 기억 이어가기

이 파일이 예전 `verification.py`를 대신한다. 바뀐 것은 구조가 아니라 전제다.

    예전: AI가 추정한 사실을 가족 전원이 맞음/모름/이견으로 판정해야 완료됐다.
    지금: 한 사람이 만들면 그 순간 가족 공간에 게시된다. 나머지 가족은
          의무가 없고, 기억이 떠오를 때만 자기 기억을 더한다.

전원 확인을 버린 이유는 사용자 구성이다. 가족에는 앱이 익숙하지 않은 고령자와
어린아이가 함께 있다. 모두의 응답을 완료 조건으로 걸면 추억은 영원히 미완으로
남고, 만든 사람은 자기가 남긴 기록이 왜 반쪽인지 알 수 없다.

그래서 남은 것은 두 행동뿐이다.

    나도 기억나요 (echo)          누르기만 한다. 판정이 아니라 공감이다.
    내 기억 더하기 (contribution) 원본을 건드리지 않고 나란히 쌓인다.

기억이 서로 어긋나도 하나를 정답으로 고르지 않는다. "환갑 여행"과 "여름휴가"는
둘 다 남고, 화면은 "가족들이 조금 다르게 기억하고 있어요"라고만 알린다.
누가 맞는지는 AI도 가족도 여기서 판정하지 않는다.

남긴 기억은 지울 수 있다 (delete_memory). 지우는 것은 그 사람이 남긴 문장이고,
함께 올린 사진·영상·목소리는 사건에 그대로 남는다 — 원본을 지우는 자리는
사진첩이다. 남긴 사람과 가족 관리자만 지운다. 판정하지 않는 것과 지우지 못하는
것은 다르다: 내가 한 말을 거둘 수 없으면 그건 보존이 아니라 구속이다.

추억 자체도 지울 수 있다 (delete_event). 이때는 그 추억에 딸린 사진·영상·목소리와
기억 문장·전사문·이야기까지 함께 지운다 — 추억을 지운 사람에게 사진첩에 남은 그
장면은 지운 것이 아니고, 지우려면 사진첩에서 같은 일을 한 번 더 해야 했다. 대신
사진이 0장이 된 것을 신호로 자동으로 지우지는 않는다: 가족이 남긴 문장이 남의
사진 정리에 딸려 사라지면 안 된다.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Optional

from backend.config import EXAONE_PLANNER_MODEL
from backend.models.graph_models import (
    Confidence,
    Edge,
    EventNode,
    MediaType,
    MemoryKind,
    MemoryNode,
    MemoryState,
    NodeType,
    PlaceNode,
    RelationType,
    SourceType,
)
from backend.services import (
    event_resolver,
    llm_client,
    media_analyzer,
    memory_context,
    visibility,
)
from backend.services.graph_manager import graph_manager


# --- 상태 파생 ---------------------------------------------------------------


def _person_ref(person_id: Optional[str]) -> Optional[dict]:
    if not person_id:
        return None
    person = graph_manager.get_node(person_id)
    if not person:
        return {"id": person_id, "name": person_id, "relation": ""}
    return {
        "id": person_id,
        "name": person.get("name", person_id),
        "relation": person.get("relation", ""),
        "thumbnail_url": person.get("thumbnail_url"),
    }


def memories_of(event_id: str, viewer_id: Optional[str] = None) -> list[dict]:
    """이 추억에 붙은 기억 문장 (오래된 것부터)

    공개 범위를 지난다 — 기억 문장이 목록에서만 걸러지고 상세에서 새어 나가면
    가려 준다는 말이 거짓이 된다 (기획안 08장).
    """
    nodes = [
        node
        for node in graph_manager.get_connected_nodes(event_id)
        if node.get("node_type") == NodeType.MEMORY
    ]
    nodes = visibility.filter_memories(nodes, viewer_id)
    return sorted(nodes, key=lambda m: m.get("created_at") or "")


def author_memory(event_id: str, memories: Optional[list[dict]] = None) -> Optional[dict]:
    """최초 작성자의 기억 (없으면 None)

    kind로 표시된 것을 먼저 찾고, 없으면 가장 오래된 기억을 작성자의 것으로 본다.
    시드 데이터와 예전에 쌓인 기억에는 kind가 없기 때문이다 — 마이그레이션을
    돌리지 않고도 상세 화면이 "최초 작성자의 기억"을 세울 수 있어야 한다.

    다만 스스로 "더한 기억"이라고 밝힌 것(kind=contribution)은 이 자리에 올리지
    않는다. 작성자가 자기 첫 기억을 지우면 남는 것은 남이 더한 기억인데, 그것을
    "최초 작성자의 기억" 자리에 세우면 남의 문장이 작성자의 것으로 읽힌다.
    그런 추억에는 작성자의 기억이 없는 것이 맞다.
    """
    items = memories if memories is not None else memories_of(event_id)
    for memory in items:
        if memory.get("kind") == MemoryKind.AUTHOR:
            return memory
    for memory in items:
        if not memory.get("kind"):
            return memory
    return None


def state_of(event_id: str, viewer_id: Optional[str] = None) -> Optional[dict]:
    """추억 하나에 기억이 얼마나 쌓였는가

    상태는 저장하지 않고 매번 기억에서 파생한다. 저장하면 기억이 더해져도
    상태가 갱신되지 않아 화면과 데이터가 어긋난다.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    items = memories_of(event_id, viewer_id)
    first = author_memory(event_id, items)
    # 작성자의 기억이 없으면(지웠다) 무엇에 "더했다"고 셀 기준이 없다. 그때는
    # 사람 수로만 가른다 — 한 사람이 남긴 문장 하나를 "함께 기억"으로 읽지 않게.
    added = [m for m in items if m.get("id") != first["id"]] if first else []
    differs = any(m.get("differs") for m in items)

    contributors: list[str] = []
    for memory in items:
        person_id = memory.get("contributor_id")
        if person_id and person_id not in contributors:
            contributors.append(person_id)

    if differs:
        state = MemoryState.VARIED
    elif added or len(contributors) >= 2:
        state = MemoryState.SHARED
    else:
        state = MemoryState.ALONE

    echoes = event.get("echoes") or []

    return {
        "state": state.value,
        "author": _person_ref(event.get("author_id") or (first or {}).get("contributor_id")),
        "contributors": [_person_ref(pid) for pid in contributors],
        "memory_count": len(items),
        "added_count": len(added),
        "echo_count": len(echoes),
        "echoed_by": [_person_ref(e.get("person_id")) for e in echoes if e.get("person_id")],
        # 서로 다르게 기억하는 내용이 있는가. 화면은 이 값으로 안내문 한 줄만 띄운다.
        "varied": differs,
    }


# --- 추억 만들기 -------------------------------------------------------------


def _resolve_place_by_name(name: str) -> Optional[str]:
    """이름으로 장소를 찾고, 없으면 만든다

    같은 이름이 이미 있으면 재사용한다. 새로 만들면 같은 장소가 둘이 되고
    지도에 점이 겹친다.
    """
    name = (name or "").strip()
    if not name:
        return None
    for place in graph_manager.get_places():
        if (place.get("name") or "").strip() == name:
            return place["id"]
    place = PlaceNode(name=name)
    graph_manager.add_place(place)
    return place.id


def create_memory(
    author_id: Optional[str],
    title: str,
    description: str = "",
    date_start: Optional[str] = None,
    place_id: Optional[str] = None,
    place_name: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
    media_ids: Optional[list[str]] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict:
    """추억 하나를 만든다. 만드는 즉시 가족 공간에 게시된다

    다른 가족의 승인을 받지 않는다. AI 초안을 그대로 쓰든 고쳐 쓰든, 저장은
    한 번이고 그 순간부터 가족이 함께 본다.

    설명(description)은 사건에 남고, 같은 문장이 작성자의 기억으로도 남는다.
    상세 화면이 "최초 작성자의 기억"을 세우려면 사람에게 귀속된 문장이 있어야
    한다 — 사건 설명은 누구의 것도 아니다.
    """
    title = (title or "").strip() or "제목 없는 추억"
    description = (description or "").strip()

    if not place_id and place_name:
        place_id = _resolve_place_by_name(place_name)
    if place_id and not graph_manager.get_node(place_id):
        place_id = None
    if place_id and lat is not None and lng is not None:
        place = graph_manager.get_node(place_id) or {}
        if place.get("lat") is None or place.get("lng") is None:
            graph_manager.update_node(place_id, {"lat": lat, "lng": lng})

    event = EventNode(
        title=title,
        description=description,
        date_start=(date_start or None),
        location_id=place_id,
        # 가족이 직접 만든 추억이다. AI가 초안을 썼더라도 사람이 확인하고
        # 저장을 눌렀으므로 추정이 아니다.
        confidence=Confidence.CONFIRMED,
        source=SourceType.USER_INPUT,
        author_id=author_id,
    )
    graph_manager.add_event(event)

    if place_id:
        graph_manager.add_edge(Edge(
            source=event.id, target=place_id, relation=RelationType.LOCATED_AT,
        ))

    for person_id in _valid_persons(person_ids):
        graph_manager.add_edge(Edge(
            source=person_id,
            target=event.id,
            relation=RelationType.PARTICIPATED_IN,
            properties={"role": "참여자"},
        ))

    attach_media(event.id, media_ids or [])

    if description and author_id:
        # 사진은 추억에 이미 붙어 있다. 작성자의 기억에까지 매달면 상세 화면에서
        # 같은 사진이 위 갤러리와 기억 아래에 두 번 나온다. 기억에 사진을 매다는
        # 것은 "이 기억과 함께 올린 사진"이 있을 때뿐이다 (가족이 더한 기억).
        add_contribution(
            event.id,
            author_id,
            description,
            kind=MemoryKind.AUTHOR,
        )

    return graph_manager.get_node(event.id) or {}


def _valid_persons(person_ids: Optional[list[str]]) -> list[str]:
    """그래프에 있는 인물만 남긴다 (없는 사람을 만들지 않는다)"""
    result: list[str] = []
    for person_id in person_ids or []:
        person_id = (person_id or "").strip()
        if not person_id or person_id in result:
            continue
        node = graph_manager.get_node(person_id)
        if node and node.get("node_type") == NodeType.PERSON:
            result.append(person_id)
    return result


def attach_media(event_id: str, media_ids: list[str]) -> list[str]:
    """사진·영상을 이 추억에 잇는다 (CAPTURED_DURING)

    자동으로 묶지 않는다. 어느 추억에 붙일지는 올린 사람이 화면에서 고른 결과가
    여기로 온다 (기획안 08: 자동으로 기억을 병합하지 않는다).
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return []

    attached: list[str] = []
    for media_id in media_ids or []:
        media_id = (media_id or "").strip()
        if not media_id or media_id in attached:
            continue
        media = graph_manager.get_node(media_id)
        if not media or media.get("node_type") != NodeType.MEDIA:
            continue
        graph_manager.add_edge(Edge(
            source=media_id, target=event_id, relation=RelationType.CAPTURED_DURING,
        ))
        attached.append(media_id)

    # 사진에 지목된 사람은 그 사건에 함께 있던 사람이기도 하다. 붙일 때만 하지
    # 않고 한 자리에서 다시 센다 (event_resolver.sync_participants_of_event) —
    # 나중에 지목한 사람도 같은 규칙으로 사건에 닿아야 한다. 규칙이 두 벌이면
    # 한쪽만 고쳐졌을 때 이야기에 들어가는 사람이 경로마다 달라진다.
    if attached:
        event_resolver.sync_participants_of_event(event_id)

    return attached


# --- 기억 더하기 -------------------------------------------------------------


def add_contribution(
    event_id: str,
    person_id: str,
    content: str,
    media_ids: Optional[list[str]] = None,
    differs: bool = False,
    source_type: str = SourceType.USER_INPUT,
    polished: Optional[str] = None,
    audio_media_id: Optional[str] = None,
    kind: str = MemoryKind.CONTRIBUTION,
) -> Optional[dict]:
    """다른 가족이 만든 추억에 내 기억을 더한다

    원본을 수정하거나 덮어쓰지 않는다. 별도 기억으로 저장하고 사건에 잇는다 —
    상세 화면에서 최초 작성자의 기억 아래에 나란히 쌓인다.

    사진·영상을 함께 올린 경우 그 기록은 사건에도 붙고(CAPTURED_DURING), 이
    기억의 근거로도 이어진다(EVIDENCED_BY). 문장에서 원본으로 되짚을 수 있어야
    한다.

    Returns:
        만들어진 기억 노드. 사건이나 사람이 없으면 None.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None
    person = graph_manager.get_node(person_id)
    if not person or person.get("node_type") != NodeType.PERSON:
        return None

    content = (content or "").strip()
    if not content:
        return None

    attached = attach_media(event_id, media_ids or [])
    if audio_media_id:
        audio = graph_manager.get_node(audio_media_id)
        if audio and audio.get("node_type") == NodeType.MEDIA and audio_media_id not in attached:
            attached.append(audio_media_id)

    memory = MemoryNode(
        content=content,
        source_type=source_type,
        contributor_id=person_id,
        confidence=Confidence.CONFIRMED,
        kind=kind,
        polished=(polished or "").strip() or None,
        differs=bool(differs),
        media_ids=attached,
    )
    graph_manager.add_memory(memory)

    graph_manager.add_edge(Edge(
        source=memory.id, target=event_id, relation=RelationType.ABOUT,
    ))
    graph_manager.add_edge(Edge(
        source=person_id, target=memory.id, relation=RelationType.REMEMBERS,
    ))
    for media_id in attached:
        graph_manager.add_edge(Edge(
            source=memory.id, target=media_id, relation=RelationType.EVIDENCED_BY,
        ))

    # 기억을 남긴 사람은 그 자리에 함께 있던 사람이다
    graph_manager.add_edge(Edge(
        source=person_id,
        target=event_id,
        relation=RelationType.PARTICIPATED_IN,
        properties={"role": "참여자"},
    ))

    return graph_manager.get_node(memory.id)


def toggle_echo(event_id: str, person_id: str) -> Optional[dict]:
    """나도 기억나요 (누르면 켜지고 다시 누르면 꺼진다)

    확인이 아니다. 아무도 누르지 않아도 추억은 그대로 게시된 상태다.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None
    if not graph_manager.get_node(person_id):
        return None

    echoes = list(event.get("echoes") or [])
    already = any(e.get("person_id") == person_id for e in echoes)

    if already:
        echoes = [e for e in echoes if e.get("person_id") != person_id]
        echoed = False
    else:
        echoes.append({"person_id": person_id, "at": datetime.now().isoformat()})
        echoed = True

    graph_manager.update_node(event_id, {"echoes": echoes})
    return {
        "event_id": event_id,
        "echoed": echoed,
        "echo_count": len(echoes),
        "echoed_by": [_person_ref(e.get("person_id")) for e in echoes if e.get("person_id")],
    }


# --- 기억 지우기 -------------------------------------------------------------


def attached_memory(event_id: str, memory_id: str) -> Optional[dict]:
    """이 사건에 붙어 있는 기억 하나 (아니면 None)

    사건을 함께 받는 이유는 "사건에서 지운다"는 말을 지키기 위해서다. 다른
    사건의 기억 id를 넣어도 여기서 걸린다 — 화면이 보고 있는 추억과 지워지는
    문장이 어긋나면, 지운 사람은 무엇을 지웠는지 모른다.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    memory = graph_manager.get_node(memory_id)
    if not memory or memory.get("node_type") != NodeType.MEMORY:
        return None

    attached = any(
        node.get("id") == memory_id
        for node in graph_manager.get_connected_nodes(event_id)
        if node.get("node_type") == NodeType.MEMORY
    )
    return memory if attached else None


def _story_may_quote(event: dict, memory: dict) -> bool:
    """사건에 저장된 "함께 기억한 이야기"가 이 기억을 담고 있을 수 있는가

    이야기를 쓴 시점이 기억이 생긴 시점보다 뒤라면 담고 있다. 그보다 앞서 쓰인
    이야기는 이 기억을 볼 수 없었으므로 그대로 둔다 — 지울 이유가 없는 것까지
    지우면 가족이 만든 이야기를 잃는다.
    """
    if not event.get("together_story"):
        return False

    written_at = event.get("together_story_at")
    created_at = memory.get("created_at")
    if not written_at or not created_at:
        # 언제 쓴 것인지 모르면 담고 있다고 본다. 반대로 잘못 짚으면 지운 말이
        # AI가 쓴 산문 속에 그대로 남는다.
        return True
    return written_at >= created_at


def _evidence_of(memory_id: str) -> list[dict]:
    """이 기억이 근거로 매달고 있는 원본 (EVIDENCED_BY)

    노드의 media_ids만 보면 인터뷰로 남긴 목소리를 놓친다. 인터뷰는 엣지만 잇고
    그 필드는 채우지 않는다 (interview_engine.record_answer). 엣지가 두 경로의
    공통분모다 — 그래서 기억과 함께 지워야 할 녹음을 찾는 일은 엣지로 한다.
    """
    return [
        node
        for node in graph_manager.get_connected_nodes(
            memory_id, relation=RelationType.EVIDENCED_BY
        )
        if node.get("node_type") == NodeType.MEDIA
    ]


def _voices_to_erase(memory_id: str, evidence: list[dict]) -> list[dict]:
    """이 기억과 함께 사라져야 할 목소리

    목소리로 남긴 기억은 문장과 녹음이 한 몸이다. 문장만 지우고 녹음을 남기면
    지운 것이 아니라 형태만 바꿔 남긴 것이 된다 — 전사문이 그 녹음 노드에 함께
    있어서 말한 내용이 그대로 읽히고, 사건 상세의 "가족이 남긴 목소리"에서 계속
    재생된다. visibility.py가 원본과 그 원본을 설명한 문장을 함께 가리는 것과
    같은 이유다.

    사진·영상은 지우지 않는다. 그것은 가족이 사건에 올린 기록이고, 문장 하나를
    거두는 일과 무게가 다르다. 원본을 지우는 자리는 사진첩이다.

    다른 기억이 아직 근거로 쓰는 녹음은 남긴다. 인터뷰 녹음 하나에 여러 문장이
    매달릴 수 있고, 그때 지우면 남의 기억에서 근거가 사라진다.

    사건에만 붙은 녹음(POST /{id}/media로 더한 것)은 근거 엣지가 없으므로 애초에
    여기 들어오지 않는다.
    """
    voices = []
    for node in evidence:
        if node.get("media_type") != MediaType.AUDIO:
            continue
        others = [
            other
            for other in graph_manager.get_connected_nodes(
                node["id"], relation=RelationType.EVIDENCED_BY
            )
            if other.get("node_type") == NodeType.MEMORY and other.get("id") != memory_id
        ]
        if others:
            continue
        voices.append(node)
    return voices


def delete_memory(event_id: str, memory_id: str) -> Optional[dict]:
    """사건에서 기억 문장 하나를 지운다

    목소리로 남긴 기억이면 그 녹음도 함께 지운다 (_voices_to_erase). 문장만 지우고
    녹음을 남기면 지운 것이 아니다 — 전사문이 녹음에 함께 있고, 사건 상세에서 그
    목소리가 계속 재생된다.

    사진·영상은 남는다. 그것은 가족이 사건에 올린 기록이고, 원본을 지우는 자리는
    사진첩이다 (원본을 지울 때 기억 문장이 남는 것과 짝을 맞춘 것이다). 대신 무엇이
    지워지고 무엇이 남았는지 돌려준다. 지운 사람이 "다 지웠다"고 오해하는 것이 가장
    나쁜 실패다.

    "함께 기억한 이야기"는 이 기억이 생긴 뒤에 쓰였다면 함께 지운다. 그 이야기에는
    지운 문장이 들어 있다 — 모델이 없을 때는 문장을 그대로 나열하기까지 한다
    (_story_fallback). 문장만 지우고 이야기를 남기면 거둔 말이 AI의 산문 속에
    계속 남는다. 다시 만드는 것은 단추 한 번이다.

    권한은 라우터가 본다 (permissions.require_owner_of). 여기는 무엇이 지워지고
    무엇이 남는지만 정한다.

    Returns:
        지운 것과 남은 것. 사건·기억이 없거나 서로 붙어 있지 않으면 None.
    """
    memory = attached_memory(event_id, memory_id)
    if not memory:
        return None

    event = graph_manager.get_node(event_id) or {}

    evidence = _evidence_of(memory_id)
    voices = _voices_to_erase(memory_id, evidence)
    erased = {node["id"] for node in voices}
    # 함께 올린 사진·영상. 지우지 않고 세어만 둔다.
    kept_media = [node["id"] for node in evidence if node["id"] not in erased]

    story_cleared = _story_may_quote(event, memory)

    # 한 묶음으로 지운다. 갈라지면 지운 문장을 담은 이야기만 남거나, 문장 없는
    # 녹음이 사건에 떠도는 상태가 생긴다.
    with graph_manager.batch():
        if story_cleared:
            graph_manager.update_node(event_id, {
                "together_story": None,
                "together_story_at": None,
                "together_story_basis": 0,
                "together_story_persons": 0,
            })
        for node in voices:
            graph_manager.delete_node(node["id"])
        graph_manager.delete_node(memory_id)

    # 노드를 먼저, 파일을 나중에 (media_analyzer.erase_files의 주석과 같은 이유)
    for node in voices:
        media_analyzer.erase_files(node)

    return {
        "event_id": event_id,
        "memory_id": memory_id,
        "deleted_voices": [node["id"] for node in voices],
        "kept_media": kept_media,
        "story_cleared": story_cleared,
    }


def _event_media(event_id: str, memory_ids: Optional[list[str]] = None) -> list[dict]:
    """이 추억이 데리고 있는 사진·영상·목소리

    두 길로 붙는다. 사건에 직접 붙은 것(CAPTURED_DURING)과, 이 사건의 기억이
    근거로 매단 것(EVIDENCED_BY)이다. 목소리로 남긴 기억의 녹음은 뒤쪽만 있다 —
    add_contribution이 그 녹음을 기억의 근거로만 잇는다. 앞쪽만 세면 추억을 지운
    뒤에 주인 없는 녹음이 남는다.

    추억 상세가 보여주는 목록(detail의 media)과 같은 것을 세되, 공개 범위로
    걸러내지 않는다. 내게 가려진 원본도 이 추억의 것이면 함께 지워져야 한다.
    """
    if memory_ids is None:
        memory_ids = [
            node["id"]
            for node in graph_manager.get_connected_nodes(event_id)
            if node.get("node_type") == NodeType.MEMORY
        ]

    found: dict[str, dict] = {}
    for node in graph_manager.get_connected_nodes(event_id):
        if node.get("node_type") == NodeType.MEDIA:
            found[node["id"]] = node
    for memory_id in memory_ids:
        for node in _evidence_of(memory_id):
            found.setdefault(node["id"], node)
    return list(found.values())


def _media_still_used(media_id: str, event_id: str, doomed_memories: set[str]) -> bool:
    """이 원본을 다른 추억이 아직 쓰고 있는가

    사진 한 장은 추억 둘에 붙을 수 있다 (attach_media는 예전 연결을 끊지 않는다).
    그때 한 추억을 지우면서 원본까지 지우면, 남은 추억의 사진첩에 구멍이 난다 —
    사용자가 고른 것은 이 추억을 지우는 일이었다. 다른 기억이 아직 근거로 쓰는
    녹음을 남기는 것과 같은 판단이다 (_voices_to_erase).
    """
    for node in graph_manager.get_connected_nodes(media_id):
        node_type = node.get("node_type")
        if node_type == NodeType.EVENT and node["id"] != event_id:
            return True
        if node_type == NodeType.MEMORY and node["id"] not in doomed_memories:
            return True
    return False


def delete_event_plan(event_id: str) -> Optional[dict]:
    """이 추억을 지우면 무엇이 함께 사라지는지 (지우기 전에 보는 것)

    라우터가 원본마다 권한을 보려면 지우기 전의 목록이 필요하다 — 남이 올린
    사진은 그 사람이나 가족 관리자만 지운다 (permissions.require_owner_of).
    그래서 "무엇이 딸려 오는가"를 지우는 일에서 떼어 두었다. delete_event가
    같은 함수를 다시 불러 판정하므로 규칙이 두 벌이 되지 않는다.

    Returns:
        지울 것들. 그 id의 사건이 없으면 None.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    connected = graph_manager.get_connected_nodes(event_id)
    memory_ids = [
        node["id"] for node in connected if node.get("node_type") == NodeType.MEMORY
    ]
    doomed = set(memory_ids)

    media, shared = [], []
    for node in _event_media(event_id, memory_ids):
        if _media_still_used(node["id"], event_id, doomed):
            shared.append(node)
        else:
            media.append(node)

    return {
        "event_id": event_id,
        "title": event.get("title") or "",
        "memory_ids": memory_ids,
        # 이 추억과 함께 지워질 원본
        "media": media,
        # 다른 추억에도 붙어 있어 남는 원본
        "shared_media": shared,
        # 이 사건이 걸려 있던 장소. 사건을 지운 뒤에 아직 쓰이는지 다시 본다
        "place_ids": [
            node["id"] for node in connected if node.get("node_type") == NodeType.PLACE
        ],
        "echo_count": len(event.get("echoes") or []),
    }


def delete_event(event_id: str, keep_media: Optional[Mapping[str, str]] = None) -> Optional[dict]:
    """추억 하나를 지운다 — 사건과 거기에 딸린 것 전부

    사진이 0장이 된 것을 신호로 삼아 자동으로 지우지 않는다. 그 추억에는 다른
    가족이 남긴 기억 문장과 "나도 기억나요"가 붙어 있을 수 있고, 사진 한 장
    지우기에 딸려 그것이 사라지면 정리가 아니라 사고다. 지우는 것은 사람이
    고른 결과로만 일어난다.

    함께 지우는 것:

      - 기억 문장(MemoryNode)과 그 관계. 사건이 없어지면 그 문장은 어디에도
        걸리지 않고, 상세로 들어갈 길조차 없다
      - 사진·영상·목소리의 노드와 원본 파일(media_analyzer.erase_files).
        예전에는 이것을 남겨 두고 "원본을 지우는 자리는 사진첩"이라고 안내했다.
        추억을 지운 사람에게 그것은 지운 것이 아니다 — 사진첩에 그 장면이
        그대로 있고, 지우려면 사진첩에서 같은 일을 한 번 더 해야 했다
      - 전사문·맥락·"함께 기억한 이야기". 별도 저장소가 없다. 기억 노드와
        미디어 노드에 얹혀 있어 그 노드와 함께 사라진다
      - 아무것도 걸리지 않게 된 장소 (event_resolver.prune_orphan_places)

    남기는 것:

      - 사람. 이 추억만의 것이 아니다 — 다른 추억과 사진첩에 계속 나온다
      - 다른 추억에도 붙어 있는 원본(shared). 사진 한 장은 추억 둘에 붙을 수
        있고, 그것까지 지우면 남은 추억에 구멍이 난다
      - 지울 권한이 없는 원본(keep_media). 남이 올린 사진은 그 사람이나
        가족 관리자만 지운다 — 라우터가 판정해 이유와 함께 여기로 넘긴다

    공개 범위로 걸러 세지 않는다. 내가 볼 수 없는 기억·원본도 이 사건에 붙어
    있으면 함께 지워진다 — 남겨 두면 사건 없는 문장이 저장소에 떠돌고, 어느
    화면에서도 거둘 수 없다. 대신 무엇이 지워지고 무엇이 남았는지 세어 돌려준다.
    "지웠습니다" 한 마디로 끝내면 사용자는 무엇이 사라졌는지 모른다.

    권한은 라우터가 본다 (permissions.require_owner_of). 여기는 무엇이 지워지고
    무엇이 남는지만 정한다 — delete_memory와 같은 분업이다.

    Args:
        keep_media: 지우지 말 원본 id -> 남기는 이유. 라우터가 권한으로 막은 것이
            들어온다. 이유를 서버 안에서 다시 쓰지 않고 받아 적는 이유는 그것이
            판정한 자리에만 있기 때문이다 — 누가 올린 사진인지는 라우터가 안다.

    Returns:
        지운 것과 남은 것. 그 id의 사건이 없으면 None.
    """
    plan = delete_event_plan(event_id)
    if not plan:
        return None

    blocked = dict(keep_media or {})
    doomed_media = [node for node in plan["media"] if node["id"] not in blocked]

    # 한 묶음으로 지운다. 갈라지면 사건은 없는데 그 사건의 기억 문장만 남는
    # 상태가 생기고, 그 문장은 어느 화면에서도 지울 수 없다.
    with graph_manager.batch():
        for memory_id in plan["memory_ids"]:
            graph_manager.delete_node(memory_id)
        for node in doomed_media:
            graph_manager.delete_node(node["id"])
        graph_manager.delete_node(event_id)
        # 사건이 없어진 뒤에 판정한다 — 먼저 보면 이 사건의 엣지가 아직 남아
        # 있어 모든 장소가 "쓰이는 중"으로 읽힌다
        deleted_places = event_resolver.prune_orphan_places(plan["place_ids"])

    # 노드를 먼저, 파일을 나중에 (media_analyzer.erase_files의 주석과 같은 이유)
    for node in doomed_media:
        media_analyzer.erase_files(node)

    counts = {"photo": 0, "video": 0, "audio": 0}
    for node in doomed_media:
        media_type = node.get("media_type") or MediaType.PHOTO.value
        if media_type in counts:
            counts[media_type] += 1

    return {
        "event_id": event_id,
        "title": plan["title"],
        "deleted_memories": plan["memory_ids"],
        "deleted_media": [node["id"] for node in doomed_media],
        # 사진 몇 장, 영상 몇 개, 목소리 몇 개인지. 화면이 그대로 적는다
        "deleted_counts": counts,
        "deleted_places": deleted_places,
        # 지우지 않고 남긴 원본과 그 이유. 다른 추억에도 붙어 있거나, 남이 올린 것이다
        "kept_media": (
            [
                {"id": node["id"], "reason": "다른 추억에도 붙어 있습니다"}
                for node in plan["shared_media"]
            ]
            + [
                {"id": node["id"], "reason": blocked[node["id"]]}
                for node in plan["media"]
                if node["id"] in blocked
            ]
        ),
        "echo_count": plan["echo_count"],
    }


# --- 화면이 쓰는 모양 --------------------------------------------------------


def question_for_media(media_id: str) -> Optional[str]:
    """이 음성이 답한 질문

    질문은 음성 노드가 아니라 그 음성을 근거로 삼은 기억(EVIDENCED_BY)에 남아
    있다. 인터뷰로 남긴 목소리는 언제나 어떤 질문의 답이고, 질문을 빼면
    "모르겠어요" 한 마디가 무슨 이야기인지 읽을 수 없다.

    음성을 목록으로 내려주는 곳(미디어 목록·추억 상세)이 함께 쓴다.
    """
    for node in graph_manager.get_connected_nodes(media_id):
        if node.get("node_type") == NodeType.MEMORY and node.get("question"):
            return node["question"]
    return None


def _memory_view(memory: dict, visible_media_ids: Optional[set] = None) -> dict:
    """기억 하나를 화면 모양으로

    원문(content)과 AI가 다듬은 문장(polished)을 함께 내려준다. 화면은 다듬은
    쪽을 보여주되 원문을 되짚을 수 있게 둔다 — 사람이 말한 그대로가 자산이다.

    맥락(context)도 함께 내려준다. 원문 아래에 "이 기억에서 발견된 맥락"으로
    붙는 파생값이고, 원문을 대신하지 않는다 (services/memory_context.py).
    """
    media = []
    for media_id in memory.get("media_ids") or []:
        node = graph_manager.get_node(media_id)
        if not node or node.get("node_type") != NodeType.MEDIA:
            continue
        media.append({
            "id": node["id"],
            "media_type": node.get("media_type", "photo"),
            "file_path": node.get("file_path", ""),
            "thumbnail_path": node.get("thumbnail_path"),
            "duration_sec": node.get("duration_sec"),
            "transcript": node.get("transcript"),
            "waveform": node.get("waveform") or [],
            "question": question_for_media(node["id"]),
        })

    return {
        "id": memory["id"],
        "content": memory.get("content", ""),
        "polished": memory.get("polished"),
        "kind": memory.get("kind") or MemoryKind.CONTRIBUTION.value,
        "differs": bool(memory.get("differs")),
        "source_type": memory.get("source_type"),
        "created_at": memory.get("created_at"),
        "contributor": _person_ref(memory.get("contributor_id")),
        "media": media,
        # 이 기억에서 뽑아낸 맥락 (없으면 None). 원문을 대신하지 않는다.
        "context": memory_context.view(memory.get("context"), visible_media_ids),
    }


def detail(event_id: str, viewer_id: Optional[str] = None) -> Optional[dict]:
    """추억 상세 (기획안 09 기억 상세 화면 구조)

    사진·영상 / 제목·날짜·장소·함께한 사람 / 최초 작성자의 기억 / 나도 기억나요 /
    가족이 더한 기억 / 다르게 기억한다는 안내 / 함께 기억한 이야기를 한 번에
    내려준다. 화면이 조각마다 서버를 다시 부르지 않게 하는 것이 목적이다.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    connected = graph_manager.get_connected_nodes(event_id)
    participants = [n for n in connected if n.get("node_type") == NodeType.PERSON]
    media = visibility.filter_media(
        [n for n in connected if n.get("node_type") == NodeType.MEDIA], viewer_id
    )
    place = graph_manager.get_node(event.get("location_id") or "")
    if place and place.get("node_type") != NodeType.PLACE:
        place = None

    items = memories_of(event_id, viewer_id)
    first = author_memory(event_id, items)
    state = state_of(event_id, viewer_id) or {}
    # 맥락이 가리키는 사진도 이 사람이 볼 수 있는 것만 내려간다
    visible_media_ids = {m["id"] for m in media}

    return {
        "id": event["id"],
        "title": event.get("title", ""),
        "description": event.get("description", ""),
        "date_start": event.get("date_start"),
        "date_end": event.get("date_end"),
        "place": {"id": place["id"], "name": place.get("name", "")} if place else None,
        "created_at": event.get("created_at"),
        "author": state.get("author"),
        "participants": [
            {
                "id": p["id"],
                "name": p.get("name", ""),
                "relation": p.get("relation", ""),
                "thumbnail_url": p.get("thumbnail_url"),
            }
            for p in participants
        ],
        "media": [
            {
                "id": m["id"],
                "media_type": m.get("media_type", "photo"),
                "file_path": m.get("file_path", ""),
                "thumbnail_path": m.get("thumbnail_path"),
                "duration_sec": m.get("duration_sec"),
                "transcript": m.get("transcript"),
                "waveform": m.get("waveform") or [],
                "speaker_id": m.get("speaker_id"),
                # 인터뷰 녹음이면 무슨 질문에 답한 것인지 (음성만 해당)
                "question": (
                    question_for_media(m["id"])
                    if m.get("media_type") == MediaType.AUDIO
                    else None
                ),
            }
            for m in media
        ],
        "author_memory": _memory_view(first, visible_media_ids) if first else None,
        "contributions": [
            _memory_view(m, visible_media_ids)
            for m in items
            if m.get("id") != (first or {}).get("id")
        ],
        "state": state.get("state", MemoryState.ALONE.value),
        "varied": state.get("varied", False),
        "echo_count": state.get("echo_count", 0),
        "echoed_by": state.get("echoed_by", []),
        "i_echoed": bool(viewer_id) and any(
            e.get("person_id") == viewer_id for e in (event.get("echoes") or [])
        ),
        "i_added": bool(viewer_id) and any(
            m.get("contributor_id") == viewer_id for m in items
        ),
        "together_story": event.get("together_story"),
        "together_story_at": event.get("together_story_at"),
        # 이야기를 쓴 뒤에 기억이 더 쌓였거나 함께한 사람이 늘었는가
        # (화면이 "다시 만들기"를 권한다). 사람이 늘어나는 자리는 사진에서
        # 직접 지목하는 길이다 — 얼굴 인식이 놓친 할머니를 나중에 지목하면
        # 이미 쓰인 이야기에는 아직 할머니가 없다.
        #
        # 사람 수는 0일 때 세지 않는다. 이 값을 남기기 전에 쓰인 이야기가 0으로
        # 남아 있어, 그것까지 낡았다고 하면 예전 추억 전부에 "다시 만들기"가 뜬다.
        "together_story_stale": bool(
            event.get("together_story")
            and (
                (event.get("together_story_basis") or 0) < len(items)
                or 0 < (event.get("together_story_persons") or 0) < len(participants)
            )
        ),
    }


def feed(viewer_id: Optional[str] = None, limit: int = 30) -> list[dict]:
    """기억 이어가기 목록

    처리해야 할 확인 요청 목록이 아니다. 다른 가족이 만든 추억을 보고, 기억이
    떠오르면 더하는 자리다. 그래서 정렬은 "급한 것"이 아니라 "내가 아직 아무
    말도 얹지 않은 최근 추억"이 앞이다. 아무것도 하지 않아도 된다.
    """
    items = []
    for event in graph_manager.get_events():
        state = state_of(event["id"], viewer_id)
        if not state:
            continue

        memories = memories_of(event["id"], viewer_id)
        first = author_memory(event["id"], memories)
        connected = graph_manager.get_connected_nodes(event["id"])
        media = visibility.filter_media(
            [n for n in connected if n.get("node_type") == NodeType.MEDIA], viewer_id
        )
        photos = [m for m in media if m.get("media_type") != "audio"]
        visible_media_ids = {m["id"] for m in media}
        place = graph_manager.get_node(event.get("location_id") or "")
        if place and place.get("node_type") != NodeType.PLACE:
            place = None

        author = state.get("author") or {}
        mine = bool(viewer_id) and author.get("id") == viewer_id
        i_added = bool(viewer_id) and any(
            m.get("contributor_id") == viewer_id for m in memories
        )

        items.append({
            "event_id": event["id"],
            "title": event.get("title", ""),
            "date_start": event.get("date_start"),
            "place": {"id": place["id"], "name": place.get("name", "")} if place else None,
            "author": state.get("author"),
            "participants": [
                {"id": p["id"], "name": p.get("name", ""), "relation": p.get("relation", "")}
                for p in connected
                if p.get("node_type") == NodeType.PERSON
            ],
            "thumbs": [
                m.get("thumbnail_path") or m.get("file_path", "")
                for m in photos[:3]
                if m.get("thumbnail_path") or m.get("file_path")
            ],
            "media_count": len(media),
            "author_memory": _memory_view(first, visible_media_ids) if first else None,
            "contributions": [
                _memory_view(m, visible_media_ids)
                for m in memories
                if m.get("id") != (first or {}).get("id")
            ],
            "state": state["state"],
            "varied": state["varied"],
            "echo_count": state["echo_count"],
            "echoed_by": state["echoed_by"],
            "i_echoed": bool(viewer_id) and any(
                e.get("person_id") == viewer_id for e in (event.get("echoes") or [])
            ),
            "i_added": i_added,
            "mine": mine,
            "created_at": event.get("created_at"),
        })

    # 내가 만든 추억은 뒤로 (여기는 남의 기억에 얹는 자리다), 아직 아무 말도
    # 얹지 않은 것을 앞으로, 그 안에서는 최근 것 먼저.
    items.sort(
        key=lambda i: (i.get("created_at") or "", i.get("date_start") or ""),
        reverse=True,
    )
    items.sort(key=lambda i: (1 if i["mine"] else 0, 1 if i["i_added"] else 0))
    return items[:limit]


# --- AI ---------------------------------------------------------------------


_FILLER = ("음,", "어,", "그,", "저기,", "뭐,", "음…", "어…")


def _tidy_fallback(raw: str) -> str:
    """모델 없이 문장을 다듬는다 (군말 제거 + 마침표)

    LLM이 없어도 화면이 비지 않아야 한다. 대신 사람 말을 다시 쓰지는 않는다 —
    할 수 있는 것은 군말 제거와 공백 정리뿐이고, 그 이상은 원문을 그대로 둔다.
    """
    text = " ".join((raw or "").split())
    for filler in _FILLER:
        if text.startswith(filler):
            text = text[len(filler):].strip()
    if text and text[-1] not in ".!?…":
        text += "."
    return text


async def polish(raw: str) -> tuple[str, bool]:
    """음성을 옮긴 글을 읽기 좋은 문장으로 정리한다

    원문은 건드리지 않는다. 여기서 나온 문장은 MemoryNode.polished에 따로 들어가고,
    화면은 원문을 함께 되짚을 수 있게 둔다 (기획안 07: 원본 음성·텍스트 유지).

    Returns:
        (다듬은 문장, AI가 썼는지)
    """
    raw = (raw or "").strip()
    if not raw:
        return "", False

    if not llm_client.is_enabled("extract"):
        return _tidy_fallback(raw), False

    result = await llm_client.complete(
        [
            {
                "role": "system",
                "content": (
                    "너는 가족이 말한 기억을 읽기 좋게 다듬는 편집자야.\n"
                    "규칙:\n"
                    "1. 내용을 더하거나 빼지 마. 없는 사실을 만들지 마.\n"
                    "2. 말투는 남기고 군말(음, 어, 그)과 반복만 정리해.\n"
                    "3. 한두 문장으로. 한국어로.\n"
                    "4. 설명 없이 다듬은 문장만 출력해."
                ),
            },
            {"role": "user", "content": raw},
        ],
        max_tokens=300,
        thinking=False,
        temperature=0.2,
        purpose="extract",
    )

    if not result:
        return _tidy_fallback(raw), False

    cleaned = " ".join(result.split()).strip().strip('"')
    return (cleaned or _tidy_fallback(raw)), bool(cleaned)


async def extract_context(event_id: str, memory_id: str) -> Optional[dict]:
    """저장된 기억에서 맥락을 뽑아 그 기억에 붙인다 (원문은 그대로 둔다)

    순서를 바꾸지 않는다. 문장을 먼저 저장하고 그 다음에 맥락을 뽑는다 — 모델
    호출이 실패하든 형식이 어긋나든 가족이 남긴 말은 이미 그래프에 있다.

    사건은 건드리지 않는다. 제목·날짜·장소·참여자는 여기서 바뀌지 않고, 사진을
    새로 잇지도 않는다. 맥락은 기억 노드 안에만 들어간다
    (services/memory_context.py의 첫 주석이 그 이유를 적어 두었다).

    Returns:
        붙인 맥락. 뽑을 것이 없거나 모델을 부를 수 없으면 None.
    """
    memory = graph_manager.get_node(memory_id)
    if not memory or memory.get("node_type") != NodeType.MEMORY:
        return None

    context = await memory_context.extract(
        memory.get("content") or "", memory.get("contributor_id")
    )
    if not context:
        return None

    context = memory_context.resolve_media(context, event_id, memory)
    graph_manager.update_node(memory_id, {"context": context})
    return context


def _story_fallback(title: str, entries: list[dict], persons: Optional[list[dict]] = None) -> str:
    """모델 없이 여러 기억을 잇는다

    문장을 새로 쓰지 않고 누가 무엇을 기억하는지 나열한다. AI가 없을 때 이야기를
    지어내면 그게 가장 나쁜 실패다 — 가족사가 근거 없이 불어난다.

    함께한 사람은 한 줄로 적는다. 기억을 남긴 사람만 나열하면, 사진에 있는데
    아직 아무 말도 남기지 않은 사람은 — 나중에 직접 지목한 할머니가 그렇다 —
    모델이 없는 동안 이야기에서 통째로 빠진다.
    """
    lines = []
    for entry in entries:
        # 이름과 호칭을 함께 적는다 ("김민수(아빠)"). 이름만 적으면 가족이 서로를
        # 부르는 말이 이야기에서 사라진다 (memory_context.person_label).
        name = memory_context.person_label(entry) or "가족"
        text = entry.get("text") or ""
        if text:
            lines.append(f"{name}: {text}")
    if not lines:
        return ""
    head = f"'{title}'에 대해 가족이 남긴 기억입니다."
    labels = memory_context.person_labels(persons or [])
    if labels:
        head += f" 함께한 사람은 {', '.join(labels)}입니다."
    tail = "누가 맞는지는 정하지 않았습니다. 서로 다른 기억도 그대로 함께 남아 있습니다."
    return "\n".join([head] + lines + [tail])


async def compose_together_story(event_id: str, viewer_id: Optional[str] = None) -> Optional[dict]:
    """여러 사람의 기억을 엮어 "함께 기억한 이야기"를 쓴다

    AI는 누가 맞는지 판정하지 않는다. 공통된 내용은 함께 서술하고, 갈리는 부분은
    "누구는 이렇게, 누구는 저렇게 기억한다"로 남긴다. 이 규칙을 프롬프트에서
    빼면 모델은 반드시 한쪽으로 정리한다.

    결과는 사건 노드에 저장한다. 화면이 매번 모델을 부르지 않게 하고, 기억이 더
    쌓이면 낡았다는 표시(together_story_stale)가 화면에 뜬다.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    items = memories_of(event_id, viewer_id)
    if not items:
        return None

    entries = []
    for memory in items:
        person = _person_ref(memory.get("contributor_id")) or {}
        entries.append({
            "name": person.get("name") or "가족",
            "relation": person.get("relation") or "",
            "text": memory.get("polished") or memory.get("content") or "",
            "differs": bool(memory.get("differs")),
        })

    title = event.get("title", "")
    place = graph_manager.get_node(event.get("location_id") or "") or {}
    connected = graph_manager.get_connected_nodes(event_id)
    participants = [n for n in connected if n.get("node_type") == NodeType.PERSON]

    facts = [f"제목: {title}"]
    if event.get("date_start"):
        facts.append(f"날짜: {event['date_start']}")
    if place.get("name"):
        facts.append(f"장소: {place['name']}")
    if participants:
        # 함께한 사람도 사실이다. 넘기지 않으면 이야기는 기억을 남긴 사람만
        # 부르고, 사진에 있는데 아직 아무 말도 남기지 않은 사람은 — 얼굴 인식이
        # 놓쳐 나중에 직접 지목한 할머니가 대표적이다 — 이야기에서 빠진다.
        facts.append(
            "함께한 사람: " + ", ".join(memory_context.person_labels(participants))
        )

    # 원문을 맥락으로 바꿔치우지 않는다. 원문(위 entries)에 맥락과 사진 설명을
    # 더해 함께 넘긴다 — 맥락만 주면 모델은 사람이 실제로 쓴 말투와 세부를 잃고,
    # 원문만 주면 여러 기억이 같은 장면을 말하고 있다는 것을 읽지 못한다.
    visible_media = visibility.filter_media(
        [n for n in connected if n.get("node_type") == NodeType.MEDIA], viewer_id
    )
    contexts = memory_context.from_memories(items, {m["id"] for m in visible_media})
    context_lines = "\n".join(memory_context.prompt_line(c) for c in contexts)
    scene_lines = "\n".join(
        f"- {m['id']}: {m['scene_description']}"
        for m in visible_media
        if m.get("scene_description")
    )

    story = None
    ai_used = False

    if llm_client.is_enabled():
        # 대괄호로 표시하지 않는다. 모델이 그것을 본문에 그대로 옮겨 적는다
        # (기억 맥락에서 "[사진에서 확인되지 않음]"이 실제로 이야기에 나왔다).
        lines = "\n".join(
            f"- {memory_context.person_label(e) or '가족'}: {e['text']}"
            + (" — 다르게 기억한다고 밝혔다" if e["differs"] else "")
            for e in entries
        )
        story = await llm_client.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "너는 한 가족의 기억을 모아 하나의 이야기로 정리하는 기록자야.\n"
                        "규칙:\n"
                        "1. 누가 맞는지 판단하지 마. 사실을 하나로 정하지 마.\n"
                        "2. 여러 사람이 같이 말한 내용은 함께 서술해.\n"
                        "3. 서로 다르게 기억하는 부분은 '누구는 ~로, 누구는 ~로 기억한다'처럼"
                        " 양쪽을 모두 남겨.\n"
                        "4. 주어진 기억에 없는 사실을 만들지 마.\n"
                        "5. 가족이 기억하는 것은 그 사람의 관점이다. 사진에 그 장면이"
                        " 있다고 쓰지 말고 '누구는 ~를 기억한다'로 써.\n"
                        "6. 대괄호로 묶은 제목은 자료를 나누는 표시다. 본문에 옮겨 적지 마.\n"
                        "7. '함께한 사람'은 한 명도 빼지 말고 이야기 안에서 불러라."
                        " 아직 아무 기억도 남기지 않은 사람도 그 자리에 있었다."
                        " 다만 그 사람이 무엇을 했는지는 주어진 기억에 있는 것만 써.\n"
                        "8. 사람은 '김민수(아빠)'처럼 이름과 호칭을 함께 적어. 주어진"
                        " 모양 그대로 쓰면 된다 — 이름만 쓰거나 호칭만 쓰지 마.\n"
                        "9. 3~5문장, 담담한 한국어 서술로. 제목이나 머리말 없이 본문만."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "[사건]\n"
                        + "\n".join(facts)
                        + "\n\n[가족이 남긴 기억]\n"
                        + lines
                        + (f"\n\n[가족이 기억하는 것]\n{context_lines}" if context_lines else "")
                        + (f"\n\n[연결된 사진의 장면 설명]\n{scene_lines}" if scene_lines else "")
                    ),
                },
            ],
            max_tokens=700,
            model=EXAONE_PLANNER_MODEL if len(entries) <= 2 else None,
        )
        ai_used = bool(story)

    if not story:
        story = _story_fallback(title, entries, participants)

    # 프롬프트 제목을 베껴 오면 떼어낸다. "[사진에서 확인되지 않음]"이 이야기
    # 본문에 나온 적이 있다 — 프롬프트에 "옮기지 마라"를 적어도 막히지 않는다
    # (interview_engine._clean_question과 같은 판단이다).
    story = memory_context.strip_prompt_marks(story)
    if not story:
        return None
    if ai_used:
        # 규칙 8을 적어도 모델은 "아빠 김민수"라고 쓴다. 모델이 쓴 산문에만
        # 적용한다 — 폴백은 가족의 원문을 그대로 나열하므로 손대지 않는다.
        story = memory_context.label_person_mentions(story, participants)
    # 규칙 7을 적어도 모델은 기억을 남긴 사람만 부르고 나머지를 지운다. 빠진
    # 사람은 한 줄로 잇는다 — 사진에서 지목한 사람이 이야기에 없으면, 지목한
    # 사람에게는 지목이 저장되지 않은 것으로 보인다.
    story = memory_context.ensure_persons_named(story, participants)

    now = datetime.now().isoformat()
    graph_manager.update_node(event_id, {
        "together_story": story,
        "together_story_at": now,
        "together_story_basis": len(items),
        # 이 이야기가 몇 사람을 담고 썼는지. 나중에 지목한 사람이 늘면 화면이
        # "다시 만들기"를 권한다 (detail의 together_story_stale).
        "together_story_persons": len(participants),
    })

    return {
        "event_id": event_id,
        "story": story,
        "at": now,
        "basis": len(items),
        "ai_used": ai_used,
    }
