"""가족 확인(STEP 04) 회귀 테스트

    python tests/test_verification.py

그래프를 실제로 변경하므로, 테스트가 끝나면 자기가 만든 확인 이력과 기억을
지워 원래 상태로 되돌린다. 데모 데이터를 더럽히지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import (  # noqa: E402
    NodeType,
    VerificationState,
    VerifyAction,
)
from backend.services import verification  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행 (시드에 김민수의 기억 M001이 하나 붙어 있다)


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _reset(event_id=EVENT):
    """이 테스트가 만든 확인 이력과 기억을 지운다"""
    graph_manager.update_node(event_id, {"verifications": []})
    for node in list(graph_manager.get_memories()):
        # 시드 기억은 M001~M008. 그 밖의 memory_* 는 테스트가 만든 것이다.
        if node["id"].startswith("memory_"):
            graph_manager.delete_node(node["id"])


def test_initial_state_is_inferred():
    """확인 이력이 없으면 '확인 필요'다 (Inbox에 할 일이 있는 상태)"""
    _require_seeded_graph()
    _reset()
    state = verification.get_state(EVENT)
    assert state["state"] == VerificationState.INFERRED.value, state["state"]
    assert state["confirmed_by"] == []


def test_confirm_records_who_and_when():
    """맞음은 확인자와 확인 시점을 남긴다 (기획안: 확인자와 확인 시점 기록)"""
    _require_seeded_graph()
    _reset()
    result = verification.record(EVENT, "P01", VerifyAction.CONFIRM.value)
    state = result["state"]

    assert state["state"] == VerificationState.CONFIRMED.value
    assert [p["name"] for p in state["confirmed_by"]] == ["김민수"]
    entry = state["verifications"][0]
    assert entry["person_id"] == "P01"
    assert entry["at"], "확인 시점이 없다"
    _reset()


def test_unknown_is_recorded_but_not_confirmation():
    """모름도 정보다. 다만 확인으로 세지 않는다"""
    _require_seeded_graph()
    _reset()
    state = verification.record(EVENT, "P04", VerifyAction.UNKNOWN.value)["state"]
    assert state["state"] == VerificationState.INFERRED.value, "모름이 확인으로 셈"
    assert [p["name"] for p in state["unknown_by"]] == ["김지우"]
    _reset()


def test_dispute_preserves_both_versions():
    """이견은 기존 기록을 덮어쓰지 않고 그 사람의 기억으로 함께 보존한다

    기획안: "기억이 다르면 다수결로 삭제하지 않고 각 버전과 출처를 함께 보존"
    """
    _require_seeded_graph()
    _reset()

    before = {m["id"] for m in graph_manager.get_connected_nodes(EVENT)
              if m.get("node_type") == NodeType.MEMORY}
    assert before, "시드 기억이 없으면 이 테스트가 무의미하다"

    note = "캠코더는 여행 다녀와서 산 것으로 기억해요."
    result = verification.record(EVENT, "P02", VerifyAction.DISPUTE.value, note)

    # 기존 기억이 그대로 남아 있다
    after = {m["id"]: m for m in graph_manager.get_connected_nodes(EVENT)
             if m.get("node_type") == NodeType.MEMORY}
    assert before <= set(after), f"기존 기억이 사라졌다: {before - set(after)}"

    # 이견이 새 기억으로 보존되고 화자가 붙었다
    new_id = result["created_memory_id"]
    assert new_id, "이견 기억이 생성되지 않았다"
    assert new_id in after
    assert after[new_id]["content"] == note
    assert after[new_id]["contributor_id"] == "P02"

    # 화자 -> 기억 엣지도 생겼다
    remembers = [
        e for e in graph_manager.get_all_edges()
        if e["source"] == "P02" and e["target"] == new_id and e["relation"] == "remembers"
    ]
    assert remembers, "REMEMBERS 엣지가 없다"
    _reset()


def test_conflict_survives_majority():
    """충돌은 다수결로 지워지지 않는다

    기획안: "다수결로 삭제하지 않고" — 확인이 더 많아도 충돌 상태를 유지한다.
    """
    _require_seeded_graph()
    _reset()

    verification.record(EVENT, "P02", VerifyAction.DISPUTE.value, "제 기억은 달라요.")
    for person_id in ("P01", "P03", "P04"):
        verification.record(EVENT, person_id, VerifyAction.CONFIRM.value)

    state = verification.get_state(EVENT)
    assert state["state"] == VerificationState.CONFLICTED.value, (
        f"확인 3명 대 이견 1명인데 {state['state']} 로 정리됨 - 다수결로 충돌을 지웠다"
    )
    assert len(state["confirmed_by"]) == 3
    assert len(state["disputed_by"]) == 1
    _reset()


def test_supported_when_multiple_contributors():
    """확인이 없어도 두 사람 이상의 기억이 있으면 '다중 근거'다"""
    _require_seeded_graph()
    _reset()

    # 확인 없이 다른 사람의 기억만 추가한다 (dispute가 기억을 만들어준다)
    verification.record(EVENT, "P02", VerifyAction.DISPUTE.value, "저는 이렇게 기억해요.")
    # 충돌 표시를 지우고 기억만 남긴 상태를 만든다
    graph_manager.update_node(EVENT, {"verifications": []})

    state = verification.get_state(EVENT)
    assert state["state"] == VerificationState.SUPPORTED.value, (
        f"기여자 2명인데 {state['state']}. 기여자={[p['name'] for p in state['memory_contributors']]}"
    )
    _reset()


def test_same_person_verification_is_replaced():
    """같은 사람이 다시 판정하면 최신 판단만 남는다"""
    _require_seeded_graph()
    _reset()
    verification.record(EVENT, "P01", VerifyAction.UNKNOWN.value)
    state = verification.record(EVENT, "P01", VerifyAction.CONFIRM.value)["state"]

    assert len(state["verifications"]) == 1, f"이력이 중복됨: {state['verifications']}"
    assert state["state"] == VerificationState.CONFIRMED.value
    assert state["unknown_by"] == []
    _reset()


def test_invalid_input_is_rejected():
    """없는 대상이나 잘못된 행동은 기록하지 않는다"""
    _require_seeded_graph()
    assert verification.record("NO_SUCH_EVENT", "P01", "confirm") is None
    assert verification.record(EVENT, "NO_SUCH_PERSON", "confirm") is None
    assert verification.record(EVENT, "P01", "shrug") is None
    assert verification.get_state("P01") is None, "인물 노드를 이벤트로 취급했다"


def test_inbox_puts_conflicts_first():
    """Inbox는 충돌을 맨 앞에, 확인 완료를 맨 뒤에 놓는다"""
    _require_seeded_graph()
    _reset()

    verification.record("E02", "P02", VerifyAction.DISPUTE.value, "제 기억은 달라요.")
    verification.record("E03", "P01", VerifyAction.CONFIRM.value)

    items = verification.list_pending()
    states = [i["state"] for i in items]
    assert states[0] == VerificationState.CONFLICTED.value, f"충돌이 맨 앞이 아님: {states}"
    assert states[-1] == VerificationState.CONFIRMED.value, f"확인 완료가 맨 뒤가 아님: {states}"

    graph_manager.update_node("E02", {"verifications": []})
    graph_manager.update_node("E03", {"verifications": []})
    _reset()


# --- 수정(correct) — 기획안의 "맞음 / 수정 / 모름" 중 가운데 ------------------


def _snapshot(event_id=EVENT):
    """수정 테스트가 건드리는 값만 떠 둔다"""
    event = graph_manager.get_node(event_id)
    return {
        key: event.get(key)
        for key in ("title", "date_start", "description", "location_id", "confidence", "source")
    }


def _restore_event(snapshot, event_id=EVENT):
    graph_manager.update_node(event_id, snapshot)


def test_correct_overwrites_value_and_records_who():
    """수정은 값을 덮어쓰고, 누가 무엇을 무엇으로 바꿨는지 남긴다"""
    _require_seeded_graph()
    _reset()
    before = _snapshot()
    try:
        result = verification.record(
            EVENT, "P01", VerifyAction.CORRECT.value,
            corrections={"title": "1998 부산 여행(고침)", "date_start": "1998-08-02"},
        )
        assert result is not None

        event = graph_manager.get_node(EVENT)
        assert event["title"] == "1998 부산 여행(고침)", event["title"]
        assert event["date_start"] == "1998-08-02", event["date_start"]

        # 고친 값은 더 이상 AI 추정이 아니다
        assert event["confidence"] == "confirmed", event["confidence"]
        assert event["source"] == "user_input", event["source"]

        fields = {c["field"]: c for c in result["changes"]}
        assert fields["title"]["before"] == before["title"], fields["title"]
        assert fields["date_start"]["after"] == "1998-08-02", fields["date_start"]

        # 고친 사람이 그 값을 보증한다 -> 확인 완료
        state = result["state"]
        assert state["state"] == VerificationState.CONFIRMED.value, state["state"]
        assert [p["id"] for p in state["corrected_by"]] == ["P01"], state["corrected_by"]

        # 이력에 남는다 (값만 바뀌면 되짚을 수 없다)
        entry = graph_manager.get_node(EVENT)["verifications"][-1]
        assert entry["action"] == VerifyAction.CORRECT.value, entry
        assert len(entry["changes"]) == 2, entry
        print("  수정 기록 OK:", [c["field"] for c in entry["changes"]])
    finally:
        _restore_event(before)
        _reset()


def test_correct_moves_the_place_edge_too():
    """장소를 고치면 LOCATED_AT 엣지도 함께 옮긴다

    location_id만 고치면 사건 목록과 그래프 화면이 서로 다른 장소를 가리킨다.
    """
    _require_seeded_graph()
    _reset()
    before = _snapshot()
    old_place = before["location_id"]
    new_place = next(
        p["id"] for p in graph_manager.get_places() if p["id"] != old_place
    )
    try:
        verification.record(
            EVENT, "P02", VerifyAction.CORRECT.value,
            corrections={"location_id": new_place},
        )
        assert graph_manager.get_node(EVENT)["location_id"] == new_place

        edges = [
            e for e in graph_manager.get_all_edges()
            if e["source"] == EVENT and e["relation"] == "located_at"
        ]
        targets = {e["target"] for e in edges}
        assert new_place in targets, targets
        assert old_place not in targets, f"예전 장소 엣지가 남았다: {targets}"

        detail = graph_manager.get_event_detail(EVENT)
        assert detail["location"]["id"] == new_place, detail["location"]
        print("  장소 엣지 이동 OK:", old_place, "->", new_place)
    finally:
        # 엣지를 원래 장소로 되돌린다
        verification.record(
            EVENT, "P02", VerifyAction.CORRECT.value,
            corrections={"location_id": old_place},
        )
        _restore_event(before)
        _reset()


def test_correct_rejects_bad_input():
    """고칠 수 없는 필드·없는 장소·바뀐 것 없음은 받지 않는다"""
    _require_seeded_graph()
    _reset()
    before = _snapshot()
    try:
        for corrections, expected in [
            ({"confidence": "confirmed"}, "고칠 수 없는"),
            ({"location_id": "NO_SUCH_PLACE"}, "그런 장소가 없습니다"),
            ({"title": before["title"]}, "바뀐 값이 없습니다"),
            ({}, "바뀐 값이 없습니다"),
        ]:
            try:
                verification.record(
                    EVENT, "P01", VerifyAction.CORRECT.value, corrections=corrections
                )
            except ValueError as e:
                assert expected in str(e), (corrections, str(e))
            else:
                raise AssertionError(f"{corrections} 를 받아들였다")

        # 아무것도 바뀌지 않았다
        assert _snapshot() == before, "실패한 수정이 값을 바꿨다"
        assert not graph_manager.get_node(EVENT).get("verifications"), "실패한 수정이 이력을 남겼다"
        print("  잘못된 수정 거절 OK")
    finally:
        _restore_event(before)
        _reset()


def test_inbox_carries_current_values_and_correction_history():
    """확인 목록이 수정 폼을 채울 값과 수정 이력을 함께 내려준다"""
    _require_seeded_graph()
    _reset()
    before = _snapshot()
    try:
        verification.record(
            EVENT, "P03", VerifyAction.CORRECT.value,
            corrections={"description": "광안리에서 처음 바다를 봤다."},
        )
        item = next(i for i in verification.list_pending() if i["event_id"] == EVENT)

        assert item["description"] == "광안리에서 처음 바다를 봤다.", item["description"]
        assert item["place"] and item["place"]["id"] == before["location_id"], item["place"]
        assert [p["id"] for p in item["corrected_by"]] == ["P03"], item["corrected_by"]

        history = item["corrections"]
        assert len(history) == 1, history
        assert history[0]["person_name"], history[0]
        assert history[0]["changes"][0]["field"] == "description", history[0]
        print("  확인 목록 수정 이력 OK")
    finally:
        _restore_event(before)
        _reset()


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}\n{e}")
    _reset()
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
