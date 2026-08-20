"""Memory Chat Engine - EXAONE 연동 + Graph RAG"""

from __future__ import annotations

import uuid
from datetime import date
from typing import AsyncIterator, Optional

from backend.services import chat_graph, graph_search, llm_client, memories, visibility
from backend.services.graph_manager import graph_manager
from backend.models.schemas import SourceItem


# 대화 히스토리 저장 (MVP: in-memory)
_conversations: dict[str, list[dict]] = {}

# 대화별로 마지막에 근거로 쓴 노드. 이어지는 질문은 그 자체로 검색되지 않는다 —
# "뭘 모르겠다는 거야?"에는 찾을 대상이 하나도 없어서 검색이 빈손으로 돌아오고,
# 그러면 모델은 "반드시 [검색 결과]를 근거로" 라는 규칙과 방금 자기가 한 말
# 사이에서 엉킨다. 앞 turn의 근거를 그대로 물려준다.
_last_results: dict[str, list[dict]] = {}


SYSTEM_PROMPT = """너는 "LG HomeStory"의 AI 어시스턴트야.
사람들의 사진, 영상, 음성, 기억을 연결한 Memory Graph를 기반으로 질문에 답변해.
[인물]의 관계 표기를 그대로 존중해.

규칙:
1. 반드시 제공된 [검색 결과]를 근거로 답변해. 근거 없는 내용은 만들어내지 마.
2. 답변할 때 어떤 사진/이벤트/기억을 참고했는지 명시해.
3. 이벤트에 붙은 확인 상태에 따라 말투를 달리해.
   - shared(가족 여러 명의 기억이 있다) → 단정적으로
   - alone(한 사람의 기억만 있다) → 누구의 기억인지 밝히면서
   - varied(가족이 조금 다르게 기억한다) → 한쪽으로 정리하지 말고 누가 어떻게 기억하는지
     복수 버전을 나란히 제시해. 어느 쪽이 맞다고 판정하지 마.
4. 사람 이름은 [검색 결과]에 [인물]로 들어온 사람만 부른다. 사진 설명이나 기억
   문장에 스쳐 나온 이름을 근거처럼 단정하지 마 — 화면에 근거로 보여주지 않은
   이름을 말하면 읽는 사람이 확인할 방법이 없다.
5. [기억]에 "(질문 "..."에 대한 답)"이 붙어 있으면 그 기억은 그 질문에 대한 답이다.
   "모르겠어요"처럼 짧은 답을 옮길 때는 무엇을 모른다고 한 것인지 그 질문을 함께
   말해 — 답만 옮기면 읽는 사람은 무슨 이야기인지 알 수 없다.
6. 앞선 답변을 이어받는 질문("뭘 모르겠다는 거야?", "그게 언제야?")은 대화
   기록에서 무엇을 가리키는지 찾아 그 이야기를 이어서 답해. 다른 주제로 옮기지 마.
7. 따뜻하고 다정한 톤으로 답변해.
8. 한국어로 답변해.
"""


async def process_chat(
    query: str,
    conversation_id: Optional[str] = None,
    viewer_id: Optional[str] = None,
) -> dict:
    """채팅 질의 처리

    Flow:
    1. 질의 계획 그래프 실행 (의도 분석 → 그래프 대조 → 검색)
    2. 검색 결과를 컨텍스트로 EXAONE에 전달
    3. 답변 생성 + 소스 연결 + 신뢰도 판정
    """
    prep = await _prepare(query, conversation_id, viewer_id)

    # 2. 모델 호출
    answer, llm_used = await _call_exaone(prep["messages"], prep["search_results"])

    return _finish(query, answer, llm_used, prep)


