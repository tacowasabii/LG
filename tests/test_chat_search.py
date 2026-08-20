"""Memory Chat 검색 회귀 테스트

의존성 없이 그대로 실행할 수 있다 (pytest가 있으면 pytest로도 수집된다):

    python tests/test_chat_search.py

시드된 그래프(data/graph.json)를 읽으므로 먼저 아래를 실행해야 한다:

    python scripts/seed_from_metadata.py
    python scripts/generate_profiles.py

이 테스트가 지키는 것: 조사가 없는 맨 명사('부산')와 호칭('엄마', '딸')로
검색이 되어야 하고, 정답 노드가 상위 5개 안에 들어야 한다. 상위 5개만
소스 뱃지가 되므로 순위가 곧 근거 품질이다.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services.chat_engine import (  # noqa: E402
    MAX_SOURCES,
    _extract_sources,
    _format_search_results,
    _query_terms,
    _score_node,
    _search_graph,
)
from backend.models.graph_models import RelationCategory, RelationType  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402


# (질의, 반드시 찾아야 하는 노드 id, 설명)
SEARCH_CASES = [
    # 기획안 발표 스토리보드의 대표 질문
    ("엄마는 이때 몇 살이었어?", {"P02"}, "기획안 3:00-4:10 대표질문"),
    ("1998년 부산 여행 때 엄마는 몇 살이었어?", {"P02", "E01"}, "대표질문 + 사건 특정"),
    # 채팅 화면의 추천 질문
    ("우리 가족이 부산 처음 간 게 언제야?", {"E01"}, "추천칩"),
    ("제주도 여행에서 뭐 했어?", {"E03"}, "추천칩"),
    ("아빠가 기억하는 부산 여행 이야기 알려줘", {"P01", "E01"}, "추천칩"),
    # 호칭 - relation 필드를 검색해야 잡힌다
    ("엄마", {"P02"}, "호칭"),
    ("아빠", {"P01"}, "호칭"),
    ("할머니", {"P05"}, "호칭"),
    ("딸", {"P03"}, "한 글자 호칭"),
    ("아들", {"P04"}, "호칭"),
    ("할머니가", {"P05"}, "호칭 + 조사"),
    # 다어절 - 조사가 없는 맨 명사도 개별 검색되어야 한다
    ("부산 여행", {"E01"}, "다어절"),
    ("김하늘 결혼식", {"P03", "E07"}, "이름 + 다어절"),
    ("제주도 여름여행", {"E03"}, "다어절"),
    ("가족 캠핑", {"E06"}, "다어절"),
    ("부산에서", {"E01"}, "조사"),
    # 이름
    ("박서연", {"P02"}, "이름"),
    ("김하늘", {"P03"}, "이름"),
]

# 상위 5개(소스 뱃지 window) 안에 들어와야 하는 케이스
TOP5_CASES = [
    ("부산 여행", "E01"),
    ("할머니 칠순잔치", "E04"),
    ("엄마", "P02"),
    ("김하늘 결혼식", "P03"),
    ("1998년 부산 여행 때 엄마는 몇 살이었어?", "E01"),
]

# 데이터에 없는 대상 - 최상위가 엉뚱한 확신으로 채워지지 않아야 한다
ABSENT_CASES = ["강아지", "스키장에서", "그거 뭐였지"]


def _require_seeded_graph():
    persons = graph_manager.get_persons()
    events = graph_manager.get_events()
    if len(persons) < 5 or len(events) < 8:
        raise AssertionError(
            f"시드된 그래프가 필요합니다 (인물 {len(persons)}명, 이벤트 {len(events)}개). "
            "python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def test_search_finds_required_nodes():
    """조사 없는 맨 명사와 호칭으로도 정답 노드가 검색된다"""
    _require_seeded_graph()
    failures = []
    for query, required, note in SEARCH_CASES:
        found = {n["id"] for n in _search_graph(query)}
        missing = required - found
        if missing:
            failures.append(f"  {query!r} ({note}): {sorted(missing)} 누락")
    assert not failures, "검색 실패:\n" + "\n".join(failures)


def test_correct_node_ranks_in_badge_window():
    """정답 노드가 상위 5개 안에 든다 (상위 5개만 소스 뱃지가 된다)"""
    _require_seeded_graph()
    failures = []
    for query, expected_id in TOP5_CASES:
        top5 = [n["id"] for n in _search_graph(query)[:5]]
        if expected_id not in top5:
            failures.append(f"  {query!r}: {expected_id} 가 상위5({top5}) 밖")
    assert not failures, "순위 실패:\n" + "\n".join(failures)


def test_absent_targets_do_not_match():
    """데이터에 없는 대상은 검색되지 않는다"""
    _require_seeded_graph()
    failures = []
    for query in ABSENT_CASES:
        results = _search_graph(query)
        if results:
            failures.append(f"  {query!r}: {len(results)}건 매칭 (0건이어야 함)")
    assert not failures, "오탐:\n" + "\n".join(failures)


def test_bare_noun_is_searched_individually():
    """조사가 붙지 않은 토큰도 검색어 목록에 들어간다

    과거 버그: 조사가 실제로 깎인 토큰만 검색해서 '부산'이 통째로 빠졌다.
    """
    terms = _query_terms("부산 여행 언제 갔어?")
    assert "부산" in terms, f"'부산'이 검색어에 없음: {terms}"
    assert "여행" in terms, f"'여행'이 검색어에 없음: {terms}"


def test_single_char_relation_allowed_but_particles_not():
    """한 글자 호칭은 허용하되 한 글자 조사는 검색어가 되지 않는다"""
    assert "딸" in _query_terms("딸"), "그래프에 있는 한 글자 호칭이 빠졌다"
    # '이', '가', '의'는 어떤 인물의 relation도 아니므로 검색어가 되어선 안 된다
    for particle in ("이", "가", "의"):
        assert particle not in _query_terms(particle), f"조사 {particle!r}가 검색어로 샜다"


def test_relation_field_is_searchable():
    """search_nodes가 relation을 뒤진다 (호칭으로 인물을 찾는 유일한 경로)"""
    assert "relation" in graph_manager.SEARCH_FIELDS
    hits = {n["id"] for n in graph_manager.search_nodes("엄마")}
    assert "P02" in hits, f"'엄마'로 박서연을 못 찾음: {sorted(hits)}"


def test_person_context_includes_birth_date():
    """인물 컨텍스트에 생년월일이 실린다

    연도만 주면 생일 경과 여부를 알 수 없어 만나이가 1살 어긋난다.
    """
    _require_seeded_graph()
    context = _format_search_results(_search_graph("엄마"))
    person_lines = [line for line in context.split("\n") if "[인물]" in line]
    assert person_lines, f"인물 줄이 없음:\n{context}"
    assert "생년월일" in person_lines[0], f"생년월일이 없음: {person_lines[0]}"
    assert "1973-09-02" in person_lines[0], f"실제 날짜가 없음: {person_lines[0]}"


def test_exact_field_match_outranks_substring():
    """호칭 완전 일치가 부분 일치보다 높은 점수를 받는다"""
    terms = _query_terms("엄마")
    mother = graph_manager.get_node("P02")
    father = graph_manager.get_node("P01")
    assert _score_node(mother, terms) > _score_node(father, terms)


def test_photos_are_reachable_by_scene_description():
    """사진이 장면 설명으로 검색된다

    scene_description은 사진이 가진 유일한 텍스트다. 검색 대상에서 빠지면
    미디어 노드는 어떤 질의로도 직접 도달할 수 없다.
    """
    _require_seeded_graph()
    assert "scene_description" in graph_manager.SEARCH_FIELDS
    hits = [n for n in graph_manager.search_nodes("광안리") if n.get("node_type") == "media"]
    assert hits, "'광안리'로 사진을 하나도 못 찾음"
    # 점수 테이블에도 있어야 순위에 반영된다 (없으면 0점으로 뒤로 밀린다)
    photo = hits[0]
    assert _score_node(photo, _query_terms("광안리")) > 0, "장면 설명 매칭이 점수 0점"


def test_media_context_includes_scene_description():
    """LLM 컨텍스트에 장면 설명이 실린다

    검색에만 쓰고 컨텍스트에서 빼면, 모델은 사진이 뭘 담고 있는지 모른 채로
    답해야 해서 근거가 있는데도 추측하게 된다.
    """
    _require_seeded_graph()
    context = _format_search_results(_search_graph("광안리"))
    media_lines = [line for line in context.split("\n") if "[미디어]" in line]
    assert media_lines, f"미디어 줄이 없음:\n{context}"
    assert any("장면:" in line for line in media_lines), f"장면 설명이 없음: {media_lines[0]}"
    assert any("광안리" in line for line in media_lines), (
        f"매칭된 근거(광안리)가 컨텍스트에 안 보임: {media_lines[0]}"
    )


def test_badge_window_is_not_wasted_on_unciteable_nodes():
    """뱃지로 만들 수 없는 노드(place 등)가 상위에 와도 근거 5개를 채운다"""
    _require_seeded_graph()
    results = _search_graph("부산 여행 사진 보여줘")
    citeable = [n for n in results if n.get("node_type") in ("media", "event", "memory", "person")]
    expected = min(MAX_SOURCES, len(citeable))
    sources = _extract_sources(results)
    assert len(sources) == expected, (
        f"근거 {len(sources)}개 (기대 {expected}개). "
        f"상위5={[n['id'] for n in results[:5]]}"
    )


def test_memory_context_includes_speaker():
    """기억 컨텍스트에 화자가 실린다

    화자가 없으면 모델이 기억의 주인을 뒤바꿔 답한다. 실제로 아빠(P01)의
    캠코더 기억을 "엄마가 캠코더로 찍으며"로 잘못 말하는 것을 확인했다.
    같은 사건에 대한 관점별 기억을 구분하는 근거이기도 하다.
    """
    _require_seeded_graph()
    context = _format_search_results(_search_graph("캠코더"))
    memory_lines = [line for line in context.split("\n") if "[기억]" in line]
    assert memory_lines, f"기억 줄이 없음:\n{context}"
    assert any("김민수" in line for line in memory_lines), (
        f"화자(김민수)가 컨텍스트에 없음: {memory_lines}"
    )


def test_relation_edges_carry_category_and_label():
    """사람 사이 관계 엣지가 분류와 관계명을 함께 담는다

    지금 그래프에는 가족만 있다. 그래도 분류가 엣지에 실려 있어야 나중에
    가족 밖 관계를 더할 때 엣지 구조를 바꾸지 않는다.
    """
    _require_seeded_graph()
    edges = [
        edge
        for edge in graph_manager.get_all_edges()
        if edge["relation"] == RelationType.RELATED_TO
    ]
    assert edges, "사람 사이 관계 엣지가 없음"

    categories = {edge["properties"].get("category") for edge in edges}
    assert categories == {RelationCategory.FAMILY}, f"가족 밖 분류가 섞였음: {categories}"

    # 관계명(부부/부녀/남매)도 함께 보존되어야 화면과 프롬프트에서 쓸 수 있다
    labels = {edge["properties"].get("relation_type") for edge in edges}
    assert {"부부", "부녀", "남매"} <= labels, f"관계명 누락: {sorted(labels)}"


def test_person_detail_includes_their_memories():
    """인물 상세가 그 사람이 남긴 기억을 내려준다 (REMEMBERS 엣지)"""
    _require_seeded_graph()
    detail = graph_manager.get_person_detail("P01")
    assert detail is not None
    assert "memories" in detail, "memories 키가 없음"
    assert detail["memories"], "김민수의 기억이 비어 있음 (시드에 M001, M005가 있어야 함)"
    ids = {m["id"] for m in detail["memories"]}
    assert "M001" in ids, f"M001이 없음: {sorted(ids)}"


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
