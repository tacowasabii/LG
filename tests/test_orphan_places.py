"""아무것도 걸리지 않은 장소 거두기 회귀 테스트

    python tests/test_orphan_places.py

배포된 그래프에 "강원 홍천"과 "경기 수원"이 아무것도 걸리지 않은 점으로 떠
있었다. 더미데이터가 아니다 — 사진 EXIF 좌표에서 짐작한 지명이 추억의 장소 칸에
채워져 장소 노드가 만들어졌고(routers/media.py의 place_guess ->
memories._resolve_place_by_name), 그 추억을 지울 때 장소를 남겨 두었다.

장소는 파생 노드다. 스스로 열리는 화면이 없다 — 지도는 사건을 그리고 사진첩은
원본을 그린다. 그래서 가리키는 것이 없어진 장소는 어디에서도 닿을 수 없다.

여기서 지키는 약속은 셋이다.

    1. 가리키는 것이 하나라도 있으면 손대지 않는다. 엣지든 location_id든
    2. 아무것도 가리키지 않으면 거둔다
    3. 장소가 아닌 노드는 이 판정에 걸리지 않는다 (사람·사진은 연결이 없어도
       각자의 화면이 그대로 나열한다)

추억을 지울 때 이것이 실제로 불리는지는 tests/test_memories.py가 본다.
여기서는 판정 자체를 본다 (services/event_resolver.py).

그래프를 실제로 바꾸므로 만든 것은 끝에서 지운다. 데모 데이터를 더럽히지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import (  # noqa: E402
    Edge,
    EventNode,
    PlaceNode,
    RelationType,
)
from backend.services import event_resolver  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

# 시드에 있는 장소 여덟 곳. 이 테스트가 끝나도 그대로여야 한다
SEEDED_PLACES = 8
PERSON = "P01"  # 김민수

_created: list[str] = []


def _require_seeded_graph():
    if len(graph_manager.get_places()) < SEEDED_PLACES:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _cleanup():
    for node_id in _created:
        graph_manager.delete_node(node_id)
    _created.clear()


def _make_place(name: str) -> str:
    """추억 없이 장소만 만든다 (배포에 남아 있던 것과 같은 모양 — 좌표도 없다)"""
    place = PlaceNode(name=name)
    graph_manager.add_place(place)
    _created.append(place.id)
    return place.id


def _make_event(title: str, place_id: str = "", with_edge: bool = True) -> str:
    """장소를 가리키는 사건. with_edge=False면 location_id로만 가리킨다"""
    event = EventNode(title=title, location_id=place_id or None)
    graph_manager.add_event(event)
    _created.append(event.id)
    if place_id and with_edge:
        graph_manager.add_edge(Edge(
            source=event.id, target=place_id, relation=RelationType.LOCATED_AT,
        ))
    return event.id


def test_place_an_event_points_at_is_kept():
    """사건이 가리키는 장소는 거두지 않는다"""
    place_id = _make_place("테스트 장소 (사건이 있다)")
    _make_event("테스트 추억 (장소를 가리킨다)", place_id)

    try:
        assert not event_resolver.place_is_orphan(place_id), "쓰이는 장소를 고립으로 봤다"
        assert place_id not in [p["id"] for p in event_resolver.orphan_places()], (
            "쓰이는 장소가 목록에 올랐다"
        )
        assert event_resolver.prune_orphan_places([place_id]) == [], "쓰이는 장소를 지웠다"
        assert graph_manager.get_node(place_id), "쓰이는 장소가 사라졌다"
        print("  사건이 가리키는 장소 보존 OK")
    finally:
        _cleanup()


def test_place_reachable_only_through_location_id_is_kept():
    """엣지가 없고 location_id로만 이어진 장소도 거두지 않는다

    엣지만 보면 이 장소는 "아무도 안 쓴다"로 읽힌다. 그런데 사건 목록은
    location_id로 대표 장소를 찾으므로(routers/graph.py list_events) 화면에는
    그 이름이 그대로 나온다. 지우는 판정이라 넓게 잡는다.
    """
    place_id = _make_place("테스트 장소 (location_id로만)")
    _make_event("테스트 추억 (엣지 없이 가리킨다)", place_id, with_edge=False)

    try:
        assert not graph_manager.get_connected_nodes(place_id), "엣지가 생겼다 (전제가 틀렸다)"
        assert not event_resolver.place_is_orphan(place_id), (
            "location_id로 이어진 장소를 고립으로 봤다"
        )
        assert event_resolver.prune_orphan_places([place_id]) == [], "아직 쓰이는 장소를 지웠다"
        assert graph_manager.get_node(place_id), "location_id로 이어진 장소가 사라졌다"
        print("  location_id로만 이어진 장소 보존 OK")
    finally:
        _cleanup()


def test_place_nothing_points_at_is_pruned():
    """아무것도 가리키지 않는 장소는 거둔다 — 홍천·수원이 이 상태였다"""
    hongcheon = _make_place("강원 홍천")
    suwon = _make_place("경기 수원")

    try:
        listed = [p["id"] for p in event_resolver.orphan_places()]
        assert hongcheon in listed and suwon in listed, listed

        pruned = event_resolver.prune_orphan_places([hongcheon, suwon])
        assert set(pruned) == {hongcheon, suwon}, pruned
        assert graph_manager.get_node(hongcheon) is None, "장소가 남았다"
        assert graph_manager.get_node(suwon) is None, "장소가 남았다"

        # 한 번 더 돌려도 안전하다 (부팅마다 불린다)
        assert event_resolver.prune_orphan_places([hongcheon, suwon]) == [], "없는 것을 지웠다고 한다"
        print("  빈 장소 거두기 OK")
    finally:
        _cleanup()


def test_other_node_types_are_never_pruned():
    """장소가 아닌 노드는 이 판정에 걸리지 않는다

    연결이 없는 노드가 곧 쓰레기인 것은 아니다. 사건에 한 번도 나오지 않은
    사람도 가족이고, 추억에 붙지 않은 사진도 사진첩에 있어야 한다.
    """
    lonely_event = _make_event("테스트 추억 (장소가 없다)")

    try:
        for node_id in (PERSON, lonely_event):
            assert not event_resolver.place_is_orphan(node_id), f"{node_id}를 장소로 봤다"
            assert event_resolver.prune_orphan_places([node_id]) == [], f"{node_id}를 지웠다"
            assert graph_manager.get_node(node_id), f"{node_id}가 사라졌다"

        # 없는 id도 조용히 지난다 (부팅에서 불리므로 예외를 던지면 앱이 안 뜬다)
        assert event_resolver.prune_orphan_places(["없는-노드"]) == []
        print("  장소 아닌 노드 보존 OK")
    finally:
        _cleanup()


def test_seeded_places_are_left_alone():
    """시드된 장소 여덟 곳은 하나도 건드리지 않는다"""
    before = {p["id"] for p in graph_manager.get_places()}
    assert len(before) == SEEDED_PLACES, f"시작 상태가 이미 {len(before)}개다"

    event_resolver.prune_orphan_places(list(before))

    after = {p["id"] for p in graph_manager.get_places()}
    assert after == before, f"사라진 장소: {before - after}"
    assert event_resolver.orphan_places() == [], event_resolver.orphan_places()
    print("  시드 장소 보존 OK")


TESTS = [
    test_place_an_event_points_at_is_kept,
    test_place_reachable_only_through_location_id_is_kept,
    test_place_nothing_points_at_is_pruned,
    test_other_node_types_are_never_pruned,
    # 마지막에 둔다 — 앞의 테스트가 남긴 것이 없는지까지 함께 본다
    test_seeded_places_are_left_alone,
]


def main():
    _require_seeded_graph()
    print("빈 장소 거두기 회귀 테스트")
    failed = 0
    for test in TESTS:
        try:
            test()
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {test.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {test.__name__}: {type(e).__name__}: {e}")
    _cleanup()
    if failed:
        print(f"\n{failed}개 실패")
        sys.exit(1)
    print(f"\n{len(TESTS)}개 통과")


if __name__ == "__main__":
    main()
