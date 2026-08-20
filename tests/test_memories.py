"""추억 · 기억 이어가기 회귀 테스트

    python tests/test_memories.py

예전 tests/test_verification.py를 대신한다. 그 테스트는 "전원이 확인하면 완료"
구조를 지켰고, 그 구조 자체가 없어졌다. 지금 지켜야 하는 약속은 다르다.

    1. 한 사람이 만들면 그 자리에서 게시된다 (승인 대기 상태가 없다)
    2. 더한 기억은 원본을 덮어쓰지 않는다
    3. 다르게 기억해도 한쪽을 정답으로 정하지 않는다
    4. 나도 기억나요는 눌렀다 뗄 수 있고, 아무도 안 눌러도 추억은 그대로다

그래프를 실제로 바꾸므로 만든 것은 끝에서 지운다. 데모 데이터를 더럽히지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import (  # noqa: E402
    MemoryKind,
    MemoryState,
    NodeType,
    RelationType,
)
from backend.services import memories  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행 (시드에 김민수의 기억 M001이 하나 붙어 있다)
AUTHOR = "P01"  # 김민수
OTHER = "P02"  # 박서연

_created: list[str] = []


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _cleanup():
    """이 테스트가 만든 노드와 공감 표시를 지운다"""
    for node_id in _created:
        graph_manager.delete_node(node_id)
    _created.clear()
    graph_manager.update_node(EVENT, {"echoes": []})


def test_new_memory_is_published_immediately():
    """만들면 바로 가족 공간에 있다 — 확인 대기 상태가 없다"""
    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억",
        description="테스트로 남긴 기억입니다.",
        date_start="2024-01-02",
        place_name="테스트 장소",
        person_ids=[AUTHOR, OTHER],
    )
    _created.append(event["id"])
    if event.get("location_id"):
        _created.append(event["location_id"])

    try:
        detail = memories.detail(event["id"], AUTHOR)
        assert detail, "상세를 만들지 못했다"
        assert detail["author"]["id"] == AUTHOR, detail["author"]

        # 작성자의 기억이 사람에게 귀속된 문장으로 남는다
        first = detail["author_memory"]
        assert first, "최초 작성자의 기억이 없다"
        assert first["kind"] == MemoryKind.AUTHOR.value, first["kind"]
        assert first["contributor"]["id"] == AUTHOR, first["contributor"]
        _created.append(first["id"])

        # 아무도 확인하지 않았지만 이미 게시된 상태다
        assert detail["state"] == MemoryState.ALONE.value, detail["state"]
        assert detail["echo_count"] == 0, detail["echo_count"]

        # 참여자로 지목한 사람이 그래프에 이어졌다
        names = {p["id"] for p in detail["participants"]}
        assert {AUTHOR, OTHER} <= names, names
        print("  즉시 게시 OK")
    finally:
        _cleanup()


def test_contribution_does_not_overwrite_original():
    """더한 기억은 원본을 건드리지 않는다"""
    before = graph_manager.get_node(EVENT)
    before_title = before.get("title")
    before_desc = before.get("description")
    first_before = memories.author_memory(EVENT)

    memory = memories.add_contribution(
        EVENT, OTHER, "이때 아빠가 렌터카 길을 잘못 들어서 엄청 돌아갔던 게 기억나요."
    )
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    try:
        after = graph_manager.get_node(EVENT)
        assert after.get("title") == before_title, "제목이 바뀌었다"
        assert after.get("description") == before_desc, "설명이 바뀌었다"

        first_after = memories.author_memory(EVENT)
        assert first_after["id"] == first_before["id"], "최초 작성자의 기억이 바뀌었다"
        assert first_after["content"] == first_before["content"], "원본 문장이 바뀌었다"

        detail = memories.detail(EVENT, OTHER)
        added = [m["id"] for m in detail["contributions"]]
        assert memory["id"] in added, added
        assert detail["state"] == MemoryState.SHARED.value, detail["state"]
        assert detail["i_added"] is True, detail["i_added"]

        # 기억 → 사건, 사람 → 기억 엣지가 함께 생긴다 (출처 보존)
        edges = graph_manager.get_all_edges()
        assert any(
            e["source"] == memory["id"]
            and e["target"] == EVENT
            and e["relation"] == RelationType.ABOUT
            for e in edges
        ), "ABOUT 엣지가 없다"
        assert any(
            e["source"] == OTHER
            and e["target"] == memory["id"]
            and e["relation"] == RelationType.REMEMBERS
            for e in edges
        ), "REMEMBERS 엣지가 없다"
        print("  원본 보존 OK")
    finally:
        _cleanup()


def test_different_memory_is_kept_not_resolved():
    """다르게 기억해도 한쪽으로 정리하지 않는다"""
    memory = memories.add_contribution(
        EVENT,
        OTHER,
        "환갑 여행은 아니고 그냥 여름휴가였던 것 같아요.",
        differs=True,
    )
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    try:
        state = memories.state_of(EVENT)
        assert state["state"] == MemoryState.VARIED.value, state["state"]
        assert state["varied"] is True, state

        # 원래 기억도 그대로 남아 있다 (지우거나 감추지 않는다)
        detail = memories.detail(EVENT)
        assert detail["author_memory"], "원래 기억이 사라졌다"
        assert any(m["differs"] for m in detail["contributions"]), detail["contributions"]
        print("  다른 기억 보존 OK")
    finally:
        _cleanup()


def test_echo_toggles_and_is_optional():
    """나도 기억나요는 눌렀다 뗄 수 있고, 없어도 추억은 그대로다"""
    try:
        on = memories.toggle_echo(EVENT, OTHER)
        assert on["echoed"] is True, on
        assert on["echo_count"] == 1, on
        assert memories.detail(EVENT, OTHER)["i_echoed"] is True

        off = memories.toggle_echo(EVENT, OTHER)
        assert off["echoed"] is False, off
        assert off["echo_count"] == 0, off

        # 공감이 없어도 추억은 여전히 게시된 상태다 (상태는 기억에서만 파생한다)
        state = memories.state_of(EVENT)
        assert state["state"] in {s.value for s in MemoryState}, state
        print("  공감 토글 OK")
    finally:
        _cleanup()


def test_feed_puts_others_memories_first():
    """기억 이어가기는 남의 추억, 그중 내가 아직 얹지 않은 것을 앞에 둔다"""
    items = memories.feed(OTHER)
    assert items, "목록이 비었다"

    mine_positions = [i for i, item in enumerate(items) if item["mine"]]
    others_positions = [i for i, item in enumerate(items) if not item["mine"]]
    if mine_positions and others_positions:
        assert min(mine_positions) > max(others_positions), (
            "내가 만든 추억이 남의 추억보다 앞에 있다"
        )

    open_items = [i for i, item in enumerate(items) if not item["mine"] and not item["i_added"]]
    added_items = [i for i, item in enumerate(items) if not item["mine"] and item["i_added"]]
    if open_items and added_items:
        assert min(added_items) > max(open_items), "이미 기억을 더한 추억이 앞에 있다"
    print("  목록 순서 OK")


def test_media_attaches_only_when_asked():
    """사진은 사용자가 고른 추억에만 붙는다 (자동 병합 금지)"""
    media = [
        node
        for node in graph_manager.get_media_nodes()
        if node.get("media_type") == "photo"
    ]
    assert media, "시드에 사진이 없다"
    target = media[0]

    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (사진 연결)",
        person_ids=[AUTHOR],
        media_ids=[target["id"]],
    )
    _created.append(event["id"])

    try:
        detail = memories.detail(event["id"], AUTHOR)
        assert any(m["id"] == target["id"] for m in detail["media"]), detail["media"]

        # 붙이라고 하지 않은 다른 사진은 들어오지 않는다
        assert len(detail["media"]) == 1, detail["media"]

        # 만든 추억에도 노드 종류가 그대로다
        assert graph_manager.get_node(event["id"])["node_type"] == NodeType.EVENT
        print("  사진 연결 OK")
    finally:
        # 사진에 붙은 CAPTURED_DURING은 사건을 지우면 함께 사라진다
        _cleanup()


TESTS = [
    test_new_memory_is_published_immediately,
    test_contribution_does_not_overwrite_original,
    test_different_memory_is_kept_not_resolved,
    test_echo_toggles_and_is_optional,
    test_feed_puts_others_memories_first,
    test_media_attaches_only_when_asked,
]


def main():
    _require_seeded_graph()
    print("추억 · 기억 이어가기 회귀 테스트")
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
