"""가족 확인 (기획안 STEP 04 — 확인하기)

기획안이 가치 6단계 중 4단계로 규정한 부분이다.

    "가족에게 질문하고 확인·수정·이견을 기록해 신뢰도 확보"
    "충돌을 지우지 않음 — 기억이 다르면 다수결로 삭제하지 않고
     각 버전과 출처를 함께 보존한다"

세 가지 행동을 받는다.
  맞음(confirm)   확인자와 시점을 남긴다
  모름(unknown)   확인 불가도 정보다. 다른 사람에게 물어야 한다는 뜻
  이견(dispute)   사실을 덮어쓰지 않는다. 그 사람의 기억을 별도 Memory로
                  남기고 사건을 충돌 상태로 표시한다

확인 상태는 저장하지 않고 verifications와 기억에서 파생한다. 저장하면
기억이 추가돼도 상태가 갱신되지 않아 어긋난다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from backend.models.graph_models import (
    Confidence,
    Edge,
    MemoryNode,
    NodeType,
    RelationType,
    SourceType,
    VerificationState,
    VerifyAction,
)
from backend.services.graph_manager import graph_manager


def get_state(event_id: str) -> Optional[dict]:
    """사건의 확인 상태와 근거를 파생해서 돌려준다

    4단계는 기획안의 CONFIRMED / SUPPORTED / INFERRED / CONFLICTED다.
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    verifications = event.get("verifications") or []
    confirmed_by = [v["person_id"] for v in verifications if v.get("action") == VerifyAction.CONFIRM]
    disputed_by = [v["person_id"] for v in verifications if v.get("action") == VerifyAction.DISPUTE]
    unknown_by = [v["person_id"] for v in verifications if v.get("action") == VerifyAction.UNKNOWN]

    # 이 사건에 대한 기억을 남긴 사람들 (다중 근거 판정에 쓴다)
    contributors = {
        node.get("contributor_id")
        for node in graph_manager.get_connected_nodes(event_id)
        if node.get("node_type") == NodeType.MEMORY and node.get("contributor_id")
    }

    if disputed_by:
        # 충돌은 다수결로 지우지 않는다. 확인이 더 많아도 충돌 상태를 유지한다.
        state = VerificationState.CONFLICTED
    elif confirmed_by:
        state = VerificationState.CONFIRMED
    elif len(contributors) >= 2:
        state = VerificationState.SUPPORTED
    else:
        state = VerificationState.INFERRED

    return {
        # 열거형 대신 값을 내보낸다. f-string에 열거형을 넣으면
        # "VerificationState.CONFLICTED" 같은 repr이 프롬프트로 새어 들어간다.
        "state": state.value,
        "confirmed_by": _names(confirmed_by),
        "disputed_by": _names(disputed_by),
        "unknown_by": _names(unknown_by),
        "memory_contributors": _names(sorted(contributors)),
        "verifications": verifications,
    }


def _names(person_ids: list[str]) -> list[dict]:
    """person_id 목록을 이름과 함께 돌려준다 (화면에서 그대로 쓴다)"""
    result = []
    for person_id in person_ids:
        person = graph_manager.get_node(person_id)
        result.append({
            "id": person_id,
            "name": person.get("name", person_id) if person else person_id,
        })
    return result


def record(
    event_id: str,
    person_id: str,
    action: str,
    note: Optional[str] = None,
) -> Optional[dict]:
    """확인 결과를 기록한다

    Returns:
        {"state": ..., "created_memory_id": ...} 또는 대상이 없으면 None
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None
    if not graph_manager.get_node(person_id):
        return None
    if action not in {a.value for a in VerifyAction}:
        return None

    entry = {
        "person_id": person_id,
        "action": action,
        "at": datetime.now().isoformat(),
    }
    if note:
        entry["note"] = note

    # 같은 사람의 이전 확인은 새 것으로 대체한다 (마음이 바뀔 수 있다).
    # 다만 이력을 지우는 게 아니라 그 사람의 최신 판단만 남긴다.
    verifications = [
        v for v in (event.get("verifications") or [])
        if v.get("person_id") != person_id
    ]
    verifications.append(entry)
    graph_manager.update_node(event_id, {"verifications": verifications})

    created_memory_id = None
    if action == VerifyAction.DISPUTE and note:
        # 이견은 사실을 덮어쓰지 않는다. 그 사람의 버전을 별도 기억으로 보존한다.
        memory = MemoryNode(
            content=note,
            source_type=SourceType.INTERVIEW,
            contributor_id=person_id,
            confidence=Confidence.CONFIRMED,
        )
        graph_manager.add_memory(memory)
        graph_manager.add_edge(Edge(
            source=memory.id, target=event_id, relation=RelationType.ABOUT,
        ))
        graph_manager.add_edge(Edge(
            source=person_id, target=memory.id, relation=RelationType.REMEMBERS,
        ))
        created_memory_id = memory.id

    return {"state": get_state(event_id), "created_memory_id": created_memory_id}


def list_pending() -> list[dict]:
    """확인이 필요한 사건 목록 (Verification Inbox)

    확인 완료(CONFIRMED)를 뒤로 보내고, 충돌과 미확인을 앞으로 올린다.
    """
    order = {
        VerificationState.CONFLICTED.value: 0,
        VerificationState.INFERRED.value: 1,
        VerificationState.SUPPORTED.value: 2,
        VerificationState.CONFIRMED.value: 3,
    }

    items = []
    for event in graph_manager.get_events():
        state = get_state(event["id"])
        if not state:
            continue

        connected = graph_manager.get_connected_nodes(event["id"])
        participants = [n for n in connected if n.get("node_type") == NodeType.PERSON]
        memories = [n for n in connected if n.get("node_type") == NodeType.MEMORY]

        items.append({
            "event_id": event["id"],
            "event_title": event.get("title", ""),
            "date_start": event.get("date_start"),
            "state": state["state"],
            "confirmed_by": state["confirmed_by"],
            "disputed_by": state["disputed_by"],
            "unknown_by": state["unknown_by"],
            "participants": [
                {"id": p["id"], "name": p.get("name", ""), "relation": p.get("relation", "")}
                for p in participants
            ],
            "memories": [
                {
                    "id": m["id"],
                    "content": m.get("content", ""),
                    "contributor_id": m.get("contributor_id"),
                    "contributor_name": (
                        (graph_manager.get_node(m["contributor_id"]) or {}).get("name")
                        if m.get("contributor_id") else None
                    ),
                }
                for m in memories
            ],
        })

    items.sort(key=lambda i: (order.get(i["state"], 9), i.get("date_start") or ""))
    return items
