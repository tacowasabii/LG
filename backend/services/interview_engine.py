"""AI Memory Interview Engine - 기억의 빈 곳을 질문하며 새로운 기록 수집"""

from __future__ import annotations

import uuid
from typing import Optional

from backend.services import llm_client
from backend.models.graph_models import (
    MemoryNode, Edge, RelationType, SourceType, Confidence, NodeType,
)
from backend.services.graph_manager import graph_manager
from backend.services.gap_detector import detect_gaps


# 인터뷰 세션 저장 (MVP: in-memory)
_sessions: dict[str, dict] = {}


INTERVIEW_SYSTEM_PROMPT = """너는 사람들의 기억을 수집하는 따뜻한 인터뷰어야.
사진, 이벤트, 기억에 대해 자연스럽게 질문해서 빠진 정보를 채워나가.
인터뷰 대상은 가족일 수도 있고 친구·연인일 수도 있다. 주어진 관계에 맞는 호칭을 써.

규칙:
1. 한 번에 하나의 질문만 해.
2. 질문은 구체적이고 답하기 쉬워야 해.
3. 따뜻하고 대화하듯 자연스러운 톤으로 질문해.
4. 답변에서 구조화할 수 있는 정보(날짜, 장소, 인물, 에피소드)를 추출해.
5. 3~5개 질문 후 자연스럽게 마무리해.
6. 한국어로 질문해.
"""


async def start_interview(target_type: str = "auto", target_id: Optional[str] = None) -> dict:
    """인터뷰 세션 시작

    target_type: "event" | "media" | "auto"
    - auto: Gap이 있는 이벤트를 자동 선택
    """
    session_id = str(uuid.uuid4())

    # 타겟 결정
    target_node = None
    # 수집한 기억을 누구의 것으로 기록할지. Gap이 "기억이 없는 참여자"를 이미 지목한다.
    contributor_id = None
    contributor_name = None

    if target_id:
        target_node = graph_manager.get_node(target_id)

    if not target_node and target_type == "auto":
        # Gap이 있는 이벤트 자동 선택
        gaps = detect_gaps()
        if gaps:
            gap = gaps[0]
            if gap.get("event_id"):
                target_node = graph_manager.get_node(gap["event_id"])
            contributor_id = gap.get("target_person_id")
            contributor_name = gap.get("target_person")

    # 타겟 정보 구성
    context = _build_interview_context(target_node, contributor_name)

    # 첫 질문 생성
    first_question = await _generate_question(context, [])

    # 세션 저장
    _sessions[session_id] = {
        "target_node": target_node,
        "context": context,
        "contributor_id": contributor_id,
        "contributor_name": contributor_name,
        "questions": [first_question],
        "answers": [],
        "updated_nodes": [],
        "question_count": 1,
        "max_questions": 5,
    }

    return {
        "session_id": session_id,
        "question": first_question,
        "context": {
            "target_type": target_node.get("node_type") if target_node else None,
            "target_id": target_node.get("id") if target_node else None,
            "target_title": target_node.get("title", target_node.get("name", "")) if target_node else None,
            "contributor_name": contributor_name,
        },
    }


async def process_answer(session_id: str, answer: str) -> dict:
    """사용자 답변 처리 → Graph 업데이트 + 다음 질문 생성"""
    session = _sessions.get(session_id)
    if not session:
        return {
            "session_id": session_id,
            "next_question": None,
            "is_complete": True,
            "updated_nodes": [],
            "message": "세션을 찾을 수 없습니다.",
        }

    # 답변 저장
    session["answers"].append(answer)

    # 답변에서 정보 추출 → Memory 노드 생성
    updated_nodes = await _process_answer_to_graph(session, answer)
    session["updated_nodes"].extend(updated_nodes)

    # 종료 조건 확인
    is_complete = session["question_count"] >= session["max_questions"]

    next_question = None
    if not is_complete:
        # 다음 질문 생성
        next_question = await _generate_question(session["context"], session["answers"])
        session["questions"].append(next_question)
        session["question_count"] += 1

    return {
        "session_id": session_id,
        "next_question": next_question,
        "is_complete": is_complete,
        "updated_nodes": updated_nodes,
        "message": "감사합니다! 소중한 기억이 기록되었어요." if is_complete else "",
    }


def get_session_status(session_id: str) -> Optional[dict]:
    """인터뷰 세션 상태 조회"""
    session = _sessions.get(session_id)
    if not session:
        return None
    return {
        "session_id": session_id,
        "question_count": session["question_count"],
        "max_questions": session["max_questions"],
        "is_complete": session["question_count"] >= session["max_questions"],
        "updated_nodes": session["updated_nodes"],
    }


