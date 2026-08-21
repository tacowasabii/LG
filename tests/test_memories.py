"""추억 · 기억 이어가기 회귀 테스트

    python tests/test_memories.py

예전 tests/test_verification.py를 대신한다. 그 테스트는 "전원이 확인하면 완료"
구조를 지켰고, 그 구조 자체가 없어졌다. 지금 지켜야 하는 약속은 다르다.

    1. 한 사람이 만들면 그 자리에서 게시된다 (승인 대기 상태가 없다)
    2. 더한 기억은 원본을 덮어쓰지 않는다
    3. 다르게 기억해도 한쪽을 정답으로 정하지 않는다
    4. 나도 기억나요는 눌렀다 뗄 수 있고, 아무도 안 눌러도 추억은 그대로다
    5. 남긴 기억은 거둘 수 있다. 목소리는 함께 지워지고 사진은 추억에 남는다
    6. 추억도 거둘 수 있다. 기억·사진·영상·목소리와 원본 파일까지 함께 지워진다.
       다른 추억에도 붙어 있는 원본만 남는다
    7. 정보(제목·날짜·장소·함께한 사람)는 뒤늦게 고칠 수 있다. 고쳐도 가족이 남긴
       기억과 "나도 기억나요"는 그대로 있다

그래프를 실제로 바꾸므로 만든 것은 끝에서 지운다. 데모 데이터를 더럽히지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import MEDIA_DIR  # noqa: E402
from backend.models.graph_models import (  # noqa: E402
    Edge,
    MediaNode,
    MediaType,
    MemoryKind,
    MemoryState,
    NodeType,
    RelationType,
)
from backend.services import event_resolver, memories  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행 (시드에 김민수의 기억 M001이 하나 붙어 있다)
AUTHOR = "P01"  # 김민수
OTHER = "P02"  # 박서연
THIRD = "P03"  # 김하늘 (기억을 남기지 않은 사람 — 참여자로 더하는 자리에 쓴다)

_created: list[str] = []
_temp_files: list = []


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
    for path in _temp_files:
        if path.exists():
            path.unlink()
    _temp_files.clear()
    graph_manager.update_node(EVENT, {"echoes": []})


def _make_temp_audio(event_id: str = EVENT) -> MediaNode:
    """지워도 되는 임시 녹음 (시드 음성을 건드리지 않기 위해)

    기억과 함께 지워지는지 보려면 실제 파일이 있어야 한다 — 노드만 만들면 파일이
    지워졌는지 확인할 수 없다.

    어느 추억에 붙일지 받는다. 추억을 지울 때 원본까지 사라지는지 보는 테스트는
    시드 추억(E01)에 붙지 않은 녹음이 필요하다 — 두 추억에 걸린 원본은 남기는
    것이 규칙이다 (memories._media_still_used).
    """
    index = len(_temp_files) + 1
    file_name = f"test-memory-voice-{index}.webm"
    path = MEDIA_DIR / file_name
    path.write_bytes(b"not-a-real-recording")
    _temp_files.append(path)

    node = MediaNode(
        media_type=MediaType.AUDIO,
        file_path=f"/media-files/{file_name}",
        original_filename=file_name,
        duration_sec=3.0,
        transcript="테스트로 남긴 목소리입니다.",
    )
    graph_manager.add_media(node)
    _created.append(node.id)

    # 실제 흐름과 같게 추억에 잇는다. 화면은 녹음을 올릴 때 추억을 함께 보내고
    # (MemoryComposer -> uploadVoice(eventId)), media 라우터가 이 엣지를 만든다.
    # 이 엣지 때문에 기억을 지워도 추억의 "가족이 남긴 목소리"에 계속 남아 있었다.
    if event_id:
        graph_manager.add_edge(Edge(
            source=node.id, target=event_id, relation=RelationType.CAPTURED_DURING,
        ))
    return node


def _make_temp_photo(event_id: str = "") -> MediaNode:
    """지워도 되는 임시 사진 (시드 사진을 건드리지 않기 위해)

    추억을 지울 때 원본까지 사라지는지 보려면 실제 파일이 있어야 한다 — 노드만
    만들면 파일이 지워졌는지 확인할 수 없다.
    """
    index = len(_temp_files) + 1
    file_name = f"test-memory-photo-{index}.jpg"
    path = MEDIA_DIR / file_name
    path.write_bytes(b"not-a-real-photo")
    _temp_files.append(path)

    node = MediaNode(
        media_type=MediaType.PHOTO,
        file_path=f"/media-files/{file_name}",
        original_filename=file_name,
        scene_description="테스트로 올린 사진입니다.",
    )
    graph_manager.add_media(node)
    _created.append(node.id)

    if event_id:
        graph_manager.add_edge(Edge(
            source=node.id, target=event_id, relation=RelationType.CAPTURED_DURING,
        ))
    return node


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

        # 기억 → 추억, 사람 → 기억 엣지가 함께 생긴다 (출처 보존)
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
        # 사진에 붙은 CAPTURED_DURING은 추억을 지우면 함께 사라진다
        _cleanup()


def test_memory_can_be_removed_by_the_person_who_left_it():
    """남긴 기억은 거둘 수 있다. 함께 올린 원본은 추억에 남는다"""
    photos = [
        m for m in graph_manager.get_media_for_event(EVENT)
        if m.get("media_type") == "photo"
    ]
    assert photos, "시드 추억에 사진이 없다"
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

        # 문장에 매달렸던 관계도 함께 끊긴다 (근거 · 남긴 사람 · 추억)
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
    """추억을 함께 받는다 — 다른 추억의 기억은 여기서 지워지지 않는다"""
    memory = memories.add_contribution(EVENT, OTHER, "이 기억은 E01의 것입니다.")
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    try:
        others = [e["id"] for e in graph_manager.get_events() if e["id"] != EVENT]
        assert others, "다른 추억이 없다"

        assert memories.delete_memory(others[0], memory["id"]) is None, "다른 추억에서 지워졌다"
        assert graph_manager.get_node(memory["id"]), "지워지면 안 되는 기억이 지워졌다"
        print("  추억 확인 OK")
    finally:
        _cleanup()


def test_event_deletion_takes_its_media_with_it():
    """추억을 지우면 그 추억의 사진·목소리와 원본 파일까지 사라진다

    예전에는 원본을 남기고 "지우는 자리는 사진첩입니다"라고 안내했다. 추억을
    지운 사람에게 사진첩에 그대로 있는 그 장면은 지운 것이 아니다 — 지우려면
    사진첩에서 같은 일을 한 번 더 해야 했다.
    """
    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (원본까지 삭제)",
        description="지울 추억에 남긴 내 기억입니다.",
        person_ids=[AUTHOR, OTHER],
    )
    _created.append(event["id"])

    mine = memories.author_memory(event["id"])
    assert mine, "최초 작성자의 기억이 없다"
    _created.append(mine["id"])

    # 이 추억만의 사진 한 장. 시드 추억에 붙이지 않는다 — 두 추억에 걸린 원본은
    # 남기는 것이 규칙이고, 여기서 보려는 것은 지워지는 쪽이다
    photo = _make_temp_photo(event["id"])
    photo_path = MEDIA_DIR / photo.original_filename

    # 목소리로 남긴 기억. 그 녹음은 추억이 아니라 기억의 근거로 붙는다
    audio = _make_temp_audio(event_id="")
    audio_path = MEDIA_DIR / audio.original_filename
    spoken = memories.add_contribution(
        event["id"], OTHER, "목소리로 남긴 기억입니다.", audio_media_id=audio.id
    )
    assert spoken, "기억을 더하지 못했다"
    _created.append(spoken["id"])

    try:
        result = memories.delete_event(event["id"])
        assert result, "지우지 못했다"

        assert graph_manager.get_node(event["id"]) is None, "추억이 남아 있다"
        assert set(result["deleted_memories"]) == {mine["id"], spoken["id"]}, (
            result["deleted_memories"]
        )
        assert set(result["deleted_media"]) == {photo.id, audio.id}, result["deleted_media"]
        assert result["deleted_counts"] == {"photo": 1, "video": 0, "audio": 1}, (
            result["deleted_counts"]
        )
        assert result["kept_media"] == [], result["kept_media"]

        # 노드도 파일도 남지 않는다. 파일이 남으면 주소를 아는 사람에게는
        # 지워지지 않은 것이다
        for node_id in (photo.id, audio.id, mine["id"], spoken["id"]):
            assert graph_manager.get_node(node_id) is None, f"{node_id}가 남았다"
        assert not photo_path.exists(), "사진 파일이 남았다"
        assert not audio_path.exists(), "녹음 파일이 남았다"

        # 추억도 기억도 원본도 없어졌으니 그것들에 매달렸던 관계도 남지 않는다
        gone = {event["id"], mine["id"], spoken["id"], photo.id, audio.id}
        assert not any(
            gone & {e["source"], e["target"]} for e in graph_manager.get_all_edges()
        ), "지운 추억의 엣지가 남았다"

        # 사람은 남는다 — 이 추억만의 것이 아니다
        assert graph_manager.get_node(AUTHOR), "사람이 함께 지워졌다"
        assert graph_manager.get_node(OTHER), "사람이 함께 지워졌다"
        print("  추억 삭제 OK (기억 · 사진 · 목소리 · 파일까지)")
    finally:
        _cleanup()


def test_media_shared_with_another_event_survives():
    """다른 추억에도 붙어 있는 원본은 남긴다

    사진 한 장은 추억 둘에 붙을 수 있다 (attach_media는 예전 연결을 끊지 않는다).
    그것까지 지우면 남은 추억의 사진첩에 구멍이 난다 — 사용자가 고른 것은 이
    추억을 지우는 일이었다.
    """
    photos = [
        m for m in graph_manager.get_media_for_event(EVENT)
        if m.get("media_type") == "photo"
    ]
    assert photos, "시드 추억에 사진이 없다"
    shared = photos[0]

    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (사진 공유)",
        description="시드 추억과 사진을 함께 쓰는 추억입니다.",
        person_ids=[AUTHOR],
        media_ids=[shared["id"]],
    )
    _created.append(event["id"])

    mine = memories.author_memory(event["id"])
    assert mine, "최초 작성자의 기억이 없다"
    _created.append(mine["id"])

    # 이 추억만의 사진도 한 장 둔다. 하나는 남고 하나는 지워지는지 함께 본다
    only_here = _make_temp_photo(event["id"])
    only_here_path = MEDIA_DIR / only_here.original_filename

    try:
        result = memories.delete_event(event["id"])
        assert result, "지우지 못했다"

        assert result["deleted_media"] == [only_here.id], result["deleted_media"]
        assert not only_here_path.exists(), "이 추억만의 사진 파일이 남았다"

        kept_ids = [kept["id"] for kept in result["kept_media"]]
        assert kept_ids == [shared["id"]], result["kept_media"]
        assert "다른 추억" in result["kept_media"][0]["reason"], result["kept_media"][0]

        assert graph_manager.get_node(shared["id"]), "다른 추억이 쓰는 사진이 지워졌다"
        assert any(
            m["id"] == shared["id"] for m in graph_manager.get_media_for_event(EVENT)
        ), "다른 추억의 사진 연결이 끊겼다"
        assert memories.memories_of(EVENT), "다른 추억의 기억이 함께 지워졌다"
        print("  공유된 사진은 남는다 OK")
    finally:
        _cleanup()


def test_delete_event_only_touches_events():
    """추억이 아닌 id로는 아무것도 지워지지 않는다"""
    assert memories.delete_event(AUTHOR) is None, "사람이 지워졌다"
    assert graph_manager.get_node(AUTHOR), "지워지면 안 되는 인물이 지워졌다"
    assert memories.delete_event("없는-추억") is None, "없는 추억을 지웠다고 한다"
    print("  추억만 지운다 OK")


def test_place_goes_when_the_last_event_that_used_it_goes():
    """추억을 지우면 그 추억만 쓰던 장소도 함께 거둔다

    장소는 사진의 EXIF 좌표에서 파생된 노드다 (event_resolver.resolve_place).
    스스로 열리는 화면이 없어서 — 지도는 추억을 그리고 사진첩은 원본을 그린다 —
    추억이 없어진 장소는 어느 화면에서도 닿을 수 없고, 연결된 기억 화면에
    아무것도 걸리지 않은 점으로만 남는다. 배포된 그래프에 "강원 홍천"과
    "경기 수원"이 그렇게 떠 있었다.

    다른 추억이 아직 쓰고 있는 장소는 그대로 둔다 — 장소는 한 추억만의 것이
    아니다. 그래서 같은 장소를 두 추억이 쓰는 자리에서 확인한다.
    """
    # 홍천 좌표. 시드된 장소 여덟 곳에서 모두 5km 넘게 떨어져 있어 새 장소가 된다
    place_id = event_resolver.resolve_place(37.697, 127.889)
    assert place_id, "장소를 만들지 못했다"
    _created.append(place_id)

    first = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (장소 하나를 둘이 쓴다 · 첫째)",
        place_id=place_id,
    )
    _created.append(first["id"])
    second = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (장소 하나를 둘이 쓴다 · 둘째)",
        place_id=place_id,
    )
    _created.append(second["id"])

    try:
        # 아직 둘째가 쓰고 있다
        result = memories.delete_event(first["id"])
        assert result, "첫째를 지우지 못했다"
        assert result["deleted_places"] == [], result["deleted_places"]
        assert graph_manager.get_node(place_id), "아직 쓰이는 장소가 지워졌다"

        # 마지막 추억이 없어지면 장소도 따라간다
        result = memories.delete_event(second["id"])
        assert result, "둘째를 지우지 못했다"
        assert result["deleted_places"] == [place_id], result["deleted_places"]
        assert graph_manager.get_node(place_id) is None, "빈 장소가 남았다"

        # 시드된 장소는 하나도 건드리지 않는다
        seeded = [p for p in graph_manager.get_places() if p["id"].startswith("place_E")]
        assert len(seeded) == 8, f"시드 장소가 {len(seeded)}개로 바뀌었다"
        print("  빈 장소 거두기 OK (쓰이는 장소는 남는다)")
    finally:
        _cleanup()


def test_voice_goes_with_the_memory_it_belongs_to():
    """목소리로 남긴 기억을 지우면 그 녹음도 사라진다

    문장만 지우고 녹음을 남기면 지운 것이 아니다 — 전사문이 녹음에 함께 있고,
    추억 상세의 "가족이 남긴 목소리"에서 계속 재생된다.
    """
    audio = _make_temp_audio()
    path = MEDIA_DIR / audio.original_filename

    memory = memories.add_contribution(
        EVENT, OTHER, "목소리로 남긴 기억입니다.", audio_media_id=audio.id
    )
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    try:
        # 지우기 전에는 추억에 붙어 있다
        assert any(
            m["id"] == audio.id for m in memories.detail(EVENT, OTHER)["media"]
        ), "녹음이 추억에 붙지 않았다"

        result = memories.delete_memory(EVENT, memory["id"])
        assert result, "지우지 못했다"
        assert result["deleted_voices"] == [audio.id], result["deleted_voices"]

        assert graph_manager.get_node(audio.id) is None, "녹음 노드가 남았다"
        assert not path.exists(), "녹음 파일이 남았다"
        assert all(
            m["id"] != audio.id for m in memories.detail(EVENT, OTHER)["media"]
        ), "추억 상세에 녹음이 남아 있다"
        print("  목소리 함께 삭제 OK")
    finally:
        _cleanup()


def test_voice_stays_when_another_memory_still_leans_on_it():
    """다른 기억이 아직 근거로 쓰는 녹음은 남긴다

    인터뷰 녹음 하나에 여러 문장이 매달릴 수 있다. 그때 지우면 남의 기억에서
    근거가 사라진다.
    """
    audio = _make_temp_audio()
    path = MEDIA_DIR / audio.original_filename

    first = memories.add_contribution(
        EVENT, OTHER, "같은 녹음을 근거로 삼은 첫 문장입니다.", audio_media_id=audio.id
    )
    second = memories.add_contribution(
        EVENT, AUTHOR, "같은 녹음을 근거로 삼은 둘째 문장입니다.", audio_media_id=audio.id
    )
    assert first and second, "기억을 더하지 못했다"
    _created.extend([first["id"], second["id"]])

    try:
        kept = memories.delete_memory(EVENT, first["id"])
        assert kept and kept["deleted_voices"] == [], kept
        assert graph_manager.get_node(audio.id), "아직 쓰는 녹음이 지워졌다"
        assert path.exists(), "아직 쓰는 녹음 파일이 지워졌다"

        # 마지막으로 그 녹음에 매달린 문장을 지우면 함께 사라진다
        last = memories.delete_memory(EVENT, second["id"])
        assert last and last["deleted_voices"] == [audio.id], last
        assert graph_manager.get_node(audio.id) is None, "녹음이 남았다"
        assert not path.exists(), "녹음 파일이 남았다"
        print("  근거가 남은 녹음 보존 OK")
    finally:
        _cleanup()


def test_photos_are_not_erased_with_the_memory():
    """사진은 기억과 함께 지워지지 않는다 (원본을 지우는 자리는 사진첩이다)"""
    photos = [
        m for m in graph_manager.get_media_for_event(EVENT)
        if m.get("media_type") == "photo"
    ]
    assert photos, "시드 추억에 사진이 없다"
    photo = photos[0]

    memory = memories.add_contribution(
        EVENT, OTHER, "사진과 함께 남긴 기억입니다.", media_ids=[photo["id"]]
    )
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    try:
        result = memories.delete_memory(EVENT, memory["id"])
        assert result and result["deleted_voices"] == [], result
        assert result["kept_media"] == [photo["id"]], result["kept_media"]
        assert graph_manager.get_node(photo["id"]), "사진이 함께 지워졌다"
        print("  사진 보존 OK")
    finally:
        _cleanup()


def test_info_can_be_fixed_without_losing_what_the_family_left():
    """제목·날짜·장소·함께한 사람은 뒤늦게 고칠 수 있다 — 남긴 것은 그대로

    만들 때 AI 초안을 고쳐 저장했더라도 어긋난 것이 뒤늦게 나온다: EXIF에 촬영
    날짜가 없어 올린 날이 들어갔거나, 좌표에서 짐작한 지명이 옆 동네였거나, 얼굴
    인식이 놓친 사람이 "함께한 사람"에 없다. 그때 지우고 다시 만들게 하면 가족이
    그 추억에 남긴 기억과 "나도 기억나요"가 함께 사라진다.

    기억 문장은 이 경로로 바뀌지 않는다 — 제목·날짜·장소는 가족이 함께 보는
    기록이고 기억 문장은 그 말을 한 사람의 것이다.

    제목을 비워 보내면 지금 제목을 그대로 둔다. 목록·지도·이야기가 모두 제목으로
    이 추억을 부르므로 이름 없는 추억을 만들 수 없다 (화면에는 라우터가 400으로
    이유를 밝힌다).
    """
    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (정보 고치기 전)",
        description="처음 남긴 기억입니다.",
        date_start="2020-01-01",
        place_name="테스트 장소 (고치기 전)",
        person_ids=[AUTHOR],
    )
    _created.append(event["id"])
    _created.append(event["location_id"])

    added = memories.add_contribution(event["id"], OTHER, "저도 여기 있었습니다.")
    assert added, "기억을 더하지 못했다"
    _created.append(added["id"])
    memories.toggle_echo(event["id"], OTHER)

    try:
        result = memories.update_memory(
            event["id"],
            title="테스트 추억 (고친 뒤)",
            date_start="2019-05-05",
            place_name="테스트 장소 (고친 뒤)",
            # 기억을 남긴 OTHER는 이미 참여자다 (add_contribution). 얼굴 인식이
            # 놓친 사람을 뒤늦게 더하는 자리를 보려면 아무 말도 남기지 않은
            # 사람이 필요하다
            person_ids=[AUTHOR, OTHER, THIRD],
        )
        assert result, "정보를 고치지 못했다"
        _created.append(result["place"]["id"])
        assert set(result["changed"]) == {"title", "date_start", "place", "participants"}, (
            result["changed"]
        )
        assert [p["id"] for p in result["added_participants"]] == [THIRD], (
            result["added_participants"]
        )
        assert result["removed_participants"] == [], result["removed_participants"]
        assert result["still_tagged"] == [], result["still_tagged"]

        detail = memories.detail(event["id"], AUTHOR)
        assert detail["title"] == "테스트 추억 (고친 뒤)", detail["title"]
        assert detail["date_start"] == "2019-05-05", detail["date_start"]
        assert detail["place"]["name"] == "테스트 장소 (고친 뒤)", detail["place"]
        assert sorted(p["id"] for p in detail["participants"]) == sorted(
            [AUTHOR, OTHER, THIRD]
        ), detail["participants"]

        # 가족이 남긴 것은 하나도 움직이지 않았다
        assert detail["author_memory"]["content"] == "처음 남긴 기억입니다.", (
            detail["author_memory"]
        )
        assert [m["content"] for m in detail["contributions"]] == ["저도 여기 있었습니다."], (
            detail["contributions"]
        )
        assert detail["echo_count"] == 1, detail["echo_count"]

        # 제목은 비울 수 없다 — 비워 보내면 지금 제목이 남는다
        result = memories.update_memory(
            event["id"], title="   ", date_start="2019-05-05",
            place_name="테스트 장소 (고친 뒤)", person_ids=[AUTHOR, OTHER, THIRD],
        )
        assert result and result["changed"] == [], result["changed"]
        assert memories.detail(event["id"], AUTHOR)["title"] == "테스트 추억 (고친 뒤)"
        print("  정보 고치기 OK (기억·기억나요는 그대로)")
    finally:
        _cleanup()


def test_place_left_behind_by_an_edit_is_collected():
    """장소를 고쳐 옮기면 아무것도 걸리지 않게 된 예전 장소를 함께 거둔다

    추억을 지울 때와 같은 처리다 (delete_event). 장소는 파생 노드여서 스스로
    열리는 화면이 없고, 아무 추억도 가리키지 않으면 지도에 지울 수 없는 점으로만
    남는다. 다른 추억이 아직 쓰는 장소는 그대로 둔다 — 장소는 한 추억만의 것이
    아니다.
    """
    # 홍천 좌표. 시드된 장소 여덟 곳에서 모두 5km 넘게 떨어져 있어 새 장소가 된다
    place_id = event_resolver.resolve_place(37.697, 127.889)
    assert place_id, "장소를 만들지 못했다"
    _created.append(place_id)

    first = memories.create_memory(
        author_id=AUTHOR, title="테스트 추억 (장소를 옮긴다 · 첫째)", place_id=place_id
    )
    _created.append(first["id"])
    second = memories.create_memory(
        author_id=AUTHOR, title="테스트 추억 (장소를 옮긴다 · 둘째)", place_id=place_id
    )
    _created.append(second["id"])

    try:
        # 첫째가 떠나도 둘째가 아직 쓰고 있다
        result = memories.update_memory(
            first["id"], title=first["title"], place_name="테스트 장소 (옮긴 뒤)"
        )
        assert result, "첫째의 장소를 옮기지 못했다"
        _created.append(result["place"]["id"])
        assert result["deleted_places"] == [], result["deleted_places"]
        assert graph_manager.get_node(place_id), "아직 쓰이는 장소가 지워졌다"

        # 마지막 추억이 떠나면 장소도 따라간다 (장소를 비운 경우다)
        result = memories.update_memory(second["id"], title=second["title"])
        assert result and result["place"] is None, result["place"]
        assert result["deleted_places"] == [place_id], result["deleted_places"]
        assert graph_manager.get_node(place_id) is None, "빈 장소가 남았다"
        assert memories.detail(second["id"], AUTHOR)["place"] is None
        print("  옮긴 뒤 빈 장소 거두기 OK (쓰이는 장소는 남는다)")
    finally:
        _cleanup()


def test_a_removed_participant_who_is_still_in_a_photo_is_named():
    """사진에 지목된 사람을 함께한 사람에서 빼면, 되돌아온다고 밝힌다

    사진 지목이 참여자를 다시 세는 근거다
    (event_resolver.sync_participants_of_event). 정보 칸에서 뗀 것만으로는 다음
    정리에서 그 사람이 돌아온다 — 참여자 규칙을 한 벌 더 만들어 조용히 막지 않고,
    어디서 떼야 하는지 알려 주는 쪽을 골랐다.

    사람이 직접 넣은 참여자는 그 정리가 건드리지 않는다 (via가 없다). 둘을 한
    자리에서 확인한다.
    """
    event = memories.create_memory(
        author_id=AUTHOR,
        title="테스트 추억 (사진에 지목된 사람)",
        person_ids=[AUTHOR],
    )
    _created.append(event["id"])
    photo = _make_temp_photo(event["id"])
    event_resolver.set_media_persons(photo.id, [OTHER])

    try:
        before = sorted(p["id"] for p in memories.detail(event["id"], AUTHOR)["participants"])
        assert before == sorted([AUTHOR, OTHER]), before

        result = memories.update_memory(event["id"], title=event["title"], person_ids=[AUTHOR])
        assert result, "참여자를 고치지 못했다"
        assert [p["id"] for p in result["removed_participants"]] == [OTHER], (
            result["removed_participants"]
        )
        assert [p["id"] for p in result["still_tagged"]] == [OTHER], result["still_tagged"]
        after = [p["id"] for p in memories.detail(event["id"], AUTHOR)["participants"]]
        assert after == [AUTHOR], after

        # 밝힌 그대로다 — 사진에서 떼지 않으면 다음 정리에서 돌아온다
        event_resolver.sync_participants_of_event(event["id"])
        again = sorted(p["id"] for p in memories.detail(event["id"], AUTHOR)["participants"])
        assert again == sorted([AUTHOR, OTHER]), again
        print("  사진에 남은 지목 밝히기 OK (직접 넣은 참여자는 그대로)")
    finally:
        _cleanup()


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
    test_event_deletion_takes_its_media_with_it,
    test_media_shared_with_another_event_survives,
    test_delete_event_only_touches_events,
    test_place_goes_when_the_last_event_that_used_it_goes,
    test_voice_goes_with_the_memory_it_belongs_to,
    test_voice_stays_when_another_memory_still_leans_on_it,
    test_photos_are_not_erased_with_the_memory,
    test_info_can_be_fixed_without_losing_what_the_family_left,
    test_place_left_behind_by_an_edit_is_collected,
    test_a_removed_participant_who_is_still_in_a_photo_is_named,
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
