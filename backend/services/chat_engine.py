"""Memory Chat Engine - EXAONE 연동 + Graph RAG"""

from __future__ import annotations

import uuid
import httpx
from typing import Optional

from backend.config import EXAONE_API_URL, EXAONE_API_KEY, EXAONE_MODEL
from backend.services.graph_manager import graph_manager
from backend.models.schemas import SourceItem


# 대화 히스토리 저장 (MVP: in-memory)
_conversations: dict[str, list[dict]] = {}


SYSTEM_PROMPT = """너는 "Family Memory Graph"의 AI 어시스턴트야.
가족의 사진, 영상, 음성, 기억을 연결한 Memory Graph를 기반으로 가족의 질문에 답변해.

규칙:
1. 반드시 제공된 [검색 결과]를 근거로 답변해. 근거 없는 내용은 만들어내지 마.
2. 답변할 때 어떤 사진/이벤트/기억을 참고했는지 명시해.
3. 확실하지 않은 정보는 "~으로 추정됩니다"라고 표시해.
4. 따뜻하고 가족적인 톤으로 답변해.
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


def _search_graph(query: str) -> list[dict]:
    """Graph에서 질의 관련 노드 검색"""
    results = []

    # 텍스트 검색
    text_results = graph_manager.search_nodes(query)
    results.extend(text_results)

    # 키워드 분리 후 개별 검색 (간단한 토크나이징)
    keywords = [w for w in query.split() if len(w) >= 2]
    for keyword in keywords:
        # 조사 제거 (간단)
        clean = keyword.rstrip("이가을를에서의도는은")
        if clean and len(clean) >= 2 and clean != keyword:
            more = graph_manager.search_nodes(clean)
            for item in more:
                if item not in results:
                    results.append(item)

    # 결과에 연결된 노드도 포함 (1-hop)
    expanded = list(results)
    for node in results[:5]:  # 상위 5개만 확장
        connected = graph_manager.get_connected_nodes(node["id"])
        for c in connected[:3]:
            if c not in expanded:
                expanded.append(c)

    return expanded[:20]  # 최대 20개


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
            lines.append(
                f"{i}. [인물] {node.get('name', '')} "
                f"(관계: {node.get('relation', '')})"
            )
        elif node_type == "place":
            lines.append(
                f"{i}. [장소] {node.get('name', '')} "
                f"(주소: {node.get('address', '')})"
            )
        elif node_type == "media":
            lines.append(
                f"{i}. [미디어] {node.get('original_filename', '')} "
                f"(날짜: {node.get('exif_date', node.get('created_at', ''))}, "
                f"타입: {node.get('media_type', '')})"
            )
        elif node_type == "memory":
            lines.append(
                f"{i}. [기억] {node.get('content', '')}"
            )

    return "\n".join(lines)


def _build_messages(query: str, context: str, conversation_id: str) -> list[dict]:
    """EXAONE API용 메시지 빌드"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

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
    """EXAONE API 호출"""
    if not EXAONE_API_KEY:
        # API 키 없으면 시뮬레이션 응답
        return _simulate_response(messages)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                EXAONE_API_URL,
                headers={
                    "Authorization": f"Bearer {EXAONE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": EXAONE_MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        # API 실패 시 시뮬레이션 폴백
        return _simulate_response(messages)


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


def _extract_sources(search_results: list[dict]) -> list[SourceItem]:
    """검색 결과에서 답변 소스 추출"""
    sources = []
    seen_ids = set()

    for node in search_results[:5]:  # 최대 5개 소스
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

    return sources
