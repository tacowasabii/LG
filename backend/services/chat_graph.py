"""Memory Chat 질의 계획 그래프 (LangGraph)

기획안 04장이 EXAONE의 역할로 내세운 Graph Query Planning을 구현한다.
그전까지 EXAONE은 답변·질문·내레이션 "생성"만 했고, 질의 해석은 substring
검색이었다.

    질의 → [계획: 인물·장소·사건·연도 추출]
             ↓
          [대조: 뽑아낸 대상이 그래프에 있는지 확인]
             ↓
          [검색: 계획한 조건으로 정밀 검색]
             ↓
          [결과 없음?] ──예──→ [완화: 토큰 기반으로 다시 검색]
             ↓ 아니오
            끝

대조 단계가 미해결 과제였던 신뢰도 표시를 해결한다. '런던 여행'처럼 그래프에
없는 대상을 물으면 missing_entities에 남아, 다른 결과가 있어도 "확인된 기록
기반"으로 표시하지 않는다.

LLM이 없거나 계획이 실패하면 규칙 기반 검색으로 그대로 내려간다.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from backend.config import CHAT_QUERY_PLANNING, EXAONE_PLANNER_MODEL
from backend.services import graph_search, llm_client
from backend.services.graph_manager import graph_manager

PLANNER_SYSTEM = """너는 기억 그래프 검색을 위한 질의 분석기야.
사용자 질문에서 검색 조건만 뽑아 JSON으로 출력해. 설명이나 인사는 하지 마.

출력 형식:
{
  "persons": ["질문에 나온 사람의 이름 또는 호칭"],
  "places": ["지명"],
  "events": ["행사·사건의 이름"],
  "year": "4자리 연도 또는 null",
  "topics": ["위 항목에 안 들어가는 핵심 명사"],
  "intent": "fact | photos | story | list"
}

규칙:
1. 질문에 실제로 등장한 표현만 넣어. 추측해서 채우지 마.
2. 조사(은/는/이/가/의/에서)는 떼고 넣어. "엄마는" -> "엄마"
3. 사진·영상·기억·이야기 같은 일반 매체어는 topics에 넣지 말고 intent로 표현해.
   사진을 찾는 질문이면 intent를 photos로.
4. 여러 사람을 뭉뚱그린 표현은 persons에 넣지 마.
   "우리 가족", "다들", "모두", "온 가족" -> persons는 빈 배열.
   특정 인물의 이름이나 호칭("엄마", "하늘", "친구")만 넣어.
5. events에는 행사·사건의 이름만 넣어 (결혼식, 졸업식, 여행, 칠순잔치, 캠핑).
   동작이나 서술은 넣지 마. "처음 간 것", "처음 가다", "놀았다" -> 넣지 않는다.