def _build_interview_context(target_node: Optional[dict], contributor_name: Optional[str] = None) -> str:
    """인터뷰 컨텍스트 구성"""
    if not target_node:
        return "가족의 기억에 대해 전반적으로 질문합니다."

    node_type = target_node.get("node_type", "")
    lines = []

    if contributor_name:
        # 질문이 특정 가족을 향하게 한다 (그 사람의 기억이 빠져 있어서 인터뷰 대상이 됐다)
        lines.append(f"인터뷰 대상: {contributor_name} (이 사람의 기억이 아직 기록되지 않았습니다)")

    if node_type == "event":
        lines.append(f"이벤트: {target_node.get('title', '')}")
        lines.append(f"날짜: {target_node.get('date_start', '미상')}")
        lines.append(f"설명: {target_node.get('description', '없음')}")

        # 참여자 정보
        connected = graph_manager.get_connected_nodes(target_node["id"])
        persons = [n for n in connected if n.get("node_type") == "person"]
        if persons:
            lines.append(f"참여자: {', '.join(p.get('name', '') for p in persons)}")

        # 기존 기억
        memories = [n for n in connected if n.get("node_type") == "memory"]
        if memories:
            lines.append("기존 기억:")
            for m in memories[:3]:
                lines.append(f"  - {m.get('content', '')[:100]}")

    elif node_type == "media":
        lines.append(f"미디어: {target_node.get('original_filename', '')}")
        lines.append(f"날짜: {target_node.get('exif_date', '미상')}")
        lines.append(f"타입: {target_node.get('media_type', '')}")

    return "\n".join(lines)


async def _generate_question(context: str, previous_answers: list[str]) -> str:
    """EXAONE으로 인터뷰 질문 생성"""
    messages = [{"role": "system", "content": INTERVIEW_SYSTEM_PROMPT}]

    user_content = f"""[인터뷰 대상 정보]
{context}

[이전 답변들]
{chr(10).join(f'- {a}' for a in previous_answers) if previous_answers else '(첫 질문입니다)'}

위 정보를 바탕으로 가족에게 할 다음 질문 하나를 생성해주세요.
빠진 정보(날짜, 장소, 함께한 사람, 그때의 감정이나 에피소드)를 채울 수 있는 질문이면 좋겠습니다."""

    messages.append({"role": "user", "content": user_content})

    question = await llm_client.complete(messages, max_tokens=256)
    if question is None:
        return _simulate_question(context, previous_answers)
    return question


def _simulate_question(context: str, previous_answers: list[str]) -> str:
    """EXAONE 없을 때 시뮬레이션 질문"""
    question_pool = [
        "이 사진이 찍힌 날, 어떤 일이 있었는지 기억나세요?",
        "그때 함께 있었던 가족이 누구였나요? 특별히 기억나는 순간이 있나요?",
        "이 장소에서의 추억 중 가장 먼저 떠오르는 것은 무엇인가요?",
        "그날의 날씨나 분위기가 기억나시나요?",
        "이 사진을 보면 어떤 감정이 떠오르나요? 그때의 기분은 어땠나요?",
    ]

    idx = len(previous_answers) % len(question_pool)
    return question_pool[idx]


async def _process_answer_to_graph(session: dict, answer: str) -> list[str]:
    """답변을 구조화하여 Graph에 저장

    같은 사건에 대한 가족별 기억을 따로 보존하려면 "누가 말했는지"가 남아야 한다.
    contributor_id와 REMEMBERS 엣지가 없으면 Gap 탐지도 "아직 기억을 남기지
    않은 참여자"를 찾을 수 없다.
    """
    updated_nodes = []
    contributor_id = session.get("contributor_id")

    # Memory 노드 생성
    memory = MemoryNode(
        content=answer,
        source_type=SourceType.INTERVIEW,
        contributor_id=contributor_id,
        confidence=Confidence.CONFIRMED,
    )
    graph_manager.add_memory(memory)
    updated_nodes.append(memory.id)

    # 타겟 이벤트가 있으면 연결
    target = session.get("target_node")
    if target and target.get("node_type") == "event":
        edge = Edge(
            source=memory.id,
            target=target["id"],
            relation=RelationType.ABOUT,
        )
        graph_manager.add_edge(edge)

    # 화자 → 기억 (REMEMBERS)
    if contributor_id and graph_manager.get_node(contributor_id):
        graph_manager.add_edge(Edge(
            source=contributor_id,
            target=memory.id,
            relation=RelationType.REMEMBERS,
        ))

    return updated_nodes
