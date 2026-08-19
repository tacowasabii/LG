"""Memory Chat Engine - EXAONE 연동 + Graph RAG"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from backend.services import llm_client
from backend.services.graph_manager import graph_manager
from backend.models.schemas import SourceItem


# 대화 히스토리 저장 (MVP: in-memory)
_conversations: dict[str, list[dict]] = {}


SYSTEM_PROMPT = """너는 "LG HomeStory"의 AI 어시스턴트야.
사람들의 사진, 영상, 음성, 기억을 연결한 Memory Graph를 기반으로 질문에 답변해.
관계는 가족뿐 아니라 친구·연인도 포함된다. [인물]의 관계 표기를 그대로 존중해.

규칙:
1. 반드시 제공된 [검색 결과]를 근거로 답변해. 근거 없는 내용은 만들어내지 마.
2. 답변할 때 어떤 사진/이벤트/기억을 참고했는지 명시해.
3. 확실하지 않은 정보는 "~으로 추정됩니다"라고 표시해.
4. 따뜻하고 다정한 톤으로 답변해.
5. 한국어로 답변해.
"""


async def process_chat(query: str, conversation_id: Optional[str] = None) -> dict:
    """채팅 질의 처리

    Flow:
    1. Graph에서 관련 노드 검색
    2. 검색 결과를 컨텍스트로 EXAONE에 전달
    3. 답변 생성 + 소스 연결
    """
    # 대화 세션 관리
    if not conversation_id:
        conversation_id = str(uuid.uuid4())
    if conversation_id not in _conversations:
        _conversations[conversation_id] = []

    # 1. Graph 검색 (키워드 기반)
    search_results = _search_graph(query)
    context_text = _format_search_results(search_results)

    # 2. EXAONE 호출
    messages = _build_messages(query, context_text, conversation_id)
    answer = await _call_exaone(messages)

    # 3. 대화 히스토리 저장
    _conversations[conversation_id].append({"role": "user", "content": query})
    _conversations[conversation_id].append({"role": "assistant", "content": answer})

    # 4. 소스 추출
    sources = _extract_sources(search_results)

    # 5. confidence 결정
    confidence = "confirmed" if sources else "ai_inferred"

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
        "conversation_id": conversation_id,
    }


# 검색어 뒤에서 떼어낼 조사
_PARTICLE_CHARS = "이가을를에서의도는은과와랑"
# 질의에서 떼어낼 문장부호
_PUNCT = "?!.,~\"'()[]"

# 필드별 가중치 - 이름/제목/호칭에서 맞으면 설명·내용보다 강한 신호로 본다
_FIELD_WEIGHTS = (
    ("name", 3),
    ("title", 3),
    ("relation", 3),
    ("address", 2),
    ("description", 1),
    ("content", 1),
    ("scene_description", 1),
)


def _query_terms(query: str) -> list[str]:
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
        token = token.strip(_PUNCT)
        push(token)
        push(token.rstrip(_PARTICLE_CHARS))

    return terms


def _score_node(node: dict, terms: list[str]) -> int:
    """노드가 검색어들과 얼마나 맞는지 점수화

    상위 노드만 LLM 컨텍스트와 소스 뱃지에 실리므로 순위가 곧 답변 품질이 된다.
    """
    score = 0
    for field, weight in _FIELD_WEIGHTS:
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


def _search_graph(query: str) -> list[dict]:
    """Graph에서 질의 관련 노드 검색 (관련도 순)"""
    terms = _query_terms(query)

    # 1. 검색어별로 후보 수집
    candidates: dict[str, dict] = {}
    for term in terms:
        for node in graph_manager.search_nodes(term):
            candidates.setdefault(node["id"], node)

    # 2. 관련도 순 정렬
    ranked = sorted(
        candidates.values(),
        key=lambda node: _score_node(node, terms),
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

    return results[:20]  # 최대 20개


def _format_search_results(results: list[dict]) -> str:
    """검색 결과를 LLM 컨텍스트 텍스트로 변환"""
    if not results:
        return "검색 결과가 없습니다."

    lines = ["[검색 결과]"]
    for i, node in enumerate(results, 1):
        node_type = node.get("node_type", "unknown")

        if node_type == "event":
            lines.append(
                f"{i}. [이벤트] {node.get('title', '')} "
                f"(날짜: {node.get('date_start', '미상')}, "
                f"설명: {node.get('description', '')})"
            )
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
            lines.append(
                f"{i}. [기억] {speaker}: {content}" if speaker
                else f"{i}. [기억] {content}"
            )

    return "\n".join(lines)


def _build_messages(query: str, context: str, conversation_id: str) -> list[dict]:
    """EXAONE API용 메시지 빌드"""
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

    messages.append({"role": "user", "content": user_message})
    return messages


async def _call_exaone(messages: list[dict]) -> str:
    """EXAONE API 호출 (키 없음/실패 시 시뮬레이션 폴백)"""
    answer = await llm_client.complete(messages, max_tokens=1024)
    if answer is None:
        return _simulate_response(messages)
    return answer


def _simulate_response(messages: list[dict]) -> str:
    """EXAONE API 키가 없을 때 시뮬레이션 응답 생성"""
    user_msg = messages[-1]["content"] if messages else ""

    # 검색 결과에서 이벤트/장소 추출
    events = []
    places = []
    persons = []

    for line in user_msg.split("\n"):
        if "[이벤트]" in line:
            events.append(line.split("[이벤트]")[1].strip())
        elif "[장소]" in line:
            places.append(line.split("[장소]")[1].strip())
        elif "[인물]" in line:
            persons.append(line.split("[인물]")[1].strip())

    if events:
        event_info = events[0].split("(")[0].strip()
        answer = f"가족 기록을 확인해보니, {event_info}이(가) 관련 기록으로 있어요."
        if places:
            place_info = places[0].split("(")[0].strip()
            answer += f" 장소는 {place_info}이었네요."
        if persons:
            answer += f" {', '.join([p.split('(')[0].strip() for p in persons[:3]])}이(가) 함께했어요."
        answer += "\n\n더 자세한 이야기가 궁금하시면 물어봐주세요!"
    elif places:
        answer = f"관련 장소로 {places[0].split('(')[0].strip()}에 대한 기록이 있어요."
    else:
        answer = "아직 관련 기록을 찾지 못했어요. 더 많은 사진이나 이야기를 추가하면 더 잘 답변드릴 수 있을 거예요!"

    return answer


# 화면에 띄울 근거 뱃지 개수
MAX_SOURCES = 5


def _extract_sources(search_results: list[dict]) -> list[SourceItem]:
    """검색 결과에서 답변 소스 추출

    상위 5개 노드를 잘라서 걸러면, 뱃지로 만들 수 없는 노드(place 등)가
    상위에 오면 그만큼 근거가 비어 보인다. 뱃지 5개가 모일 때까지 순회한다.
    """
    sources = []
    seen_ids = set()

    for node in search_results:
        if len(sources) >= MAX_SOURCES:
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
                confidence=0.9 if node.get("confidence") == "confirmed" else 0.7,
            ))
        elif node_type == "memory":
            sources.append(SourceItem(
                type="memory",
                id=node_id,
                title=node.get("content", "")[:50],
                confidence=0.85,
            ))
        elif node_type == "person":
            # 나이·관계를 묻는 질문은 인물 기록이 근거다
            sources.append(SourceItem(
                type="person",
                id=node_id,
                title=node.get("name", ""),
                thumbnail=node.get("thumbnail_url"),
                confidence=0.9,
            ))

    return sources
