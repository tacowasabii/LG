"""질의 계획 그래프(LangGraph) 회귀 테스트

    python tests/test_chat_graph.py

EXAONE 키가 있으면 실제 계획 노드까지 돌고, 없으면 규칙 기반 폴백 경로만
검증한다 (키 없이도 통과해야 한다 - 폴백이 깨지면 발표 중 화면이 죽는다).

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import chat_graph, graph_search, llm_client  # noqa: E402
from backend.services.chat_engine import _extract_sources  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _run(query):
    return asyncio.run(chat_graph.run(query))


def test_graph_always_returns_usable_state():
    """어떤 질의에도 쓸 수 있는 상태를 돌려준다 (키 없어도, 실패해도)"""
    _require_seeded_graph()
    for query in ["부산 여행", "", "???", "런던"]:
        state = _run(query)
        assert isinstance(state.get("results"), list), f"{query!r}: results가 리스트가 아님"
        assert isinstance(state.get("missing_entities"), list), f"{query!r}: missing_entities 없음"
        assert isinstance(state.get("plan"), dict), f"{query!r}: plan이 dict가 아님"


def test_known_query_finds_evidence():
    """그래프에 있는 대상을 물으면 근거를 찾는다"""
    _require_seeded_graph()
    state = _run("1998년 부산 여행 때 엄마는 몇 살이었어?")
    ids = {n["id"] for n in state["results"]}
    assert "E01" in ids, f"1998 부산 가족여행(E01)을 못 찾음: {sorted(ids)}"
    assert "P02" in ids, f"박서연(P02)을 못 찾음: {sorted(ids)}"


def test_plan_normalization_is_defensive():
    """계획 JSON이 형식을 벗어나도 기대 구조로 정리된다"""
    # 문자열이 배열 자리에 온 경우, 연도가 숫자/엉뚱한 값인 경우
    plan = chat_graph._normalize_plan(
        {"persons": "엄마", "places": ["부산", "  "], "year": 1998, "intent": " fact "}
    )
    assert plan["persons"] == ["엄마"]
    assert plan["places"] == ["부산"]
    assert plan["year"] == "1998"
    assert plan["intent"] == "fact"

    # 쓰레기 입력도 죽지 않고 빈 계획이 된다
    for junk in (None, {}, {"year": "옛날"}, {"persons": 123}):
        plan = chat_graph._normalize_plan(junk)
        assert plan["persons"] == [] or isinstance(plan["persons"], list)
        assert plan["year"] is None or plan["year"].isdigit()


def test_multiword_entity_is_expanded():
    """여러 낱말로 된 대상은 낱말 단위까지 펼쳐 검색한다

    계획은 "광안리 해수욕장"을 뽑는데 사진 설명에는 "광안리 해변"으로 적혀 있다.
    전체 구문으로만 찾으면 사진을 놓친다.
    """
    expanded = chat_graph._expand_entity("광안리 해수욕장")
    assert expanded[0] == "광안리 해수욕장", "전체 구문이 맨 앞에 와야 점수가 유지된다"
    assert "광안리" in expanded
    assert "해수욕장" in expanded
    # 한 낱말이면 그대로
    assert chat_graph._expand_entity("부산") == ["부산"]


def test_entity_existence_check():
    """그래프가 아는 단어와 모르는 단어를 구분한다 (신뢰도 판정의 근거)"""
    _require_seeded_graph()
    assert graph_search.entity_exists("부산")
    assert graph_search.entity_exists("광안리")
    assert not graph_search.entity_exists("런던")
    assert not graph_search.entity_exists("스키장")
    # 한 글자는 판정에서 제외 (조사가 섞여 들어오는 것을 막는다)
    assert not graph_search.entity_exists("이")


def test_absent_target_is_not_marked_confirmed():
    """그래프에 없는 대상을 물으면 "확인된 기록 기반"으로 표시하지 않는다

    '런던 여행'은 런던 기록이 없는데도 '여행'이 매칭되어 근거가 생긴다.
    계획 단계가 런던을 없는 대상으로 잡아내야 신뢰도 표시가 정직해진다.
    """
    if not llm_client.is_enabled():
        print("     (EXAONE 키 없음 - 계획 노드를 못 돌려 건너뜀)")
        return

    _require_seeded_graph()
    state = _run("런던 여행 사진 보여줘")
    assert state["planned_by_llm"], "계획 노드가 LLM을 쓰지 못했다"
    assert "런던" in state["missing_entities"], (
        f"런던이 없는 대상으로 잡히지 않음: {state['missing_entities']}"
    )

    # 근거는 있지만(여행 매칭) 신뢰도는 confirmed가 아니어야 한다
    sources = _extract_sources(state["results"])
    confidence = "confirmed" if sources and not state["missing_entities"] else "ai_inferred"
    assert sources, "근거가 아예 없으면 이 케이스를 검증할 수 없다"
    assert confidence == "ai_inferred", "없는 대상인데 confirmed로 표시됨"


def test_known_target_is_marked_confirmed():
    """그래프에 있는 대상은 확인된 기록으로 표시된다 (위 테스트의 대조군)"""
    if not llm_client.is_enabled():
        print("     (EXAONE 키 없음 - 계획 노드를 못 돌려 건너뜀)")
        return

    _require_seeded_graph()
    state = _run("부산 여행 사진 보여줘")
    assert not state["missing_entities"], f"없는 대상으로 잘못 잡힘: {state['missing_entities']}"
    sources = _extract_sources(state["results"])
    assert sources, "부산 여행 근거를 못 찾음"


# (질의, confirmed로 표시되어야 하는가, 설명)
# 화면의 추천 질문이 ai_inferred로 떨어지면 데모에서 "AI 추론 포함"이 뜬다.
# 반대로 없는 대상이 confirmed로 뜨면 신뢰 표시가 거짓이 된다. 양방향을 함께 지킨다.
CONFIDENCE_CASES = [
    ("우리 가족이 부산 처음 간 게 언제야?", True, "추천칩1"),
    ("제주도 여행에서 뭐 했어?", True, "추천칩2"),
    ("서연이 생일파티 사진 보여줘", False, "추천칩3 - 데이터에 생일파티가 없다"),
    ("아빠가 기억하는 부산 여행 이야기 알려줘", True, "추천칩4"),
    ("1998년 부산 여행 때 엄마는 몇 살이었어?", True, "기획안 대표질문"),
    ("광안리 해수욕장 사진 보여줘", True, "사진 검색"),
    ("할머니 칠순은 언제였어?", True, "이벤트"),
    ("런던 여행 사진 보여줘", False, "없는 장소"),
    ("2019년에 뭐 했어?", False, "없는 연도"),
    ("스키장 사진 있어?", False, "없는 장소"),
]


def test_confidence_matches_reality():
    """신뢰도 표시가 실제 기록 유무와 일치한다

    과거 규칙은 "근거가 하나라도 있으면 confirmed"였다. '런던 여행'을 물으면
    '여행'이 매칭돼 부산·제주 기록이 잡히고, 런던 기록이 없는데도
    "확인된 기록 기반"이 떴다.
    """
    if not llm_client.is_enabled():
        print("     (EXAONE 키 없음 - 계획 노드를 못 돌려 건너뜀)")
        return

    _require_seeded_graph()
    failures = []
    for query, want_confirmed, note in CONFIDENCE_CASES:
        state = _run(query)
        sources = _extract_sources(state["results"])
        confirmed = bool(sources) and not state["missing_entities"]
        if confirmed != want_confirmed:
            failures.append(
                f"  {query!r} ({note}): "
                f"{'confirmed' if confirmed else 'ai_inferred'} 인데 "
                f"{'confirmed' if want_confirmed else 'ai_inferred'} 기대. "
                f"없는대상={state['missing_entities']}"
            )
    assert not failures, "신뢰도 판정 불일치:\n" + "\n".join(failures)


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