async def _prepare(
    query: str, conversation_id: Optional[str], viewer_id: Optional[str]
) -> dict:
    """모델을 부르기 전까지 (세션·검색·프롬프트). 한 번에 받는 경로와 스트리밍이 공유한다."""
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    if conversation_id not in _conversations:
        _conversations[conversation_id] = []

    # 질의 계획 + 검색 (LangGraph). 실패해도 규칙 기반 결과가 돌아온다.
    plan_state = await chat_graph.run(query)
    # 볼 수 없는 원본은 근거로도 쓰지 않는다. 뱃지에서만 감추면 LLM이 본문에서
    # 그 사진의 장면 설명을 말해 버린다 (기획안 08장 Asset 권한).
    search_results = visibility.filter_search_results(plan_state["results"], viewer_id)
    missing_entities = plan_state["missing_entities"]

    # 앞 답변에 매달린 질문이면 앞 turn의 근거를 그대로 쓴다 (아래 _is_followup).
    # 물려받은 것도 지금 보는 사람의 권한으로 다시 걸러야 한다 — 그동안 공개
    # 범위가 바뀌었을 수 있고, 이 대화를 다른 사람이 이어받을 수도 있다.
    carried_over = False
    if not search_results and _is_followup(plan_state):
        previous = _last_results.get(conversation_id)
        if previous:
            search_results = visibility.filter_search_results(previous, viewer_id)
            carried_over = bool(search_results)
    if search_results:
        _last_results[conversation_id] = search_results

    context_text = _format_search_results(search_results)

    return {
        "conversation_id": conversation_id,
        "search_results": search_results,
        "missing_entities": missing_entities,
        "messages": _build_messages(
            query, context_text, conversation_id, missing_entities, carried_over
        ),
    }


def _is_followup(plan_state: dict) -> bool:
    """이 질문이 스스로 가리키는 대상 없이 앞 답변에 매달린 질문인가

    질의 계획이 인물·장소·사건·연도를 하나도 뽑지 못한 질문이다 — "뭘 모르겠다는
    거야?", "그게 언제야?" 처럼. 이런 질문은 앞 turn이 무엇을 말했는지 알아야
    답할 수 있다.

    계획을 모델이 세우지 못했을 때(폴백)는 판정하지 않는다. 그때는 계획이 늘
    비어 있어서 없는 대상을 물은 질문("런던 여행 얘기해줘")까지 이어지는 질문으로
    보고, 엉뚱하게 앞의 부산 근거로 답하게 된다.
    """
    if not plan_state.get("planned_by_llm"):
        return False
    plan = plan_state.get("plan") or {}
    if plan.get("year"):
        return False
    return not any(plan.get(key) for key in ("persons", "places", "events"))


def _finish(query: str, answer: str, llm_used: bool, prep: dict) -> dict:
    """대화 저장 + 근거·신뢰도 판정"""
    conversation_id = prep["conversation_id"]
    _conversations[conversation_id].append({"role": "user", "content": query})
    _conversations[conversation_id].append({"role": "assistant", "content": answer})

    sources = _extract_sources(prep["search_results"])

    # 근거가 있어도 질문이 지목한 대상이 그래프에 없으면 "확인된 기록"이 아니다.
    # '런던 여행'을 물었을 때 부산·제주 기록이 잡혀도 confirmed로 표시하면 안 된다.
    confidence = "confirmed" if sources and not prep["missing_entities"] else "ai_inferred"

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
        "conversation_id": conversation_id,
        # 이 답변을 실제 모델이 썼는지. 폴백이면 화면이 그렇게 밝힌다.
        "llm_used": llm_used,
        # 어느 모델이 답했는지. 배포는 Friendli, 사내망은 EXAONE이라 고정할 수 없다.
        "model": llm_client.model_for() if llm_used else None,
        "provider": llm_client.provider_for(None) if llm_used else None,
    }


async def process_chat_stream(
    query: str,
    conversation_id: Optional[str] = None,
    viewer_id: Optional[str] = None,
) -> AsyncIterator[dict]:
    """process_chat과 같은 일을 하되 답변을 토큰 단위로 흘려보낸다

    답변 전체를 기다리면 화면이 10~20초 비어 있다. 근거(사진·사건)는 모델을 부르기
    전에 이미 정해지므로 먼저 보내고, 그다음 문장을 이어 보낸다.

    yield 형태:
        {"type": "meta",  ...근거·신뢰도·대화 id}
        {"type": "delta", "text": "..."}      (여러 번)
        {"type": "done",  ...최종 페이로드}
    """
    prep = await _prepare(query, conversation_id, viewer_id)
    sources = _extract_sources(prep["search_results"])

    yield {
        "type": "meta",
        "conversation_id": prep["conversation_id"],
        "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in sources],
        "confidence": (
            "confirmed" if sources and not prep["missing_entities"] else "ai_inferred"
        ),
    }

    chunks: list[str] = []
    async for piece in llm_client.stream(prep["messages"], max_tokens=1024):
        chunks.append(piece)
        yield {"type": "delta", "text": piece}

    if chunks:
        answer, llm_used = "".join(chunks), True
    else:
        # 모델을 못 쓴 경우. 규칙 기반 답변을 한 조각으로 보낸다.
        answer, llm_used = _simulate_response(prep["search_results"]), False
        yield {"type": "delta", "text": answer}

    payload = _finish(query, answer, llm_used, prep)
    yield {
        "type": "done",
        "answer": payload["answer"],
        "sources": [
            s.model_dump() if hasattr(s, "model_dump") else s for s in payload["sources"]
        ],
        "confidence": payload["confidence"],
        "conversation_id": payload["conversation_id"],
        "llm_used": payload["llm_used"],
        "model": payload["model"],
        "provider": payload["provider"],
    }


