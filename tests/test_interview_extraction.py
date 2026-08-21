"""인터뷰 답변 → 그래프 반영 회귀 테스트

    python tests/test_interview_extraction.py

기획안 STEP 06 "이어가기"가 닫히는 자리다. 답변이 문장으로만 쌓이면 그래프는
자라지 않고, 반대로 AI가 마음대로 쓰면 가족사가 오염된다. 그 사이의 선을 지킨다.

  - 그래프에 있는 인물·장소에만 잇는다 (없는 사람을 만들지 않는다)
  - 비어 있는 자리만 채운다 (있는 값을 덮어쓰지 않는다)
  - 이렇게 넣은 것은 ai_inferred로 남는다 (사람이 적은 것과 구분된다)

LLM 호출은 하지 않는다. 추출(LLM)과 잇기(규칙)를 나눠 두었으므로 잇기만 시험한다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import (  # noqa: E402
    Confidence,
    MemoryNode,
    MemoryState,
    RelationType,
    SourceType,
)
from backend.services import interview_engine, memories  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행
SPEAKER = "P01"  # 김민수 (말하는 사람)
GUEST = "P05"  # 이정자 (할머니 — E01에는 참여자로 없다)


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _snapshot(event_id=EVENT):
    event = graph_manager.get_node(event_id)
    return {
        key: event.get(key)
        for key in ("title", "date_start", "description", "location_id", "confidence", "source")
    }


def _restore(snapshot, event_id=EVENT, added_edges=(), memory_id=None):
    graph_manager.update_node(event_id, snapshot)
    for source, target in added_edges:
        graph_manager.remove_edge(source, target)
    if memory_id:
        graph_manager.delete_node(memory_id)


def _make_memory():
    """근거로 쓸 기억 하나 (실제 경로와 같게 만든다)"""
    memory = MemoryNode(
        content="테스트용 답변",
        source_type=SourceType.INTERVIEW,
        contributor_id=SPEAKER,
        confidence=Confidence.CONFIRMED,
    )
    graph_manager.add_memory(memory)
    return memory.id


def _edges_between(source, target):
    return [
        e
        for e in graph_manager.get_all_edges()
        if e["source"] == source and e["target"] == target
    ]


def test_known_person_is_linked_as_inferred_participant():
    """답변에 나온 사람이 그래프에 있으면 참여자로 잇는다 (추정으로)"""
    _require_seeded_graph()
    before = _snapshot()
    memory_id = _make_memory()
    try:
        guest = graph_manager.get_node(GUEST)
        result = interview_engine.link_extracted(
            {"persons": [guest["name"]], "places": [], "date": None},
            graph_manager.get_node(EVENT),
            SPEAKER,
            memory_id,
        )

        assert [p["id"] for p in result["persons"]] == [GUEST], result["persons"]
        edges = _edges_between(GUEST, EVENT)
        assert edges, "참여 엣지가 생기지 않았다"

        props = edges[0]["properties"]
        assert props["confidence"] == Confidence.AI_INFERRED, props
        assert props["source"] == SourceType.INTERVIEW, props
        # 어느 답변에서 나왔는지 되짚을 수 있어야 한다
        assert props["from_memory"] == memory_id, props
        print("  인물 연결 OK:", guest["name"], "→", EVENT, props["confidence"])
    finally:
        _restore(before, added_edges=[(GUEST, EVENT)], memory_id=memory_id)


def test_unknown_person_is_reported_not_created():
    """그래프에 없는 호칭은 만들지 않고 남겨서 알린다

    "큰엄마"가 누구인지는 가족만 안다. AI가 정하면 잘못된 귀속이 박힌다.
    """
    _require_seeded_graph()
    before = _snapshot()
    memory_id = _make_memory()
    person_count = len(graph_manager.get_persons())
    try:
        result = interview_engine.link_extracted(
            {"persons": ["큰엄마", "옆집 아저씨"], "places": [], "date": None},
            graph_manager.get_node(EVENT),
            SPEAKER,
            memory_id,
        )

        assert result["persons"] == [], result["persons"]
        assert set(result["unmatched"]) == {"큰엄마", "옆집 아저씨"}, result["unmatched"]
        assert len(graph_manager.get_persons()) == person_count, "없는 사람을 만들었다"
        print("  없는 인물 처리 OK:", result["unmatched"])
    finally:
        _restore(before, memory_id=memory_id)


def test_speaker_is_not_relinked():
    """말한 사람은 이미 REMEMBERS로 이어져 있어 참여자로 다시 잇지 않는다"""
    _require_seeded_graph()
    before = _snapshot()
    memory_id = _make_memory()
    existing = len(_edges_between(SPEAKER, EVENT))
    try:
        speaker = graph_manager.get_node(SPEAKER)
        result = interview_engine.link_extracted(
            {"persons": [speaker["name"]], "places": [], "date": None},
            graph_manager.get_node(EVENT),
            SPEAKER,
            memory_id,
        )
        # 알아낸 것으로는 보고하되, 엣지를 새로 만들지는 않는다
        assert [p["id"] for p in result["persons"]] == [SPEAKER]
        assert result["updated_nodes"] == [], result["updated_nodes"]
        assert len(_edges_between(SPEAKER, EVENT)) == existing
        print("  화자 중복 연결 없음 OK")
    finally:
        _restore(before, memory_id=memory_id)


def test_empty_fields_are_filled_and_marked_inferred():
    """비어 있는 날짜·장소는 채우고, 채운 추억은 추정으로 표시한다"""
    _require_seeded_graph()
    before = _snapshot()
    memory_id = _make_memory()
    place = next(p for p in graph_manager.get_places() if p["id"] != before["location_id"])
    try:
        # 날짜와 장소를 비워 둔 추억을 만든다 (업로드만 하고 아무도 안 채운 상태)
        graph_manager.update_node(EVENT, {"date_start": None, "location_id": None})
        graph_manager.remove_edge(EVENT, before["location_id"])

        result = interview_engine.link_extracted(
            {"persons": [], "places": [place["name"]], "date": "1998-08"},
            graph_manager.get_node(EVENT),
            SPEAKER,
            memory_id,
        )

        event = graph_manager.get_node(EVENT)
        assert event["date_start"] == "1998-08-01", event["date_start"]
        assert event["location_id"] == place["id"], event["location_id"]
        assert set(result["filled"]) == {"date_start", "location_id"}, result["filled"]

        # 추정으로 표시된다. 사람이 적은 값과 섞이면 어디까지가 사실인지 읽을 수 없다.
        assert event["confidence"] == Confidence.AI_INFERRED, event["confidence"]

        # 확인 상태(맞음/모름/이견)는 없어졌다. 남은 축은 "기억이 얼마나 쌓였나"이고,
        # 방금 기억 하나를 남겼으므로 최소한 혼자는 아니어야 한다.
        state = memories.state_of(EVENT)
        assert state and state["state"] in (
            MemoryState.ALONE.value,
            MemoryState.SHARED.value,
            MemoryState.VARIED.value,
        ), state

        edges = _edges_between(EVENT, place["id"])
        assert edges and edges[0]["relation"] == RelationType.LOCATED_AT, edges
        print("  빈 자리 채우기 OK:", result["filled"])
    finally:
        graph_manager.remove_edge(EVENT, place["id"])
        _restore(before, memory_id=memory_id)
        # 원래 장소 엣지를 되돌린다
        from backend.models.graph_models import Edge

        graph_manager.add_edge(Edge(
            source=EVENT, target=before["location_id"], relation=RelationType.LOCATED_AT
        ))


def test_existing_values_are_never_overwritten():
    """이미 값이 있으면 답변이 달라도 덮어쓰지 않는다

    사람이 넣은 값을 AI 추출이 갈아치우면, 확인해 둔 사실이 조용히 뒤집힌다.
    """
    _require_seeded_graph()
    before = _snapshot()
    memory_id = _make_memory()
    other_place = next(p for p in graph_manager.get_places() if p["id"] != before["location_id"])
    try:
        result = interview_engine.link_extracted(
            {"persons": [], "places": [other_place["name"]], "date": "2001-05-05"},
            graph_manager.get_node(EVENT),
            SPEAKER,
            memory_id,
        )

        event = graph_manager.get_node(EVENT)
        assert event["date_start"] == before["date_start"], "날짜를 덮어썼다"
        assert event["location_id"] == before["location_id"], "장소를 덮어썼다"
        assert result["filled"] == [], result["filled"]
        # 알아낸 것 자체는 보고한다 (화면이 "이렇게 들었다"고 보여줄 수 있게)
        assert result["date"] == "2001-05-05", result["date"]
        assert result["place"]["id"] == other_place["id"], result["place"]
        print("  기존 값 보존 OK")
    finally:
        _restore(before, memory_id=memory_id)


def test_date_shapes_are_validated():
    """날짜는 ISO 모양만 통과시킨다 (타임라인이 엉키지 않게)"""
    assert interview_engine._normalize_date("1998") == "1998-01-01"
    assert interview_engine._normalize_date("1998-08") == "1998-08-01"
    assert interview_engine._normalize_date("1998-08-13") == "1998-08-13"
    for junk in ("그때", "여름", "98년", "1998년 8월", None, 1998, ""):
        assert interview_engine._normalize_date(junk) is None, junk
    print("  날짜 형식 검사 OK")


def test_relation_terms_resolve_to_people():
    """가족이 실제로 쓰는 호칭으로도 사람을 찾는다 ("엄마")"""
    _require_seeded_graph()
    mother = next(p for p in graph_manager.get_persons() if p.get("relation") == "엄마")
    assert interview_engine._resolve_person("엄마") == mother["id"]
    assert interview_engine._resolve_person(mother["name"]) == mother["id"]
    assert interview_engine._resolve_person("사돈어른") is None
    print("  호칭 해석 OK: 엄마 →", mother["name"])


def test_no_event_target_still_records_extraction():
    """추억이 정해지지 않은 인터뷰에서도 알아낸 것은 보고한다 (엣지는 만들지 않는다)"""
    _require_seeded_graph()
    memory_id = _make_memory()
    try:
        guest = graph_manager.get_node(GUEST)
        result = interview_engine.link_extracted(
            {"persons": [guest["name"]], "places": [], "date": "1998"},
            None,
            SPEAKER,
            memory_id,
        )
        assert [p["id"] for p in result["persons"]] == [GUEST]
        assert result["date"] == "1998-01-01"
        assert result["updated_nodes"] == [], result["updated_nodes"]
        assert result["filled"] == []
        print("  추억 없는 인터뷰 OK")
    finally:
        graph_manager.delete_node(memory_id)


TESTS = [
    test_known_person_is_linked_as_inferred_participant,
    test_unknown_person_is_reported_not_created,
    test_speaker_is_not_relinked,
    test_empty_fields_are_filled_and_marked_inferred,
    test_existing_values_are_never_overwritten,
    test_date_shapes_are_validated,
    test_relation_terms_resolve_to_people,
    test_no_event_target_still_records_extraction,
]


if __name__ == "__main__":
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {test.__name__}: {type(e).__name__} {e}")

    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} 통과")
    sys.exit(1 if failures else 0)
