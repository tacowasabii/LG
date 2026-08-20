"""역할 가드 회귀 테스트

    python tests/test_permissions.py

사용자 안내서가 약속한 문장이 실제로 지켜지는지 본다.
    "열람자 — 보고 듣기만 (기록을 바꾸지 않음)"
    "가족 관리자 — 초대, 공개 범위, 삭제·이관 결정"

인증이 없으므로 이것은 보안 경계가 아니라 실수 방지 가드다. 그래서 헤더를
보내지 않은 요청은 쓰기를 통과시키고(막아도 얻는 것이 없다), 되돌릴 수 없는
행위(삭제·관리)만 막는다. 그 구분이 코드와 일치하는지도 함께 확인한다.

그래프를 실제로 바꾸므로 끝에서 원래대로 되돌린다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from backend.config import MEDIA_DIR  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.graph_models import FamilyRole, MediaNode, MediaType  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

OWNER_PERSON = "P03"  # 김하늘 — 테스트에서 가족 관리자로 세운다
WRITER = "P01"  # 김민수 — 기록자
VIEWER = "P04"  # 김지우 — 열람자로 내린다
EVENT = "E01"
MEDIA = "E01_002"

_created: list[str] = []
_temp_files: list[Path] = []


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _restore():
    for person_id in (OWNER_PERSON, WRITER, VIEWER):
        graph_manager.update_node(
            person_id, {"role": FamilyRole.CONTRIBUTOR.value, "private_request": False}
        )
    graph_manager.update_node(EVENT, {"echoes": []})
    graph_manager.update_node(
        MEDIA, {"visibility": "family", "allowed_ids": [], "owner_id": None}
    )
    for node_id in _created:
        graph_manager.delete_node(node_id)
    _created.clear()

    for path in _temp_files:
        if path.exists():
            path.unlink()
    _temp_files.clear()


def _setup_roles():
    graph_manager.update_node(OWNER_PERSON, {"role": FamilyRole.OWNER.value})
    graph_manager.update_node(WRITER, {"role": FamilyRole.CONTRIBUTOR.value})
    graph_manager.update_node(VIEWER, {"role": FamilyRole.VIEWER.value})


def _as(person_id):
    return {"X-Viewer-Id": person_id} if person_id else {}


def _make_temp_media(owner_id=None, visibility="family") -> MediaNode:
    """지워도 되는 임시 기록 (시드 사진을 건드리지 않기 위해)"""
    index = len(_temp_files) + 1
    file_name = f"test-permission-{index}.jpg"
    path = MEDIA_DIR / file_name
    path.write_bytes(b"not-a-real-jpeg")
    _temp_files.append(path)

    node = MediaNode(
        media_type=MediaType.PHOTO,
        file_path=f"/media-files/{file_name}",
        original_filename=file_name,
        owner_id=owner_id,
        visibility=visibility,
    )
    graph_manager.add_media(node)
    _created.append(node.id)
    return node


# --- 열람자는 기록을 바꾸지 못한다 -------------------------------------------


def test_viewer_cannot_add_memory():
    _setup_roles()
    try:
        with TestClient(app) as client:
            res = client.post(
                f"/api/memories/{EVENT}/memory",
                json={"person_id": VIEWER, "content": "열람자가 남기려는 기억"},
                headers=_as(VIEWER),
            )
            assert res.status_code == 403, res.status_code
            assert "열람자" in res.json()["detail"], res.json()
        print("  열람자 기억 더하기 차단 OK")
    finally:
        _restore()


def test_writer_can_add_memory():
    _setup_roles()
    try:
        with TestClient(app) as client:
            res = client.post(
                f"/api/memories/{EVENT}/memory",
                json={"person_id": WRITER, "content": "기록자가 더한 기억"},
                headers=_as(WRITER),
            )
            assert res.status_code == 200, res.text
            _created.append(res.json()["memory_id"])
        print("  기록자 기억 더하기 통과 OK")
    finally:
        _restore()


def test_viewer_cannot_add_person():
    _setup_roles()
    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/graph/person",
                json={"name": "테스트", "relation": "이모"},
                headers=_as(VIEWER),
            )
            assert res.status_code == 403, res.status_code
        # 혹시 만들어졌다면 지운다
        for person in graph_manager.get_persons():
            if person.get("name") == "테스트":
                _created.append(person["id"])
        assert not _created, "차단했는데 인물이 만들어졌다"
        print("  열람자 인물 추가 차단 OK")
    finally:
        _restore()


def test_viewer_cannot_submit_interview_answer():
    _setup_roles()
    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/interview/answer",
                json={"session_id": "없는-세션", "answer": "테스트"},
                headers=_as(VIEWER),
            )
            # 세션 검사보다 역할 검사가 먼저 걸려야 한다
            assert res.status_code == 403, res.status_code
        print("  열람자 답변 차단 OK")
    finally:
        _restore()


# --- 관리 행위는 가족 관리자만 -----------------------------------------------


def test_only_admin_changes_roles():
    _setup_roles()
    try:
        with TestClient(app) as client:
            denied = client.put(
                f"/api/family/member/{WRITER}",
                json={"role": "viewer"},
                headers=_as(WRITER),
            )
            assert denied.status_code == 403, denied.status_code

            allowed = client.put(
                f"/api/family/member/{WRITER}",
                json={"role": "viewer"},
                headers=_as(OWNER_PERSON),
            )
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["role"] == "viewer", allowed.json()
        print("  역할 변경은 관리자만 OK")
    finally:
        _restore()


def test_admin_action_without_actor_is_refused():
    """누가 했는지 모르는 관리 행위는 받지 않는다"""
    _setup_roles()
    try:
        with TestClient(app) as client:
            res = client.post("/api/family/invite", json={})
            assert res.status_code == 403, res.status_code
        print("  익명 초대 차단 OK")
    finally:
        _restore()


def test_person_can_toggle_own_private_request():
    """자기가 나온 기록을 감추는 것은 본인이 정한다"""
    _setup_roles()
    try:
        with TestClient(app) as client:
            mine = client.put(
                f"/api/family/member/{VIEWER}",
                json={"private_request": True},
                headers=_as(VIEWER),
            )
            assert mine.status_code == 200, mine.text
            assert mine.json()["private_request"] is True

            others = client.put(
                f"/api/family/member/{WRITER}",
                json={"private_request": True},
                headers=_as(VIEWER),
            )
            assert others.status_code == 403, others.status_code
        print("  본인 비공개 요청 허용 · 남의 것 차단 OK")
    finally:
        _restore()


# --- 삭제는 올린 사람이나 관리자만 -------------------------------------------


def test_delete_is_limited_to_owner_and_admin():
    """삭제는 되돌릴 수 없다 — 올린 사람과 가족 관리자만

    시드 사진으로 시험하면 실제 파일이 지워져 데모 데이터가 깨진다.
    그래서 임시 기록을 만들어 그것만 지운다.
    """
    _setup_roles()
    temp = _make_temp_media(owner_id=WRITER)
    try:
        with TestClient(app) as client:
            # 남이 올린 기록은 기록자여도 못 지운다
            other_writer = client.delete(f"/api/media/{temp.id}", headers=_as("P02"))
            assert other_writer.status_code == 403, other_writer.status_code
            assert graph_manager.get_node(temp.id), "차단했는데 지워졌다"

            # 열람자도 못 지운다
            viewer = client.delete(f"/api/media/{temp.id}", headers=_as(VIEWER))
            assert viewer.status_code == 403, viewer.status_code

            # 올린 사람은 지울 수 있다
            owner = client.delete(f"/api/media/{temp.id}", headers=_as(WRITER))
            assert owner.status_code == 200, owner.text
            assert graph_manager.get_node(temp.id) is None, "삭제가 반영되지 않았다"

        # 가족 관리자도 지울 수 있다 (새 임시 기록으로 확인)
        second = _make_temp_media(owner_id=WRITER)
        with TestClient(app) as client:
            admin = client.delete(f"/api/media/{second.id}", headers=_as(OWNER_PERSON))
            assert admin.status_code == 200, admin.text
        print("  삭제 권한 OK (남·열람자 차단 · 소유자·관리자 허용)")
    finally:
        _restore()


def test_memory_delete_is_limited_to_its_author_and_admin():
    """기억을 거두는 것은 남긴 사람과 가족 관리자뿐이다

    문장에도 주인이 있다 (contributor_id). 남의 기억을 대신 거둘 수 있으면
    "누가 남긴 기억인지"가 무너진다 — 원본 삭제와 같은 판정을 지난다.
    """
    _setup_roles()

    def _leave(person_id: str) -> str:
        with TestClient(app) as client:
            res = client.post(
                f"/api/memories/{EVENT}/memory",
                json={"content": "권한 시험으로 남긴 기억입니다."},
                headers=_as(person_id),
            )
        assert res.status_code == 200, res.text
        memory_id = res.json()["memory_id"]
        _created.append(memory_id)
        return memory_id

    try:
        mine = _leave(WRITER)
        with TestClient(app) as client:
            # 남이 남긴 기억은 기록자여도 못 지운다
            other = client.delete(
                f"/api/memories/{EVENT}/memory/{mine}", headers=_as("P02")
            )
            assert other.status_code == 403, other.status_code
            assert graph_manager.get_node(mine), "차단했는데 지워졌다"

            # 열람자도 못 지운다
            viewer = client.delete(
                f"/api/memories/{EVENT}/memory/{mine}", headers=_as(VIEWER)
            )
            assert viewer.status_code == 403, viewer.status_code

            # 남긴 사람은 지울 수 있다
            own = client.delete(
                f"/api/memories/{EVENT}/memory/{mine}", headers=_as(WRITER)
            )
            assert own.status_code == 200, own.text
            assert graph_manager.get_node(mine) is None, "삭제가 반영되지 않았다"

        # 가족 관리자도 지울 수 있다 (남이 남긴 기억이라도)
        second = _leave(WRITER)
        with TestClient(app) as client:
            admin = client.delete(
                f"/api/memories/{EVENT}/memory/{second}", headers=_as(OWNER_PERSON)
            )
            assert admin.status_code == 200, admin.text
            assert graph_manager.get_node(second) is None, "삭제가 반영되지 않았다"
        print("  기억 삭제 권한 OK (남·열람자 차단 · 남긴 사람·관리자 허용)")
    finally:
        _restore()


def test_visibility_change_requires_owner_or_admin():
    _setup_roles()
    graph_manager.update_node(MEDIA, {"owner_id": WRITER})
    try:
        with TestClient(app) as client:
            denied = client.put(
                f"/api/family/media/{MEDIA}/visibility",
                json={"visibility": "private"},
                headers=_as(VIEWER),
            )
            assert denied.status_code == 403, denied.status_code

            allowed = client.put(
                f"/api/family/media/{MEDIA}/visibility",
                json={"visibility": "private"},
                headers=_as(WRITER),
            )
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["visibility"] == "private"
        print("  공개 범위 변경 권한 OK")
    finally:
        _restore()


def test_hidden_record_delete_returns_404_not_403():
    """볼 수 없는 기록의 존재를 삭제 응답으로 알려주지 않는다"""
    _setup_roles()
    temp = _make_temp_media(owner_id=WRITER, visibility="private")
    try:
        with TestClient(app) as client:
            res = client.delete(f"/api/media/{temp.id}", headers=_as(VIEWER))
            assert res.status_code == 404, res.status_code
        assert graph_manager.get_node(temp.id), "지워지면 안 되는 기록이 지워졌다"
        print("  숨은 기록 삭제 404 OK")
    finally:
        _restore()


def test_write_without_actor_still_works():
    """헤더 없는 쓰기는 통과시킨다 (인증이 없으므로 막아도 얻는 것이 없다)"""
    _setup_roles()
    try:
        with TestClient(app) as client:
            res = client.post(f"/api/memories/{EVENT}/echo?person_id={WRITER}")
            assert res.status_code == 200, res.text
        print("  익명 쓰기 통과 OK (문서화된 한계)")
    finally:
        _restore()


TESTS = [
    test_viewer_cannot_add_memory,
    test_writer_can_add_memory,
    test_viewer_cannot_add_person,
    test_viewer_cannot_submit_interview_answer,
    test_only_admin_changes_roles,
    test_admin_action_without_actor_is_refused,
    test_person_can_toggle_own_private_request,
    test_delete_is_limited_to_owner_and_admin,
    test_memory_delete_is_limited_to_its_author_and_admin,
    test_visibility_change_requires_owner_or_admin,
    test_hidden_record_delete_returns_404_not_403,
    test_write_without_actor_still_works,
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