# 검색 원시함수는 graph_search로 옮겼다 (chat_graph와 공유, 순환 import 방지).
# 아래 별칭은 기존 호출부와 테스트가 쓰던 이름을 유지하기 위한 것이다.
_PARTICLE_CHARS = graph_search.PARTICLE_CHARS
_PUNCT = graph_search.PUNCT
_FIELD_WEIGHTS = graph_search.FIELD_WEIGHTS
_query_terms = graph_search.query_terms
_score_node = graph_search.score_node
_search_graph = graph_search.search_graph


def _format_search_results(results: list[dict]) -> str:
    """검색 결과를 LLM 컨텍스트 텍스트로 변환"""
    if not results:
        return "검색 결과가 없습니다."

    lines = ["[검색 결과]"]
    for i, node in enumerate(results, 1):
        node_type = node.get("node_type", "unknown")

        if node_type == "event":
            info = [
                f"날짜: {node.get('date_start', '미상')}",
                f"설명: {node.get('description', '')}",
            ]
            # 기억이 얼마나 쌓였는지에 따라 답변 말투가 달라진다.
            # 이걸 안 주면 서로 다른 기억을 한쪽으로 정리해서 말한다.
            state = memories.state_of(node["id"])
            if state:
                info.append(f"기억상태: {state['state']}")
                if state["varied"]:
                    names = ", ".join(
                        p["name"] for p in state["contributors"] if p and p.get("name")
                    )
                    info.append(f"가족이 조금 다르게 기억함: {names}")
            lines.append(f"{i}. [이벤트] {node.get('title', '')} ({', '.join(info)})")
        elif node_type == "person":
            info = [f"관계: {node.get('relation', '')}"]
            # 나이를 묻는 질문에 답하려면 생일이 컨텍스트에 있어야 한다.
            # 연도만 주면 생일 경과 여부를 알 수 없어 만나이가 1살 어긋난다.
            if node.get("birth_date"):
                info.append(f"생년월일: {node['birth_date']}")
            elif node.get("birth_year"):
                info.append(f"출생연도: {node['birth_year']}년")
            lines.append(f"{i}. [인물] {node.get('name', '')} ({', '.join(info)})")
        elif node_type == "place":
            lines.append(
                f"{i}. [장소] {node.get('name', '')} "
                f"(주소: {node.get('address', '')})"
            )
        elif node_type == "media":
            info = [
                f"날짜: {node.get('exif_date', node.get('created_at', ''))}",
                f"타입: {node.get('media_type', '')}",
            ]
            if node.get("scene_description"):
                # 검색에는 쓰이는데 컨텍스트에 없으면, 사진이 뭘 담고 있는지
                # 모른 채로 답해야 해서 모델이 추측하게 된다
                info.append(f"장면: {node['scene_description']}")
            lines.append(f"{i}. [미디어] {node.get('original_filename', '')} ({', '.join(info)})")
        elif node_type == "memory":
            content = node.get("content", "")
            # 화자를 주지 않으면 모델이 기억의 주인을 뒤바꿔 답한다.
            # (아빠의 캠코더 기억을 엄마의 것으로 말하는 사례를 확인했다)
            speaker = None
            contributor_id = node.get("contributor_id")
            if contributor_id:
                person = graph_manager.get_node(contributor_id)
                speaker = person.get("name") if person else None
            line = f"{i}. [기억] {speaker}: {content}" if speaker else f"{i}. [기억] {content}"
            # 인터뷰로 남은 기억은 어떤 질문에 대한 답이다. 그 질문을 빼면
            # "모르겠어요" 같은 짧은 답이 무엇에 대한 것인지 알 수 없어,
            # "뭘 모르겠다는 거야?"라고 되물었을 때 답이 엉킨다.
            asked = node.get("question")
            if asked:
                line += f' (질문 "{asked}"에 대한 답)'
            lines.append(line)

    return "\n".join(lines)