6. 해당 없으면 빈 배열이나 null.
7. JSON만 출력해."""

# 계획이 비었을 때 쓰는 빈 구조
EMPTY_PLAN: dict = {
    "persons": [],
    "places": [],
    "events": [],
    "year": None,
    "topics": [],
    "intent": None,
}


class ChatState(TypedDict, total=False):
    query: str
    plan: dict
    terms: list[str]
    results: list[dict]
    # 계획이 뽑았지만 그래프에 없는 대상. 신뢰도 표시의 근거가 된다.
    missing_entities: list[str]
    # 정밀 검색이 빈손이라 토큰 기반으로 완화했는지
    relaxed: bool
    # 계획을 LLM이 세웠는지 (규칙 기반 폴백과 구분)
    planned_by_llm: bool


def _normalize_plan(raw: Optional[dict]) -> dict:
    """LLM이 준 JSON을 기대 구조로 정리한다 (형식 이탈 방어)"""
    plan = dict(EMPTY_PLAN)
    if not raw:
        return plan

    for key in ("persons", "places", "events", "topics"):
        value = raw.get(key)
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            plan[key] = [str(v).strip() for v in value if str(v).strip()]

    year = raw.get("year")
    if isinstance(year, (str, int)):
        year_text = str(year).strip()
        plan["year"] = year_text if year_text.isdigit() and len(year_text) == 4 else None

    intent = raw.get("intent")
    if isinstance(intent, str) and intent.strip():
        plan["intent"] = intent.strip()

    return plan


# 검색어로 쓸 필드
_SEARCH_KEYS = ("persons", "places", "events", "topics")
# 신뢰도 판정에 쓸 필드.
# topics는 계획이 "뭐" 같은 조각까지 담아서 판정 근거로 쓸 수 없다.
# 검색어로는 계속 쓰되 "없는 대상" 판정에서는 뺀다.
_GATING_KEYS = ("persons", "places", "events")


def _plan_entities(plan: dict, keys: tuple = _SEARCH_KEYS) -> list[str]:
    """계획에서 뽑아낸 대상 (중복 제거, 순서 유지)"""
    entities: list[str] = []
    for key in keys:
        for value in plan.get(key) or []:
            if value not in entities:
                entities.append(value)
    return entities


def _expand_entity(entity: str) -> list[str]:
    """여러 낱말로 된 대상을 낱말 단위까지 펼친다

    계획은 "광안리 해수욕장"처럼 온전한 이름을 뽑아주는데, 사진 설명에는
    "광안리 해변"으로 적혀 있어 전체 구문으로만 찾으면 놓친다.
    전체 구문을 앞에 두어 정확한 일치가 계속 높은 점수를 받게 한다.
    """
    expanded = [entity]
    for token in entity.split():
        if len(token) >= 2 and token not in expanded:
            expanded.append(token)
    return expanded


async def _plan_node(state: ChatState) -> ChatState:
    """질의에서 검색 조건을 추출한다 (EXAONE instant, 추론 없음)"""
    query = state["query"]

    if not CHAT_QUERY_PLANNING or not llm_client.is_enabled():
        return {"plan": dict(EMPTY_PLAN), "planned_by_llm": False}

    raw = await llm_client.complete_json(
        [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": query},
        ],
        max_tokens=256,
        model=EXAONE_PLANNER_MODEL,
    )
    if raw is None:
        return {"plan": dict(EMPTY_PLAN), "planned_by_llm": False}

    return {"plan": _normalize_plan(raw), "planned_by_llm": True}


def _entity_known(entity: str) -> bool:
    """그래프가 이 대상을 아는지

    여러 낱말이면 낱말 하나라도 알면 아는 것으로 본다. 계획이 "우리 가족"처럼
    묶어서 뽑아낸 표현이 문자열 그대로는 그래프에 없어도, 그 질문이 없는 대상을
    가리키는 건 아니기 때문이다. 반대로 "런던"처럼 한 낱말이 통째로 미지이면
    없는 대상으로 본다.
    """
    if graph_search.entity_exists(entity):
        return True
    tokens = [t for t in entity.split() if len(t) >= 2]
    if len(tokens) < 2:
        return False
    return any(graph_search.entity_exists(t) for t in tokens)


def _resolve_node(state: ChatState) -> ChatState:
    """계획한 대상이 그래프에 실제로 있는지 대조한다"""
    plan = state.get("plan") or dict(EMPTY_PLAN)
    entities = _plan_entities(plan, _GATING_KEYS)

    missing = [e for e in entities if not _entity_known(e)]

    # 연도도 대조한다. 그래프에 그 해의 이벤트가 없으면 없는 것이다.
    year = plan.get("year")
    if year and not any(
        str(event.get("date_start") or "").startswith(year)
        for event in graph_manager.get_events()
    ):
        missing.append(f"{year}년")

    return {"missing_entities": missing}


def _search_node(state: ChatState) -> ChatState:
    """계획한 조건으로 정밀 검색

    계획이 없거나(폴백) 뽑아낸 대상이 하나도 없으면 토큰 기반으로 바로 간다.
    """
    plan = state.get("plan") or dict(EMPTY_PLAN)
    entities = _plan_entities(plan)
    year = plan.get("year")

    terms: list[str] = []
    for entity in entities:
        if not graph_search.entity_exists(entity):
            continue
        for term in _expand_entity(entity):
            if term not in terms:
                terms.append(term)
    if year and year not in terms:
        terms.append(year)

    if not terms:
        terms = graph_search.query_terms(state["query"])
        return {
            "terms": terms,
            "results": graph_search.search_with_terms(terms),
            "relaxed": True,
        }

    return {
        "terms": terms,
        "results": graph_search.search_with_terms(terms),
        "relaxed": False,
    }


def _relax_node(state: ChatState) -> ChatState:
    """정밀 검색이 빈손일 때 토큰 기반으로 다시 검색한다"""
    terms = graph_search.query_terms(state["query"])
    return {
        "terms": terms,
        "results": graph_search.search_with_terms(terms),
        "relaxed": True,
    }


def _needs_relax(state: ChatState) -> str:
    """정밀 검색 결과가 없고 아직 완화하지 않았으면 완화한다"""
    if not state.get("results") and not state.get("relaxed"):
        return "relax"
    return END


def _build_graph():
    builder = StateGraph(ChatState)
    builder.add_node("plan", _plan_node)
    builder.add_node("resolve", _resolve_node)
    builder.add_node("search", _search_node)
    builder.add_node("relax", _relax_node)

    builder.set_entry_point("plan")
    builder.add_edge("plan", "resolve")
    builder.add_edge("resolve", "search")
    builder.add_conditional_edges("search", _needs_relax, {"relax": "relax", END: END})
    builder.add_edge("relax", END)

    return builder.compile()


_COMPILED = None


def get_compiled_graph():
    """컴파일된 그래프 (한 번만 만든다)"""
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = _build_graph()
    return _COMPILED


async def run(query: str) -> ChatState:
    """질의 계획 그래프를 실행해 검색 결과와 대조 정보를 돌려준다

    실패해도 예외를 밖으로 내보내지 않는다. 어떤 이유로든 그래프가 죽으면
    규칙 기반 검색 결과를 돌려주고 계속 진행한다.
    """
    try:
        result = await get_compiled_graph().ainvoke({"query": query})
    except Exception as e:
        print(f"[ChatGraph] 실행 실패 ({type(e).__name__}: {str(e)[:160]}) → 규칙 기반 검색")
        terms = graph_search.query_terms(query)
        return {
            "query": query,
            "plan": dict(EMPTY_PLAN),
            "terms": terms,
            "results": graph_search.search_with_terms(terms),
            "missing_entities": [],
            "relaxed": True,
            "planned_by_llm": False,
        }

    result.setdefault("missing_entities", [])
    result.setdefault("results", [])
    result.setdefault("plan", dict(EMPTY_PLAN))
    result.setdefault("planned_by_llm", False)
    return result
