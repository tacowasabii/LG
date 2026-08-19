"""Memory Graph 검색 원시함수

chat_engine과 chat_graph(LangGraph 노드)가 함께 쓴다. 두 모듈이 서로를
import하면 순환이 생기므로 공용 부분을 여기로 분리했다.
"""

from __future__ import annotations

from backend.services.graph_manager import graph_manager

# 검색어 뒤에서 떼어낼 조사
PARTICLE_CHARS = "이가을를에서의도는은과와랑"
# 질의에서 떼어낼 문장부호
PUNCT = "?!.,~\"'()[]"

# 필드별 가중치 - 이름/제목/호칭에서 맞으면 설명·내용보다 강한 신호로 본다
FIELD_WEIGHTS = (
    ("name", 3),
    ("title", 3),
    ("relation", 3),
    ("address", 2),
    ("description", 1),
    ("content", 1),
    ("scene_description", 1),
)

# 한 번에 LLM 컨텍스트로 넘길 최대 노드 수
MAX_RESULTS = 20


def query_terms(query: str) -> list[str]:
    """질의를 검색어 목록으로 분해

    전체 문장, 각 토큰, 조사를 떼어낸 형태를 모두 후보로 쓴다.
    조사가 실제로 깎인 토큰만 검색하면 '부산'처럼 조사가 붙지 않은 맨 명사가
    개별 검색에서 통째로 빠진다.
    """
    # '딸'처럼 한 글자인 호칭은 길이 제한에 걸려 빠진다.
    # 그래프에 실제로 존재하는 호칭만 예외로 허용한다 (조사 한 글자와 구분).
    short_allowed = {
        str(person.get("relation") or "")
        for person in graph_manager.get_persons()
        if len(str(person.get("relation") or "")) == 1
    }

    terms: list[str] = []

    def push(term: str) -> None:
        term = term.strip()
        if not term or term in terms:
            return
        if len(term) >= 2 or term in short_allowed:
            terms.append(term)

    push(query)
    for token in query.split():
        token = token.strip(PUNCT)
        push(token)
        push(token.rstrip(PARTICLE_CHARS))

    return terms


def score_node(node: dict, terms: list[str]) -> int:
    """노드가 검색어들과 얼마나 맞는지 점수화

    상위 노드만 LLM 컨텍스트와 소스 뱃지에 실리므로 순위가 곧 답변 품질이 된다.
    """
    score = 0
    for field, weight in FIELD_WEIGHTS:
        value = str(node.get(field) or "").lower()
        if not value:
            continue
        for term in terms:
            term_lower = term.lower()
            if term_lower == value:
                score += weight * 2  # 필드 전체와 완전 일치 ('엄마' == relation)
            elif term_lower in value:
                score += weight
    return score


def search_with_terms(terms: list[str]) -> list[dict]:
    """주어진 검색어들로 노드를 찾아 관련도 순으로 돌려준다"""
    if not terms:
        return []

    # 1. 검색어별로 후보 수집
    candidates: dict[str, dict] = {}
    for term in terms:
        for node in graph_manager.search_nodes(term):
            candidates.setdefault(node["id"], node)

    # 2. 관련도 순 정렬
    ranked = sorted(
        candidates.values(),
        key=lambda node: score_node(node, terms),
        reverse=True,
    )

    # 3. 상위 노드의 이웃을 뒤에 덧붙여 컨텍스트 보강
    #    (직접 매칭된 노드를 순위에서 밀어내지 않도록 뒤에만 붙인다)
    results = list(ranked)
    seen = set(candidates)
    for node in ranked[:5]:
        for neighbor in graph_manager.get_connected_nodes(node["id"])[:3]:
            if neighbor["id"] not in seen:
                seen.add(neighbor["id"])
                results.append(neighbor)

    return results[:MAX_RESULTS]


def search_graph(query: str) -> list[dict]:
    """규칙 기반 경로: 질의를 토큰으로 쪼개 검색한다"""
    return search_with_terms(query_terms(query))


def entity_exists(entity: str) -> bool:
    """그래프가 이 단어를 아는지

    질의 계획이 뽑아낸 인물·장소·사건이 실제로 그래프에 있는지 판정해,
    없는 대상을 물었을 때 "확인된 기록 기반"이라고 표시하지 않도록 한다.
    """
    entity = (entity or "").strip()
    if len(entity) < 2:
        return False
    return bool(graph_manager.search_nodes(entity))