def _build_messages(
    query: str,
    context: str,
    conversation_id: str,
    missing_entities: Optional[list[str]] = None,
    carried_over: bool = False,
) -> list[dict]:
    """EXAONE API용 메시지 빌드

    carried_over는 [검색 결과]가 이 질문으로 찾은 것이 아니라 앞 turn에서
    물려받은 것임을 뜻한다. 밝혀 주지 않으면 모델은 그 근거가 지금 질문에
    직접 맞아떨어지는 것으로 읽는다.
    """
    # 오늘 날짜를 주지 않으면 나이·경과연수 계산에서 모델의 학습 시점을 기준으로 삼는다
    system_content = f"{SYSTEM_PROMPT}\n오늘 날짜: {date.today().isoformat()}"
    messages = [{"role": "system", "content": system_content}]

    # 이전 대화 히스토리 추가 (최근 6개)
    history = _conversations.get(conversation_id, [])
    if history:
        messages.extend(history[-6:])

    # 현재 질의 + 검색 컨텍스트
    user_message = f"""질문: {query}

{context}

위 검색 결과를 참고하여 질문에 답변해주세요. 근거가 되는 이벤트나 미디어가 있으면 언급해주세요."""

    if carried_over:
        user_message += (
            "\n\n참고: 이 질문은 앞선 답변을 이어받는 질문입니다. 위 [검색 결과]는 "
            "앞 질문에서 쓴 근거를 그대로 가져온 것입니다. 대화 기록에서 이 질문이 "
            "무엇을 가리키는지 찾아, 그 대상에 대해 이어서 답변하세요. "
            "새 주제로 옮기거나 기록이 없다고 말하지 마세요."
        )

    if missing_entities:
        # 질의 계획이 그래프에 없다고 판정한 대상. 있는 척 답하지 않게 명시한다.
        user_message += (
            f"\n\n주의: 다음 대상은 기록에 없습니다 - {', '.join(missing_entities)}. "
            "없다는 사실을 분명히 밝히고, 실제로 있는 기록만 근거로 답변하세요."
        )

    messages.append({"role": "user", "content": user_message})
    return messages


async def _call_exaone(
    messages: list[dict], search_results: list[dict]
) -> tuple[str, bool]:
    """EXAONE API 호출 (키 없음/실패 시 시뮬레이션 폴백)

    Returns:
        (답변, 실제 모델이 썼는가). 두 번째 값을 화면까지 올린다 — 폴백이 조용히
        일어나면 사용자는 "LLM이 이상하다"고 느끼고 원인을 찾을 수 없다.
        (실제로 그 질문을 받았다: "실제 llm 같지가 않아")
    """
    answer = await llm_client.complete(messages, max_tokens=1024)
    if answer is None:
        return _simulate_response(search_results), False
    return answer, True


def _simulate_response(search_results: list[dict]) -> str:
    """EXAONE을 쓸 수 없을 때의 대체 응답

    이전에는 프롬프트 텍스트를 되파싱해서 첫 이벤트와 무관한 첫 장소를 짝지었다.
    "1998 부산 가족여행 ... 장소는 대전 가족식당" 같은 문장이 그렇게 나왔다.
    이제 그래프 노드를 직접 받아, 그 이벤트에 실제로 연결된 장소와 참여자만 쓴다.
    """
    events = [n for n in search_results if n.get("node_type") == "event"]

    if not events:
        persons = [n for n in search_results if n.get("node_type") == "person"]
        if persons:
            names = ", ".join(p.get("name", "") for p in persons[:3] if p.get("name"))
            return f"{names}에 대한 기록이 있어요. 어떤 부분이 궁금하신가요?"
        return (
            "아직 관련 기록을 찾지 못했어요. "
            "더 많은 사진이나 이야기를 추가하면 더 잘 답변드릴 수 있을 거예요!"
        )

    event = events[0]
    answer = f"기록을 확인해보니, {event.get('title', '')}이(가) 관련 기록으로 있어요."

    # 그 이벤트에 실제로 연결된 장소만 언급한다
    place = graph_manager.get_node(event.get("location_id") or "")
    if place and place.get("name"):
        answer += f" 장소는 {place['name']}이었네요."

    # 그 이벤트에 실제로 참여한 사람만 언급한다
    participants = [
        node.get("name")
        for node in graph_manager.get_connected_nodes(event["id"])
        if node.get("node_type") == "person" and node.get("name")
    ]
    if participants:
        answer += f" {', '.join(participants[:3])}이(가) 함께했어요."

    return answer + "\n\n더 자세한 이야기가 궁금하시면 물어봐주세요!"


