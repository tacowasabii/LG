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


def pick_target(speaker_id: Optional[str] = None) -> dict:
    """지금 물어보기 가장 좋은 사건 하나

    speaker_id  지금 화면 앞에서 답할 사람. 인터뷰는 이 사람의 기억을 받아 적는
                자리이므로, 물어볼 사건도 이 사람이 함께 있었던 것에서 고른다.

                이 인자가 없던 동안 여기서 고른 인물(기억을 남기지 않은 참여자)이
                그대로 "인터뷰 대상"이 됐다. 아빠로 로그인한 사람에게 화면이
                "서연님, 그때 기억나세요?"라고 물었다 — 답하는 사람과 질문받는
                사람이 어긋났고, 그러면 답변의 주인이 누구인지도 흐려진다.

    Returns:
        {"event": dict|None, "person_id": str|None, "person_name": str|None,
         "missing": ["날짜", ...]}

        사건이 하나도 없으면 event가 None이다 (인터뷰는 그때 일반 질문을 한다).
    """
    speaker = graph_manager.get_node(speaker_id) if speaker_id else None
    if speaker and speaker.get("node_type") != NodeType.PERSON:
        speaker = None

    if speaker:
        # 그 사람이 함께 있었던 사건 먼저. 없던 자리를 물으면 남는 것은 기억이
        # 아니라 추측이다.
        return (
            _best_event(speaker, only_present=True)
            or _best_event(speaker, only_present=False)
            or _empty_target()
        )

    return _best_event(None, only_present=False) or _empty_target()


def _empty_target() -> dict:
    return {"event": None, "person_id": None, "person_name": None, "missing": []}


def _best_event(speaker: Optional[dict], only_present: bool) -> Optional[dict]:
    """빈 곳이 가장 많은 사건 하나 (없으면 None)"""
    best: Optional[dict] = None
    best_score = -1

    for event in graph_manager.get_events():
        connected = graph_manager.get_connected_nodes(event["id"])
        persons = [n for n in connected if n.get("node_type") == NodeType.PERSON]
        memories = [n for n in connected if n.get("node_type") == NodeType.MEMORY]
        media = [n for n in connected if n.get("node_type") == NodeType.MEDIA]

        if only_present and speaker and speaker["id"] not in {p["id"] for p in persons}:
            continue

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

        # 아직 기억을 남기지 않은 사람에게 물으면 새로운 관점이 하나 늘어난다
        # (사건을 완성하려는 것이 아니다).
        told = {m.get("contributor_id") for m in memories if m.get("contributor_id")}

        if speaker:
            # 답할 사람이 정해져 있다. 인터뷰 대상은 그 사람이고, 그 사람이 아직
            # 말하지 않은 사건일 때 물어볼 값이 커진다.
            if speaker["id"] not in told:
                score += 4
            person_id = speaker["id"]
            person_name = speaker.get("name")
        else:
            silent = [p for p in persons if p["id"] not in told]
            if silent and len(persons) >= 2:
                score += 4
            person_id = silent[0]["id"] if silent else None
            person_name = silent[0].get("name") if silent else None

        if score > best_score:
            best_score = score
            best = {
                "event": event,
                "person_id": person_id,
                "person_name": person_name,
                "missing": missing,
            }

    return best
