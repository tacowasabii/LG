"""사진·영상에 있는 사람 지목 회귀 테스트

    python tests/test_media_person_tags.py

얼굴 인식이 없으므로 이 경로가 detected_faces의 유일한 출처다. 그래서 여기가
틀리면 새로 올린 사진은 인물과 영원히 끊기거나, 반대로 뗀 사람이 계속 붙어 있다.

되돌리기가 특히 중요하다. remove_edge는 두 노드 사이의 관계를 모두 지우므로
(JSON·Postgres 양쪽 다), 태그를 떼는 일이 목소리의 주인(NARRATED_BY)까지
지워 버릴 수 있다.

  - 지목하면 detected_faces와 DEPICTS 엣지가 함께 남는가
  - 떼면 둘 다 함께 사라지는가
  - 뗄 때 같은 사람과의 다른 관계(NARRATED_BY)가 살아남는가
  - 없는 id·인물이 아닌 id·중복을 걸러내는가
  - 지목된 사람으로 인물별 조회가 되는가
  - 지목된 사람이 비공개를 요청하면 그 기록이 다른 가족에게 가려지는가
  - 나중에 지목한 사람이 그 추억의 "함께한 사람"과 이야기에 들어가는가
  - 뗄 때 사람이 직접 적어 넣은 참여자는 그대로 남는가
  - 사람이 늘면 이미 쓰인 "함께 기억한 이야기"가 낡은 것으로 표시되는가

그래프를 실제로 바꾸므로 끝에서 원래대로 되돌린다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import Edge, RelationType  # noqa: E402
from backend.routers.media import list_media  # noqa: E402
from backend.services import event_resolver, film_composer, memories, visibility  # noqa: E402
from backend.services.event_resolver import set_media_persons  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

MEDIA = "E01_002"  # 1998 부산 여행 사진
EVENT = "E01"
P_A = "P01"  # 김민수
P_B = "P03"  # 김하늘
P_C = "P02"
P_GRANDMA = "P05"  # 이정자 (할머니). E01의 참여자가 아니다 — 나중에 지목하는 사람


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _snapshot():
    """이 테스트가 건드리는 것만 떠 둔다 — detected_faces와 미디어→인물 엣지"""
    node = graph_manager.get_node(MEDIA)
    return {
        "detected_faces": list(node.get("detected_faces") or []),
        "speaker_id": node.get("speaker_id"),
        "edges": [
            dict(e)
            for e in graph_manager.get_all_edges()
            if e["source"] == MEDIA
            and (graph_manager.get_node(e["target"]) or {}).get("node_type") == "person"
        ],
    }


def _restore(before):
    for person_id in set(
        (graph_manager.get_node(MEDIA).get("detected_faces") or [])
        + [e["target"] for e in before["edges"]]
        + [P_A, P_B, P_C]
    ):
        graph_manager.remove_edge(MEDIA, person_id)

    for edge in before["edges"]:
        graph_manager.add_edge(Edge(
            source=edge["source"],
            target=edge["target"],
            relation=edge["relation"],
            properties=edge.get("properties") or {},
        ))

    graph_manager.update_node(MEDIA, {
        "detected_faces": before["detected_faces"],
        "speaker_id": before["speaker_id"],
    })

    # 지목은 추억의 "함께한 사람"까지 바꾼다. 태그만 되돌리면 사진에 없는
    # 사람이 추억에 남아 다음 테스트의 이야기에 섞인다.
    event_resolver.sync_participants_of_event(EVENT)


def _depicted():
    return {
        e["target"]
        for e in graph_manager.get_all_edges()
        if e["source"] == MEDIA and e["relation"] == RelationType.DEPICTS
    }


def _relations_to(person_id):
    return {
        e["relation"]
        for e in graph_manager.get_all_edges()
        if e["source"] == MEDIA and e["target"] == person_id
    }


def _faces_without_grandma():
    """할머니를 뗀 상태로 맞추고 그때의 지목 목록을 돌려준다

    데모 그래프 하나를 여러 테스트·세션이 함께 쓴다. 앞선 것이 남긴 지목이
    있으면 "지목하면 늘어난다"를 셀 기준이 사라진다 — 세는 대신 시작 상태를
    정해 둔다. 원래대로 되돌리는 것은 _restore가 한다.
    """
    faces = [
        pid
        for pid in (graph_manager.get_node(MEDIA).get("detected_faces") or [])
        if pid != P_GRANDMA
    ]
    set_media_persons(MEDIA, faces)
    return faces


def _event_participants():
    return {
        e["source"]
        for e in graph_manager.get_all_edges()
        if e["target"] == EVENT and e["relation"] == RelationType.PARTICIPATED_IN
    }


def test_tagging_writes_both_faces_and_edges():
    """지목하면 detected_faces와 DEPICTS 엣지가 함께 남는다

    공개 범위 판정이 둘을 모두 읽으므로 한쪽만 쓰면 다른 경로에서 새어 나온다.
    """
    _require_seeded_graph()
    before = _snapshot()
    try:
        result = set_media_persons(MEDIA, [P_A, P_B])

        assert result == [P_A, P_B], result
        assert graph_manager.get_node(MEDIA)["detected_faces"] == [P_A, P_B]
        assert {P_A, P_B} <= _depicted(), _depicted()
        print("  지목 → detected_faces + DEPICTS OK")
    finally:
        _restore(before)


def test_untagging_removes_both():
    """뗀 사람은 detected_faces와 엣지에서 함께 사라진다"""
    _require_seeded_graph()
    before = _snapshot()
    try:
        set_media_persons(MEDIA, [P_A, P_B])
        result = set_media_persons(MEDIA, [P_A])

        assert result == [P_A], result
        assert graph_manager.get_node(MEDIA)["detected_faces"] == [P_A]
        assert P_B not in _depicted(), _depicted()
        print("  떼기 → 양쪽에서 사라짐 OK")
    finally:
        _restore(before)


def test_untagging_keeps_other_relations_to_same_person():
    """태그를 떼도 같은 사람과의 다른 관계는 살아남는다

    remove_edge는 두 노드 사이의 관계를 모두 지운다. 영상에 찍힌 사람이
    동시에 말하는 사람이면, 태그를 떼는 순간 목소리의 주인까지 사라진다.
    """
    _require_seeded_graph()
    before = _snapshot()
    try:
        graph_manager.add_edge(Edge(
            source=MEDIA, target=P_B, relation=RelationType.NARRATED_BY,
        ))
        set_media_persons(MEDIA, [P_B])
        set_media_persons(MEDIA, [])

        remaining = _relations_to(P_B)
        assert RelationType.DEPICTS not in remaining, remaining
        assert RelationType.NARRATED_BY in remaining, remaining
        print("  떼기가 NARRATED_BY를 지우지 않음 OK")
    finally:
        _restore(before)


def test_rejects_unknown_and_non_person_ids():
    """없는 id, 인물이 아닌 id, 중복은 조용히 버린다"""
    _require_seeded_graph()
    before = _snapshot()
    try:
        result = set_media_persons(MEDIA, ["없는사람", EVENT, P_A, P_A, "  "])

        assert result == [P_A], result
        assert EVENT not in _depicted(), _depicted()
        print("  잘못된 id 걸러내기 OK")
    finally:
        _restore(before)


def test_tagged_person_is_findable_by_person_filter():
    """지목한 사람으로 인물별 조회가 된다 (기능이 실제로 이어졌는지)"""
    _require_seeded_graph()
    before = _snapshot()
    try:
        set_media_persons(MEDIA, [P_C])
        # 인자를 다 채운다. 라우터 함수를 직접 부르면 안 넘긴 Query 기본값이
        # None이 아니라 Query 객체로 남아 필터가 아무것도 통과시키지 않는다.
        found = asyncio.run(list_media(media_type=None, person_id=P_C, viewer_id=None))

        assert any(m.id == MEDIA for m in found), [m.id for m in found]
        print("  인물별 조회 도달 OK")
    finally:
        _restore(before)


def test_tagged_person_private_request_hides_media():
    """지목된 사람이 비공개를 요청하면 그 기록이 다른 가족에게 가려진다

    태그가 공개 범위 판정까지 실제로 닿는지 본다. 여기가 끊기면 비공개 설정이
    형식이 된다 (기획안 08장).
    """
    _require_seeded_graph()
    before = _snapshot()
    person_before = graph_manager.get_node(P_B).get("private_request")
    try:
        set_media_persons(MEDIA, [P_B])
        graph_manager.update_node(P_B, {"private_request": True})

        node = graph_manager.get_node(MEDIA)
        assert not visibility.can_view(node, P_A), "다른 가족에게 보인다"
        assert visibility.can_view(node, P_B), "본인에게 가려졌다"
        print("  비공개 요청이 태그를 통해 적용됨 OK")
    finally:
        graph_manager.update_node(P_B, {"private_request": person_before})
        _restore(before)


def test_tagging_after_attach_reaches_the_event_and_its_story():
    """나중에 지목한 사람이 그 추억의 "함께한 사람"과 이야기에 들어간다

    얼굴 인식이 할머니를 놓친 사진을 사람이 직접 지목하는 경우다. 사진에 붙는
    순간에만 추억으로 옮기면(예전 memories.attach_media), 지목은 사진첩에서만
    보이고 추억 상세의 "함께한 사람"과 Film·TV 이야기에는 할머니가 없다 —
    이야기는 추억에 이어진 인물을 읽어 쓴다.
    """
    _require_seeded_graph()
    before = _snapshot()
    try:
        faces = _faces_without_grandma()
        assert P_GRANDMA not in _event_participants(), "지목 말고 다른 이유로 참여자다"

        set_media_persons(MEDIA, faces + [P_GRANDMA])

        assert P_GRANDMA in _event_participants(), _event_participants()

        record = film_composer._record(EVENT)
        assert P_GRANDMA in {p["id"] for p in record["persons"]}, record["persons"]
        # 문장에 실제로 나오는가. 모델 없이 쓰는 경로로 본다 (LLM 폴백)
        plain = film_composer._plain_narration(
            graph_manager.get_node(EVENT), [], record["persons"], None
        )
        assert "할머니" in plain, plain

        detail = memories.detail(EVENT)
        assert P_GRANDMA in {p["id"] for p in detail["participants"]}, detail["participants"]
        print("  나중에 지목한 사람이 추억·이야기에 도달 OK")
    finally:
        _restore(before)


def test_untagging_removes_only_the_participant_the_tag_added():
    """뗄 때 사진에서 온 참여자만 뗀다 (사람이 적어 넣은 참여자는 남는다)

    잘못 지목한 사람이 추억에 영구히 남으면 이야기가 그 사람을 계속 부른다.
    반대로 추억을 만들 때 고른 사람까지 지우면, 사진 태그 하나가 사람이 적어
    넣은 것을 덮는다.
    """
    _require_seeded_graph()
    before = _snapshot()
    try:
        faces = _faces_without_grandma()
        set_media_persons(MEDIA, faces + [P_GRANDMA])
        assert P_GRANDMA in _event_participants()

        set_media_persons(MEDIA, faces)
        assert P_GRANDMA not in _event_participants(), _event_participants()

        # 이번에는 가족이 직접 적어 넣은 참여자다 (via 표시가 없다)
        graph_manager.add_edge(Edge(
            source=P_GRANDMA,
            target=EVENT,
            relation=RelationType.PARTICIPATED_IN,
            properties={"role": "참여자"},
        ))
        set_media_persons(MEDIA, faces + [P_GRANDMA])
        set_media_persons(MEDIA, faces)
        assert P_GRANDMA in _event_participants(), "사람이 적어 넣은 참여자가 사라졌다"
        print("  사진에서 온 참여자만 떼기 OK")
    finally:
        graph_manager.remove_edge(P_GRANDMA, EVENT)
        _restore(before)


def test_new_person_makes_the_written_story_stale():
    """사람이 늘면 이미 쓰인 "함께 기억한 이야기"가 낡은 것으로 표시된다

    그 이야기는 추억 노드에 저장된다. 나중에 지목한 할머니는 이미 쓰인 문장에
    들어갈 수 없으므로, 화면이 "다시 만들기"를 권할 수 있어야 한다.
    """
    _require_seeded_graph()
    before = _snapshot()
    keys = (
        "together_story",
        "together_story_at",
        "together_story_basis",
        "together_story_persons",
    )
    event_before = {k: graph_manager.get_node(EVENT).get(k) for k in keys}
    try:
        faces = _faces_without_grandma()
        graph_manager.update_node(EVENT, {
            "together_story": "가족은 그해 여름을 이렇게 기억합니다.",
            "together_story_at": "2026-01-01T00:00:00",
            "together_story_basis": len(memories.memories_of(EVENT)),
            "together_story_persons": len(memories.detail(EVENT)["participants"]),
        })
        assert memories.detail(EVENT)["together_story_stale"] is False, "쓴 직후인데 낡았다"

        set_media_persons(MEDIA, faces + [P_GRANDMA])

        assert memories.detail(EVENT)["together_story_stale"] is True, "사람이 늘었는데 그대로다"
        print("  사람이 늘면 이야기가 낡은 것으로 표시됨 OK")
    finally:
        graph_manager.update_node(EVENT, event_before)
        _restore(before)


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}\n{e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