# 화면에 띄울 근거 뱃지 개수 (인물은 이 상한과 별도로 전부 담는다 — 아래 참고)
MAX_SOURCES = 5


def _event_thumbnail(event_id: str) -> Optional[str]:
    """사건에 연결된 사진 한 장의 썸네일 경로

    영상·음성은 목록에서 그림이 되지 않으므로 사진만 고른다.
    """
    for neighbor in graph_manager.get_connected_nodes(event_id):
        if neighbor.get("node_type") != "media":
            continue
        if neighbor.get("media_type") not in (None, "photo"):
            continue
        thumb = neighbor.get("thumbnail_path") or neighbor.get("file_path")
        if thumb:
            return thumb
    return None


def _extract_sources(search_results: list[dict]) -> list[SourceItem]:
    """검색 결과에서 답변 소스 추출

    상위 5개 노드를 잘라서 걸러면, 뱃지로 만들 수 없는 노드(place 등)가
    상위에 오면 그만큼 근거가 비어 보인다. 뱃지 5개가 모일 때까지 순회한다.

    인물은 그 상한 밖에서 전부 담는다. 채점(Trust Harness)의 Attribution Safety가
    "답변에 나온 이름이 화면의 근거에 있는가"를 재는데, 검색 문맥에는 있던 사람이
    상위 5개에서 밀려 이름만 언급되는 일이 절반 가까이 있었다 (50점). 이름을
    말하려면 그 사람을 근거로 함께 보여줘야 한다 — 아니면 읽는 사람이 확인할
    방법이 없다. 인물 노드는 그래프 전체에 몇 명뿐이라 목록이 길어지지 않는다.
    """
    sources = []
    seen_ids = set()

    # 인물 먼저 (상한과 무관하게 전부). 기억을 남긴 사람도 함께 담는다 —
    # 컨텍스트가 "[기억] 박서연: ..." 처럼 기여자 이름을 함께 주기 때문에,
    # 답변이 그 이름을 부르는데 근거에 없으면 확인할 방법이 없다.
    person_ids = []
    for node in search_results:
        if node.get("node_type") == "person":
            person_ids.append(node.get("id", ""))
        elif node.get("node_type") == "memory" and node.get("contributor_id"):
            person_ids.append(node["contributor_id"])

    for person_id in person_ids:
        if not person_id or person_id in seen_ids:
            continue
        person = graph_manager.get_node(person_id)
        if not person or person.get("node_type") != "person":
            continue
        seen_ids.add(person_id)
        sources.append(SourceItem(
            type="person",
            id=person_id,
            title=person.get("name", ""),
            thumbnail=person.get("thumbnail_url"),
            confidence=0.9,
        ))

    person_count = len(sources)

    for node in search_results:
        if len(sources) - person_count >= MAX_SOURCES:
            break

        node_id = node.get("id", "")
        if node_id in seen_ids:
            continue
        seen_ids.add(node_id)

        node_type = node.get("node_type", "")
        if node_type == "media":
            sources.append(SourceItem(
                type="media",
                id=node_id,
                title=node.get("original_filename", ""),
                thumbnail=node.get("thumbnail_path"),
                confidence=0.9 if node.get("confidence") == "confirmed" else 0.7,
            ))
        elif node_type == "event":
            sources.append(SourceItem(
                type="event",
                id=node_id,
                title=node.get("title", ""),
                # 사건 자체에는 그림이 없다. 그 사건의 사진 한 장을 얼굴로 쓴다 —
                # 근거가 글자만 늘어서면 "무엇을 보고 답했는지"가 읽히지 않는다.
                thumbnail=_event_thumbnail(node_id),
                confidence=0.9 if node.get("confidence") == "confirmed" else 0.7,
            ))
        elif node_type == "memory":
            sources.append(SourceItem(
                type="memory",
                id=node_id,
                title=node.get("content", "")[:50],
                confidence=0.85,
            ))
        # 인물은 위에서 이미 담았다

    return sources
