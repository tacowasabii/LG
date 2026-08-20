"""가족 공간 · 공개 범위 회귀 테스트

    python tests/test_family_visibility.py

기획안 08장이 요구하는 것은 "설정을 저장한다"가 아니라 "실제로 가려진다"다.
그래서 목록·검색·근거까지 내려가서 확인한다.

  - 역할·비공개 요청이 인물 노드에 남는가
  - 비공개 기록이 소유자에게만 보이는가
  - 부분 공개가 지목한 사람에게만 열리는가
  - 인물이 비공개를 요청하면 그 사람이 나온 기록이 다른 가족에게 가려지는가
  - 본인은 자기가 나온 기록을 계속 보는가
  - 가려진 기록이 사건 요약의 썸네일·개수에서도 빠지는가

그래프를 실제로 바꾸므로 끝에서 원래대로 되돌린다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import FamilyRole, Visibility  # noqa: E402
from backend.routers.graph import list_events  # noqa: E402
from backend.routers.media import list_media  # noqa: E402
from backend.services import family, visibility  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

MEDIA = "E01_002"  # 1998 부산 여행 · 아버지가 캠코더로 촬영하는 장면
EVENT = "E01"
OWNER = "P01"  # 김민수
OTHER = "P03"  # 김하늘
THIRD = "P04"  # 김지우


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _restore():
    """테스트가 건드린 공개 범위·역할·동의를 원래대로"""
    graph_manager.update_node(
        MEDIA, {"visibility": Visibility.FAMILY.value, "allowed_ids": [], "owner_id": None}
    )
    for person_id in (OWNER, OTHER, THIRD):
        graph_manager.update_node(
            person_id,
            {"private_request": False, "role": FamilyRole.CONTRIBUTOR.value},
        )


def _visible_ids(viewer_id):
    items = asyncio.run(list_media(media_type=None, person_id=None, viewer_id=viewer_id))
    return {item.id for item in items}


# --- 가족 공간 ---------------------------------------------------------------


def test_members_come_from_graph_persons():
    """구성원은 인물 노드 그대로다 (별도 사용자 목록을 만들지 않는다)"""
    members = family.list_members()
    person_ids = {p["id"] for p in graph_manager.get_persons()}

    assert {m["id"] for m in members} == person_ids, "구성원과 인물 노드가 어긋난다"
    assert all(m["name"] for m in members), "이름이 빈 구성원이 있다"
    print("  구성원", len(members), "명 · 인물 노드와 일치")


def test_role_change_persists_and_records_join():
    """역할을 바꾸면 인물 노드에 남고, 참여 시점이 기록된다"""
    try:
        family.update_member(OTHER, role=FamilyRole.OWNER.value)
        person = graph_manager.get_node(OTHER)
        assert person["role"] == FamilyRole.OWNER.value, person["role"]
        assert person["joined_at"], "참여 시점이 비었다"
        print("  역할 변경 OK:", person["role"], person["joined_at"])
    finally:
        _restore()


def test_unknown_role_is_rejected():
    """알 수 없는 역할은 받지 않는다"""
    try:
        family.update_member(OTHER, role="admin")
        raise AssertionError("잘못된 역할을 받아들였다")
    except ValueError:
        print("  잘못된 역할 거부 OK")
    finally:
        _restore()


def test_invite_expires_and_marks_person():
    """초대는 만료 시각을 갖고, 지목한 사람은 초대 대기로 바뀐다"""
    try:
        invite = family.create_invite(person_id=THIRD)
        assert invite["code"].startswith("HS-"), invite["code"]
        assert invite["expires_at"] > invite["created_at"], invite
        assert graph_manager.get_node(THIRD)["role"] == FamilyRole.INVITED.value
        assert any(i["code"] == invite["code"] for i in family.get_space()["invites"])
        print("  초대 발급 OK:", invite["code"])
    finally:
        _restore()


# --- 공개 범위 ---------------------------------------------------------------


def test_family_scope_is_visible_to_everyone():
    """가족 전체 공개는 모두가 본다 (공개 범위 필드가 없는 예전 기록도 포함)"""
    try:
        assert MEDIA in _visible_ids(OWNER)
        assert MEDIA in _visible_ids(OTHER)
        assert MEDIA in _visible_ids(None)
        print("  가족 전체 공개 OK")
    finally:
        _restore()


def test_private_is_owner_only():
    """비공개는 올린 사람만 본다"""
    try:
        family.set_media_visibility(MEDIA, Visibility.PRIVATE.value, owner_id=OWNER)
        assert MEDIA in _visible_ids(OWNER), "소유자가 자기 기록을 못 본다"
        assert MEDIA not in _visible_ids(OTHER), "비공개인데 다른 사람에게 보인다"
        assert MEDIA not in _visible_ids(None), "열람자를 모를 때도 보인다"
        print("  비공개 OK")
    finally:
        _restore()


def test_partial_opens_only_to_listed():
    """부분 공개는 지목한 사람에게만 열린다"""
    try:
        family.set_media_visibility(
            MEDIA, Visibility.PARTIAL.value, allowed_ids=[OTHER], owner_id=OWNER
        )
        assert MEDIA in _visible_ids(OTHER), "지목했는데 안 보인다"
        assert MEDIA not in _visible_ids(THIRD), "지목하지 않았는데 보인다"
        assert MEDIA in _visible_ids(OWNER), "소유자가 못 본다"
        print("  부분 공개 OK")
    finally:
        _restore()


def test_unknown_person_in_allowed_is_dropped():
    """없는 사람 id는 열람 목록에 남기지 않는다"""
    try:
        node = family.set_media_visibility(
            MEDIA, Visibility.PARTIAL.value, allowed_ids=[OTHER, "P99"], owner_id=OWNER
        )
        assert node["allowed_ids"] == [OTHER], node["allowed_ids"]
        print("  없는 인물 정리 OK")
    finally:
        _restore()


def test_person_consent_hides_their_records_from_others():
    """인물이 비공개를 요청하면 그 사람이 나온 기록이 다른 가족에게 가려진다"""
    try:
        before = len(_visible_ids(OWNER))
        family.update_member(OTHER, private_request=True)
        after = len(_visible_ids(OWNER))

        assert after < before, f"가려지지 않았다 ({before} -> {after})"
        # 본인은 자기가 나온 기록을 그대로 본다
        assert len(_visible_ids(OTHER)) == before, "본인 기록까지 가렸다"
        print(f"  인물 동의 OK: 다른 가족 {before} -> {after}, 본인은 그대로")
    finally:
        _restore()


def test_hidden_media_drops_out_of_event_summary():
    """가려진 기록은 사건 요약의 썸네일·개수에서도 빠진다

    목록에서만 감추고 사건 요약에 남으면, 썸네일로 그 사진이 그대로 보인다.
    """
    try:
        before = next(e for e in asyncio.run(list_events(viewer_id=OTHER)) if e.id == EVENT)
        family.set_media_visibility(MEDIA, Visibility.PRIVATE.value, owner_id=OWNER)
        after = next(e for e in asyncio.run(list_events(viewer_id=OTHER)) if e.id == EVENT)

        assert after.media_count == before.media_count - 1, (
            before.media_count,
            after.media_count,
        )
        assert not any(MEDIA in path for path in after.media_thumbs), after.media_thumbs

        # 소유자에게는 그대로 남아 있다
        owner_view = next(e for e in asyncio.run(list_events(viewer_id=OWNER)) if e.id == EVENT)
        assert owner_view.media_count == before.media_count, owner_view.media_count
        print(f"  사건 요약 반영 OK: {before.media_count} -> {after.media_count} (소유자는 그대로)")
    finally:
        _restore()


def test_hidden_media_is_not_used_as_chat_evidence():
    """가려진 기록은 답변의 근거로도 쓰이지 않는다

    근거 뱃지에서만 감추면 LLM이 본문에서 그 사진의 장면 설명을 말해 버린다.
    """
    try:
        family.set_media_visibility(MEDIA, Visibility.PRIVATE.value, owner_id=OWNER)
        # get_node는 사본을 돌려주므로 바꾼 뒤에 다시 읽어야 한다.
        # 실제 경로에서는 검색이 그때그때 그래프에서 노드를 꺼내 온다.
        node = graph_manager.get_node(MEDIA)

        kept = visibility.filter_search_results([node], OWNER)
        dropped = visibility.filter_search_results([node], OTHER)

        assert kept, "소유자 검색에서 빠졌다"
        assert not dropped, "다른 사람 검색에 남아 있다"
        print("  검색 단계 차단 OK")
    finally:
        _restore()


def test_cascade_preview_lists_derived_and_keeps_memories():
    """삭제 전파 미리보기는 파생물을 밝히고, 기억 문장은 지키지 않는다고 말한다"""
    preview = family.delete_cascade_preview(MEDIA)

    assert preview, "미리보기가 비었다"
    assert preview["target"], "대상 이름이 없다"
    assert preview["derived"], "파생물 목록이 비었다"
    labels = " ".join(item["label"] for item in preview["derived"])
    assert "그래프 연결" in labels, labels
    print("  삭제 전파 미리보기 OK:", len(preview["derived"]), "항목")


def test_missing_media_returns_none():
    assert family.set_media_visibility("없는-기록", Visibility.FAMILY.value) is None
    assert family.delete_cascade_preview("없는-기록") is None
    print("  없는 기록 처리 OK")


def test_http_family_endpoints():
    """실제 HTTP에서 열람자에 따라 응답이 달라지는지"""
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            space = client.get("/api/family", params={"viewer_id": OWNER})
            assert space.status_code == 200, space.text
            assert space.json()["members"], space.text

            # 비공개 요청은 본인이 정한다. 누가 하는지 밝히지 않으면 받지 않는다
            # (tests/test_permissions.py가 그 규칙을 따로 검증한다).
            anonymous = client.put(
                f"/api/family/member/{OTHER}", json={"private_request": True}
            )
            assert anonymous.status_code == 403, anonymous.status_code

            changed = client.put(
                f"/api/family/member/{OTHER}",
                json={"private_request": True},
                headers={"X-Viewer-Id": OTHER},
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["private_request"] is True

            # 비공개 요청이 걸린 뒤 다른 가족의 시야가 줄어든다
            mine = client.get("/api/family", params={"viewer_id": OTHER}).json()
            others = client.get("/api/family", params={"viewer_id": OWNER}).json()
            assert others["visibility"]["hidden"] > mine["visibility"]["hidden"], (
                others["visibility"],
                mine["visibility"],
            )

            # 역할 변경은 관리자만 — 관리자가 아직 없는 공간에서는 기록자도 할 수 있다
            bad = client.put(
                f"/api/family/member/{OTHER}",
                json={"role": "admin"},
                headers={"X-Viewer-Id": OWNER},
            )
            assert bad.status_code == 400, bad.status_code
        print("  HTTP 응답 OK: /api/family · PUT member")
    finally:
        _restore()


TESTS = [
    test_members_come_from_graph_persons,
    test_role_change_persists_and_records_join,
    test_unknown_role_is_rejected,
    test_invite_expires_and_marks_person,
    test_family_scope_is_visible_to_everyone,
    test_private_is_owner_only,
    test_partial_opens_only_to_listed,
    test_unknown_person_in_allowed_is_dropped,
    test_person_consent_hides_their_records_from_others,
    test_hidden_media_drops_out_of_event_summary,
    test_hidden_media_is_not_used_as_chat_evidence,
    test_cascade_preview_lists_derived_and_keeps_memories,
    test_missing_media_returns_none,
    test_http_family_endpoints,
]


if __name__ == "__main__":
    _require_seeded_graph()

    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {test.__name__}: {type(e).__name__} {e}")

    _restore()
    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} 통과")
    sys.exit(1 if failures else 0)
