"""Memory Gap Detector - 그래프의 빈칸·불일치 탐지"""

from __future__ import annotations

import uuid
from typing import Optional

from backend.models.graph_models import NodeType, RelationType
from backend.services.graph_manager import graph_manager


def detect_gaps() -> list[dict]:
    """Memory Graph에서 Gap 탐지

    Gap 유형:
    1. missing_date: 이벤트에 날짜 없음
    2. missing_place: 이벤트에 장소 없음
    3. missing_description: 이벤트에 설명 없음
    4. no_media: 이벤트에 연결된 미디어 없음
    5. single_perspective: 참여자가 여럿인데 한 명의 기억만 있음
    6. no_participants: 이벤트에 참여자 연결 없음
    """
    gaps = []
    events = graph_manager.get_events()

    for event in events:
        event_id = event["id"]
        event_title = event.get("title", "알 수 없는 이벤트")

        # 연결된 노드 파악
        connected = graph_manager.get_connected_nodes(event_id)
        media_nodes = [n for n in connected if n.get("node_type") == NodeType.MEDIA]
        person_nodes = [n for n in connected if n.get("node_type") == NodeType.PERSON]
        memory_nodes = [n for n in connected if n.get("node_type") == NodeType.MEMORY]
        place_nodes = [n for n in connected if n.get("node_type") == NodeType.PLACE]

        # 1. 날짜 없음
        if not event.get("date_start"):
            gaps.append(_create_gap(
                event_id=event_id,
                event_title=event_title,
                gap_type="missing_date",
                description=f"'{event_title}'의 날짜 정보가 없습니다.",
                suggested_question=f"'{event_title}'이(가) 언제쯤이었는지 기억나시나요?",
                priority=3,
            ))

        # 2. 장소 없음
        if not place_nodes and not event.get("location_id"):
            gaps.append(_create_gap(
                event_id=event_id,
                event_title=event_title,
                gap_type="missing_place",
                description=f"'{event_title}'의 장소 정보가 없습니다.",
                suggested_question=f"'{event_title}' 때 어디에 있었나요?",
                priority=3,
            ))

        # 3. 설명 없음
        if not event.get("description") or event.get("description") == "자동 생성된 이벤트":
            gaps.append(_create_gap(
                event_id=event_id,
                event_title=event_title,
                gap_type="missing_description",
                description=f"'{event_title}'에 대한 설명이 없습니다.",
                suggested_question=f"'{event_title}' 때 어떤 일이 있었나요?",
                priority=2,
            ))

        # 4. 미디어 없음
        if not media_nodes:
            gaps.append(_create_gap(
                event_id=event_id,
                event_title=event_title,
                gap_type="no_media",
                description=f"'{event_title}'에 연결된 사진이나 영상이 없습니다.",
                suggested_question=f"'{event_title}' 관련 사진이나 영상이 있나요?",
                priority=2,
            ))

        # 5. 참여자 없음
        if not person_nodes:
            gaps.append(_create_gap(
                event_id=event_id,
                event_title=event_title,
                gap_type="no_participants",
                description=f"'{event_title}'에 누가 참여했는지 기록이 없습니다.",
                suggested_question=f"'{event_title}' 때 누가 함께했나요?",
                priority=3,
            ))

        # 6. 한쪽 관점만 있음 (참여자 2명 이상, 기억 1개 이하)
        if len(person_nodes) >= 2 and len(memory_nodes) <= 1:
            # 기억이 없는 참여자 찾기
            memory_contributors = set()
            for mem in memory_nodes:
                contributor = mem.get("contributor_id")
                if contributor:
                    memory_contributors.add(contributor)

            missing_persons = [
                p for p in person_nodes
                if p["id"] not in memory_contributors
            ]

            if missing_persons:
                target_person = missing_persons[0]
                gaps.append(_create_gap(
                    event_id=event_id,
                    event_title=event_title,
                    gap_type="single_perspective",
                    description=f"'{event_title}'에 대해 {target_person.get('name', '')}의 기억이 없습니다.",
                    suggested_question=f"{target_person.get('name', '')}님, '{event_title}' 때 어떤 기억이 있으세요?",
                    target_person=target_person.get("name"),
                    target_person_id=target_person.get("id"),
                    priority=4,
                ))

    # 우선순위 높은 순으로 정렬
    gaps.sort(key=lambda g: g["priority"], reverse=True)
    return gaps


def get_gap_detail(gap_id: str) -> Optional[dict]:
    """특정 Gap 상세 정보 (Gap은 동적 생성이므로 재탐지)"""
    all_gaps = detect_gaps()
    for gap in all_gaps:
        if gap["id"] == gap_id:
            return gap
    return None


def _create_gap(
    event_id: str,
    event_title: str,
    gap_type: str,
    description: str,
    suggested_question: str,
    target_person: Optional[str] = None,
    target_person_id: Optional[str] = None,
    priority: int = 1,
) -> dict:
    """Gap 아이템 생성"""
    # 결정적 ID 생성 (같은 gap은 같은 ID)
    gap_id = f"gap_{event_id}_{gap_type}"

    return {
        "id": gap_id,
        "event_id": event_id,
        "event_title": event_title,
        "gap_type": gap_type,
        "description": description,
        "suggested_question": suggested_question,
        "target_person": target_person,
        # 인터뷰가 수집한 기억을 이 인물에게 귀속시키기 위해 id도 함께 넘긴다
        "target_person_id": target_person_id,
        "priority": priority,
    }
