"""가족 확인 (기획안 STEP 04 — 확인하기)

기획안이 가치 6단계 중 4단계로 규정한 부분이다.

    "가족에게 질문하고 확인·수정·이견을 기록해 신뢰도 확보"
    "충돌을 지우지 않음 — 기억이 다르면 다수결로 삭제하지 않고
     각 버전과 출처를 함께 보존한다"

네 가지 행동을 받는다.
  맞음(confirm)   확인자와 시점을 남긴다
  수정(correct)   값이 틀렸을 때 고친다. 무엇을 무엇으로 바꿨는지와 고친 사람을
                  함께 남긴다. 고친 사람이 그 값을 보증하는 것이므로 확인으로도 센다
  모름(unknown)   확인 불가도 정보다. 다른 사람에게 물어야 한다는 뜻
  이견(dispute)   사실을 덮어쓰지 않는다. 그 사람의 기억을 별도 Memory로
                  남기고 사건을 충돌 상태로 표시한다

수정과 이견은 다르다. 수정은 AI가 잘못 넣은 값을 바로잡는 것이고(날짜가 틀렸다),
이견은 사람마다 다른 기억이다(나는 다르게 기억한다). 앞은 덮어쓰고 뒤는 보존한다.
기획안이 "맞음 / 수정 / 모름"을 나란히 둔 이유가 이 구분이다.

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
from backend.services import visibility
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
    corrected_by = [v["person_id"] for v in verifications if v.get("action") == VerifyAction.CORRECT]
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
    elif confirmed_by or corrected_by:
        # 고친 사람은 고친 값을 보증한 것이다. 여기서 빼면 방금 바로잡은 사건이
        # 확인 목록에 영원히 남는다.
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
        "corrected_by": _names(corrected_by),
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


# 확인 화면에서 고칠 수 있는 값. 여기 없는 필드는 받지 않는다 — 확인 화면이
# 그래프 편집기가 되면 무엇이 원래 근거였는지 알 수 없게 된다.
CORRECTABLE_FIELDS = ("title", "date_start", "description", "location_id")


def _apply_corrections(event: dict, corrections: dict) -> list[dict]:
    """고친 값을 사건에 반영하고 무엇이 바뀌었는지 돌려준다

    장소는 이름을 새로 적는 게 아니라 그래프에 있는 장소를 가리킨다. 새 이름을
    받아 만들면 같은 장소가 둘이 되고 지도에 점이 겹친다.

    Raises:
        ValueError: 고칠 수 없는 필드, 없는 장소, 바뀐 것이 없을 때
    """
    event_id = event["id"]
    changes: list[dict] = []
    updates: dict = {}

    unknown = [key for key in corrections if key not in CORRECTABLE_FIELDS]
    if unknown:
        raise ValueError(
            "고칠 수 없는 항목입니다: "
            + ", ".join(unknown)
            + " (고칠 수 있는 것: "
            + ", ".join(CORRECTABLE_FIELDS)
            + ")"
        )

    for field in CORRECTABLE_FIELDS:
        if field not in corrections:
            continue
        after = corrections[field]
        if isinstance(after, str):
            after = after.strip() or None
        before = event.get(field) or None
        if after == before:
            continue

        if field == "location_id" and after:
            place = graph_manager.get_node(after)
            if not place or place.get("node_type") != NodeType.PLACE:
                raise ValueError("그런 장소가 없습니다: " + str(after))

        updates[field] = after
        changes.append({"field": field, "before": before, "after": after})

    if not changes:
        raise ValueError("바뀐 값이 없습니다.")

    # 장소를 바꿨으면 엣지도 함께 옮긴다. location_id만 고치면 사건 목록과
    # 그래프 화면이 서로 다른 장소를 가리킨다.
    if "location_id" in updates:
        old_place = event.get("location_id")
        if old_place:
            graph_manager.remove_edge(event_id, old_place)
        if updates["location_id"]:
            graph_manager.add_edge(Edge(
                source=event_id,
                target=updates["location_id"],
                relation=RelationType.LOCATED_AT,
            ))

    # 가족이 고친 값은 더 이상 AI 추정이 아니다
    updates["confidence"] = Confidence.CONFIRMED
    updates["source"] = SourceType.USER_INPUT

    graph_manager.update_node(event_id, updates)
    return changes


def record(
    event_id: str,
    person_id: str,
    action: str,
    note: Optional[str] = None,
    corrections: Optional[dict] = None,
) -> Optional[dict]:
    """확인 결과를 기록한다

    Returns:
        {"state": ..., "created_memory_id": ..., "changes": [...]} 또는
        대상이 없으면 None

    Raises:
        ValueError: 수정할 값이 잘못됐을 때 (없는 장소, 빈 수정, 모르는 필드)
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None
    if not graph_manager.get_node(person_id):
        return None
    if action not in {a.value for a in VerifyAction}:
        return None

    changes: list[dict] = []
    if action == VerifyAction.CORRECT:
        changes = _apply_corrections(event, corrections or {})

    entry = {
        "person_id": person_id,
        "action": action,
        "at": datetime.now().isoformat(),
    }
    if note:
        entry["note"] = note
    if changes:
        # 무엇을 무엇으로 바꿨는지 남긴다. 값만 덮어쓰면 되짚을 수 없다.
        entry["changes"] = changes

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

    return {
        "state": get_state(event_id),
        "created_memory_id": created_memory_id,
        "changes": changes,
    }


def list_pending(viewer_id: Optional[str] = None) -> list[dict]:
    """확인이 필요한 사건 목록 (Verification Inbox)

    확인 완료(CONFIRMED)를 뒤로 보내고, 충돌과 미확인을 앞으로 올린다.
    기억 문장은 이 사람이 볼 수 있는 것만 담는다 — 확인 화면이 공개 범위를
    비껴가는 창이 되면 안 된다.
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
        memories = visibility.filter_memories(
            [n for n in connected if n.get("node_type") == NodeType.MEMORY], viewer_id
        )

        # 화면이 수정 폼을 채우려면 지금 값이 필요하다 (제목·날짜·설명·장소)
        place = graph_manager.get_node(event.get("location_id") or "")
        if place and place.get("node_type") != NodeType.PLACE:
            place = None

        items.append({
            "event_id": event["id"],
            "event_title": event.get("title", ""),
            "date_start": event.get("date_start"),
            "description": event.get("description", ""),
            "place": {"id": place["id"], "name": place.get("name", "")} if place else None,
            "state": state["state"],
            "confirmed_by": state["confirmed_by"],
            "corrected_by": state["corrected_by"],
            "disputed_by": state["disputed_by"],
            "unknown_by": state["unknown_by"],
            # 누가 무엇을 언제 고쳤는가 (출처 보존 — 값만 바뀌면 되짚을 수 없다)
            "corrections": [
                {
                    "person_id": v["person_id"],
                    "person_name": (
                        (graph_manager.get_node(v["person_id"]) or {}).get("name")
                        or v["person_id"]
                    ),
                    "at": v.get("at"),
                    "changes": v.get("changes") or [],
                }
                for v in (event.get("verifications") or [])
                if v.get("action") == VerifyAction.CORRECT
            ],
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
