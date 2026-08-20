"""추억 · 기억 이어가기 회귀 테스트

    python tests/test_memories.py

예전 tests/test_verification.py를 대신한다. 그 테스트는 "전원이 확인하면 완료"
구조를 지켰고, 그 구조 자체가 없어졌다. 지금 지켜야 하는 약속은 다르다.

    1. 한 사람이 만들면 그 자리에서 게시된다 (승인 대기 상태가 없다)
    2. 더한 기억은 원본을 덮어쓰지 않는다
    3. 다르게 기억해도 한쪽을 정답으로 정하지 않는다
    4. 나도 기억나요는 눌렀다 뗄 수 있고, 아무도 안 눌러도 추억은 그대로다
    5. 남긴 기억은 거둘 수 있다. 문장만 지워지고 원본은 추억에 남는다
    6. 추억도 거둘 수 있다. 그 안의 기억까지 지워지고 원본은 사진첩에 남는다

그래프를 실제로 바꾸므로 만든 것은 끝에서 지운다. 데모 데이터를 더럽히지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from datetime import datetime
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


def test_memory_can_be_removed_by_the_person_who_left_it():
    """남긴 기억은 거둘 수 있다. 함께 올린 원본은 추억에 남는다"""
    photos = [
        m for m in graph_manager.get_media_for_event(EVENT)
        if m.get("media_type") == "photo"
    ]
    assert photos, "시드 사건에 사진이 없다"
    photo = photos[0]

    memory = memories.add_contribution(
        EVENT,
        OTHER,
        "지웠다가 다시 생각나면 또 적을 수 있어야 해요.",
        media_ids=[photo["id"]],
    )
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    try:
        result = memories.delete_memory(EVENT, memory["id"])
        assert result, "지우지 못했다"
        assert graph_manager.get_node(memory["id"]) is None, "기억이 남아 있다"

        # 문장에 매달렸던 관계도 함께 끊긴다 (근거 · 남긴 사람 · 사건)
        assert not any(
            memory["id"] in (e["source"], e["target"])
            for e in graph_manager.get_all_edges()
        ), "지운 기억의 엣지가 남았다"

        # 원본은 추억에 그대로 있다 — 원본을 지우는 자리는 사진첩이다
        assert result["kept_media"] == [photo["id"]], result["kept_media"]
        assert graph_manager.get_node(photo["id"]), "사진이 함께 지워졌다"

        detail = memories.detail(EVENT, OTHER)
        assert any(m["id"] == photo["id"] for m in detail["media"]), detail["media"]
        assert all(
            m["id"] != memory["id"] for m in detail["contributions"]
        ), "상세에 지운 기억이 남아 있다"
        print("  기억 삭제 OK (원본은 남는다)")
    finally:
        _cleanup()


def test_deleted_author_memory_does_not_promote_someone_elses():
    """작성자가 첫 기억을 거두면 남의 기억이 그 자리로 올라오지 않는다"""
    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (첫 기억 삭제)",
        description="내가 처음 적은 문장입니다.",
        person_ids=[AUTHOR, OTHER],
    )
    _created.append(event["id"])

    first = memories.author_memory(event["id"])
    assert first, "최초 작성자의 기억이 없다"
    _created.append(first["id"])

    added = memories.add_contribution(event["id"], OTHER, "저는 이렇게 기억해요.")
    assert added, "기억을 더하지 못했다"
    _created.append(added["id"])

    try:
        assert memories.delete_memory(event["id"], first["id"]), "지우지 못했다"

        detail = memories.detail(event["id"], AUTHOR)
        assert detail["author_memory"] is None, detail["author_memory"]
        assert [m["id"] for m in detail["contributions"]] == [added["id"]], (
            detail["contributions"]
        )
        # 한 사람이 남긴 문장 하나뿐이다. "함께 기억"으로 읽히면 안 된다.
        assert detail["state"] == MemoryState.ALONE.value, detail["state"]
        print("  작성자 자리 보존 OK")
    finally:
        _cleanup()


def test_deleting_memory_clears_a_story_that_quotes_it():
    """지운 문장을 담은 "함께 기억한 이야기"는 함께 지운다"""
    kept = {
        key: graph_manager.get_node(EVENT).get(key)
        for key in ("together_story", "together_story_at", "together_story_basis")
    }
    try:
        quoted = memories.add_contribution(EVENT, OTHER, "이야기에 이 문장이 들어갑니다.")
        assert quoted, "기억을 더하지 못했다"
        _created.append(quoted["id"])

        # 이 기억보다 뒤에 쓰인 이야기 — 문장을 담고 있다
        graph_manager.update_node(EVENT, {
            "together_story": "가족이 남긴 기억입니다. " + quoted["content"],
            "together_story_at": datetime.now().isoformat(),
            "together_story_basis": 2,
        })
        result = memories.delete_memory(EVENT, quoted["id"])
        assert result and result["story_cleared"] is True, result
        assert not graph_manager.get_node(EVENT).get("together_story"), "이야기가 남았다"

        # 기억보다 앞서 쓰인 이야기는 그 문장을 볼 수 없었다. 지울 이유가 없다.
        graph_manager.update_node(EVENT, {
            "together_story": "예전에 쓴 이야기",
            "together_story_at": "2020-01-01T00:00:00",
            "together_story_basis": 1,
        })
        later = memories.add_contribution(EVENT, OTHER, "이야기보다 나중에 남긴 기억입니다.")
        assert later, "기억을 더하지 못했다"
        _created.append(later["id"])

        result = memories.delete_memory(EVENT, later["id"])
        assert result and result["story_cleared"] is False, result
        assert graph_manager.get_node(EVENT).get("together_story") == "예전에 쓴 이야기"
        print("  이야기 정리 OK")
    finally:
        graph_manager.update_node(EVENT, kept)
        _cleanup()


def test_memory_of_another_event_is_not_deletable_here():
    """사건을 함께 받는다 — 다른 사건의 기억은 여기서 지워지지 않는다"""
    memory = memories.add_contribution(EVENT, OTHER, "이 기억은 E01의 것입니다.")
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    try:
        others = [e["id"] for e in graph_manager.get_events() if e["id"] != EVENT]
        assert others, "다른 사건이 없다"

        assert memories.delete_memory(others[0], memory["id"]) is None, "다른 사건에서 지워졌다"
        assert graph_manager.get_node(memory["id"]), "지워지면 안 되는 기억이 지워졌다"
        print("  사건 확인 OK")
    finally:
        _cleanup()


def test_event_can_be_deleted_with_its_memories():
    """추억을 지우면 그 안의 기억 문장까지 지워지고, 사진은 사진첩에 남는다

    사진첩에서 사진을 다 지워도 추억은 남는다 (원본을 지울 때 끊기는 것은
    연결뿐이다). 그 추억을 치우는 자리가 delete_event다.
    """
    photos = [
        m for m in graph_manager.get_media_for_event(EVENT)
        if m.get("media_type") == "photo"
    ]
    assert photos, "시드 사건에 사진이 없다"
    photo = photos[0]

    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (추억 삭제)",
        description="지울 추억에 남긴 내 기억입니다.",
        person_ids=[AUTHOR, OTHER],
        media_ids=[photo["id"]],
    )
    _created.append(event["id"])

    mine = memories.author_memory(event["id"])
    assert mine, "최초 작성자의 기억이 없다"
    _created.append(mine["id"])

    added = memories.add_contribution(event["id"], OTHER, "저도 여기 있었어요.")
    assert added, "기억을 더하지 못했다"
    _created.append(added["id"])

    try:
        result = memories.delete_event(event["id"])
        assert result, "지우지 못했다"

        assert graph_manager.get_node(event["id"]) is None, "추억이 남아 있다"
        assert set(result["deleted_memories"]) == {mine["id"], added["id"]}, (
            result["deleted_memories"]
        )
        for memory_id in (mine["id"], added["id"]):
            assert graph_manager.get_node(memory_id) is None, "기억 문장이 남았다"

        # 사건도 기억도 없어졌으니 그것들에 매달렸던 관계도 남지 않는다
        gone = {event["id"], mine["id"], added["id"]}
        assert not any(
            gone & {e["source"], e["target"]} for e in graph_manager.get_all_edges()
        ), "지운 추억의 엣지가 남았다"

        # 원본은 사진첩에 그대로 있고, 원래 붙어 있던 사건에서도 빠지지 않는다
        assert result["kept_media"] == [photo["id"]], result["kept_media"]
        assert graph_manager.get_node(photo["id"]), "사진이 함께 지워졌다"
        assert any(
            m["id"] == photo["id"] for m in graph_manager.get_media_for_event(EVENT)
        ), "다른 사건의 사진 연결이 끊겼다"

        # 시드 사건의 기억은 건드리지 않는다
        assert memories.memories_of(EVENT), "다른 사건의 기억이 함께 지워졌다"
        print("  추억 삭제 OK (기억은 함께, 사진은 남는다)")
    finally:
        _cleanup()


def test_delete_event_only_touches_events():
    """사건이 아닌 id로는 아무것도 지워지지 않는다"""
    assert memories.delete_event(AUTHOR) is None, "사람이 지워졌다"
    assert graph_manager.get_node(AUTHOR), "지워지면 안 되는 인물이 지워졌다"
    assert memories.delete_event("없는-사건") is None, "없는 사건을 지웠다고 한다"
    print("  사건만 지운다 OK")


TESTS = [
    test_new_memory_is_published_immediately,
    test_contribution_does_not_overwrite_original,
    test_different_memory_is_kept_not_resolved,
    test_echo_toggles_and_is_optional,
    test_feed_puts_others_memories_first,
    test_media_attaches_only_when_asked,
    test_memory_can_be_removed_by_the_person_who_left_it,
    test_deleted_author_memory_does_not_promote_someone_elses,
    test_deleting_memory_clears_a_story_that_quotes_it,
    test_memory_of_another_event_is_not_deletable_here,
    test_event_can_be_deleted_with_its_memories,
    test_delete_event_only_touches_events,
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
