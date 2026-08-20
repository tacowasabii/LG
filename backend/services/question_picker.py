"""무엇을 물어볼지 고른다 (AI 인터뷰의 과녁)

예전에는 `gap_detector`가 이 일을 했다. 그 모듈은 두 가지를 겸했다 —
(1) 인터뷰가 물어볼 대상을 고르는 일, (2) "해결해야 할 Memory Gap" 목록을
사용자에게 보여주는 일.

(2)를 없앴다. 빈칸을 과제 목록으로 보여주면 가족은 기록을 남기러 온 자리에서
할 일을 받아 간다. 채워지지 않은 기억은 결함이 아니다.

(1)은 남는다. 인터뷰는 무언가를 물어야 하고, 아무 사건이나 고르면 이미 잘
채워진 기억을 또 묻는다. 그래서 여기서는 목록을 만들지 않고 **하나**만 고른다.
화면에도 API에도 노출되지 않는다.
"""

from __future__ import annotations

from typing import Optional

from backend.models.graph_models import NodeType
from backend.services.graph_manager import graph_manager


def pick_target() -> dict:
    """지금 물어보기 가장 좋은 사건 하나

    Returns:
        {"event": dict|None, "person_id": str|None, "person_name": str|None,
         "missing": ["날짜", ...]}

        사건이 하나도 없으면 event가 None이다 (인터뷰는 그때 일반 질문을 한다).
    """
    best: Optional[dict] = None
    best_score = -1

    for event in graph_manager.get_events():
        connected = graph_manager.get_connected_nodes(event["id"])
        persons = [n for n in connected if n.get("node_type") == NodeType.PERSON]
        memories = [n for n in connected if n.get("node_type") == NodeType.MEMORY]
        media = [n for n in connected if n.get("node_type") == NodeType.MEDIA]

        missing = []
        score = 0

        if not event.get("date_start"):
            missing.append("날짜")
            score += 3
        if not event.get("location_id"):
            missing.append("장소")
            score += 3
        if not (event.get("description") or "").strip():
            missing.append("어떤 일이었는지")
            score += 2
        if not media:
            missing.append("사진")
            score += 1

        # 함께 있던 사람 중 아직 기억을 남기지 않은 사람. 그 사람에게 물으면
        # 새로운 관점이 하나 늘어난다 (사건을 완성하려는 것이 아니다).
        told = {m.get("contributor_id") for m in memories if m.get("contributor_id")}
        silent = [p for p in persons if p["id"] not in told]
        if silent and len(persons) >= 2:
            score += 4

        if score > best_score:
            best_score = score
            best = {
                "event": event,
                "person_id": silent[0]["id"] if silent else None,
                "person_name": silent[0].get("name") if silent else None,
                "missing": missing,
            }

    return best or {"event": None, "person_id": None, "person_name": None, "missing": []}
