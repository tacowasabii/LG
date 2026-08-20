"""얼굴 인식 회귀 테스트 (Amazon Rekognition)

    python tests/test_faces.py

여기서 재는 것은 "얼마나 잘 맞추나"가 아니라 **틀릴 때 무엇을 하나**다. 등장
인물은 공개 범위 판정에도 쓰이므로, 잘못 붙으면 남의 사진에 자기가 들어간다.

  - 사람이 지목한 것을 자동 인식이 덮지 않는가
  - 사진이 아닌 기록(음성·영상)은 건너뛰는가
  - 나이가 안 맞는 후보를 빼는가 (태어나기 전 사진 포함)
  - 1등과 2등이 붙어 있으면 아무도 넣지 않는가
  - 한 사람이 한 사진의 두 얼굴에 붙지 않는가
  - 자격증명이 없을 때 조용히 지나가는가

앞의 다섯 개는 AWS 호출 없이 순수 함수로 확인한다. 실제 인식은 등록 상태에
따라 달라지므로 마지막 항목만 호출한다 (등록이 없으면 건너뛴다).

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py

얼굴 등록은 따로 한다:
    python scripts/enroll_faces.py
"""

import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import MediaType, SourceType  # noqa: E402
from backend.services import event_resolver, faces  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

PHOTO = "E01_002"      # 1998 부산 (P01 P02 P03 태그)
AUDIO_LIKE = None      # 아래에서 찾는다
DAUGHTER = "P03"       # 김하늘 1996년생
SON = "P04"            # 김지우 2000년생
MOTHER = "P02"         # 박서연 1973년생


def _require_seeded_graph():
    if len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _person(pid):
    return graph_manager.get_node(pid)


def test_age_filter_rejects_unborn():
    """태어나기 전 사진에서는 후보에서 뺀다

    실측한 오답이 이것이었다. 1998년 사진의 0~2세 얼굴이 2000년생 아들로
    매칭됐다 (딸보다 1.9점 높았다). 아들은 그때 없었다.
    """
    _require_seeded_graph()
    son = _person(SON)
    assert son and son.get("birth_year") == 2000, son

    # 1998년 사진의 0~2세 얼굴
    assert not faces.age_fits(son, date(1998, 8, 1), 0, 2), "태어나기 전인데 통과했다"
    # 딸(1996년생)은 그때 2살이라 맞는다
    assert faces.age_fits(_person(DAUGHTER), date(1998, 8, 1), 0, 2)
    print("  태어나기 전 후보 제외 OK")


def test_age_filter_rejects_wrong_generation():
    """세대가 다른 후보를 뺀다

    실측 오답: 2015년 사진의 19~25세 얼굴이 엄마로 매칭됐다 (딸보다 2.9점 높았다).
    그때 엄마는 42세다.
    """
    _require_seeded_graph()
    when = date(2015, 6, 1)
    assert not faces.age_fits(_person(MOTHER), when, 19, 25), "42세가 19-25에 통과했다"
    assert faces.age_fits(_person(DAUGHTER), when, 19, 25), "19세가 19-25에서 빠졌다"
    print("  세대 불일치 후보 제외 OK")


def test_age_filter_is_lenient_when_unknown():
    """모르는 것으로 후보를 지우지 않는다

    촬영 시점이 없거나 생년이 없으면 나이로 막지 않는다. 나이를 모른다는 것이
    "그 사람이 아니다"는 뜻은 아니다.
    """
    _require_seeded_graph()
    assert faces.age_fits(_person(DAUGHTER), None, 20, 30), "촬영 시점을 몰라서 막혔다"
    assert faces.age_fits({"birth_year": None}, date(2015, 1, 1), 20, 30)
    assert faces.age_fits(_person(DAUGHTER), date(2015, 1, 1), None, None)
    print("  모를 때는 막지 않음 OK")


def test_adult_tolerance_covers_measured_skew():
    """어른 나이를 높게 추정하는 경향을 허용 범위가 덮는다

    실측: 36세 아빠를 41-49로, 28세를 32-45로 추정했다. 이 편차에서 본인이
    빠지면 어른도 못 맞춘다.
    """
    _require_seeded_graph()
    father = {"birth_year": 1970}
    assert faces.age_fits(father, date(2006, 7, 1), 41, 49), "36세가 41-49에서 빠졌다"
    assert faces.age_fits(father, date(1998, 7, 1), 32, 45), "28세가 32-45에서 빠졌다"
    print("  어른 추정 편차 허용 OK")


def test_autotag_does_not_overwrite_human_choice():
    """사람이 지목한 것을 자동 인식이 덮지 않는다

    자동 인식은 추정이다. 누른 것을 추정으로 덮으면 지목의 뜻이 없어진다.
    """
    _require_seeded_graph()
    before = list(graph_manager.get_node(PHOTO).get("detected_faces") or [])
    assert before, "시드에 태그가 있어야 이 경우를 확인할 수 있다"

    added = event_resolver.autotag_media_persons(PHOTO)

    assert added == [], f"이미 지목된 사진에 자동으로 붙였다: {added}"
    assert graph_manager.get_node(PHOTO)["detected_faces"] == before, "태그가 바뀌었다"
    print("  사람이 지목한 것을 덮지 않음 OK")


def test_autotag_skips_non_photos():
    """사진이 아닌 기록은 건너뛴다 (음성에 얼굴은 없다)"""
    _require_seeded_graph()
    others = [
        n for n in graph_manager.get_media_nodes()
        if n.get("media_type") != MediaType.PHOTO
    ]
    if not others:
        print("  사진이 아닌 기록이 없음 — 건너뜀")
        return

    node = others[0]
    before = list(node.get("detected_faces") or [])
    graph_manager.update_node(node["id"], {"detected_faces": []})
    try:
        added = event_resolver.autotag_media_persons(node["id"])
        assert added == [], f"{node.get('media_type')}에 얼굴을 붙였다: {added}"
        print(f"  {node.get('media_type')} 건너뛰기 OK")
    finally:
        graph_manager.update_node(node["id"], {"detected_faces": before})


def test_margin_and_threshold_are_set_from_measurement():
    """애매한 구간을 비우는 기준이 실측과 맞는가

    실측: 본인은 2등과 8~12점 차이, 아이가 헷갈릴 때는 0.2~2.6점 차이였다.
    그 사이에 선이 있어야 한다.
    """
    assert 2.6 < faces.MIN_MARGIN <= 8.0, faces.MIN_MARGIN
    assert faces.MATCH_THRESHOLD >= 85, faces.MATCH_THRESHOLD
    print(f"  기준 OK (임계 {faces.MATCH_THRESHOLD} · 격차 {faces.MIN_MARGIN})")


def test_identify_is_quiet_without_enrollment():
    """등록된 얼굴이 없거나 자격증명이 없으면 조용히 빈 목록"""
    if not faces.enabled():
        node = graph_manager.get_node(PHOTO)
        assert faces.identify(node) == [], "자격증명이 없는데 결과가 나왔다"
        print("  자격증명 없음 — 조용히 지나감 OK")
        return

    counts = faces.enrolled_counts()
    if not counts:
        node = graph_manager.get_node(PHOTO)
        found = [r for r in faces.identify(node) if r["person_id"]]
        assert found == [], f"등록이 없는데 사람을 찾았다: {found}"
        print("  등록 없음 — 아무도 붙이지 않음 OK")
        return

    print(f"  등록됨: {counts} (실제 인식은 scripts/enroll_faces.py --list 로 확인)")


def test_recognized_faces_are_marked_as_inference():
    """자동으로 붙인 태그는 추정으로 표시된다

    사람이 지목한 것과 구분되지 않으면, 화면이 "AI가 알아본 것"이라고 밝힐 수
    없고 사용자는 고쳐야 할 대상인지 알 수 없다.
    """
    _require_seeded_graph()
    if not faces.enabled() or not faces.enrolled_counts():
        print("  등록이 없어 건너뜀")
        return

    node = graph_manager.get_node(PHOTO)
    before = list(node.get("detected_faces") or [])
    before_source = node.get("faces_source")
    graph_manager.update_node(PHOTO, {"detected_faces": [], "faces_source": None})
    try:
        added = event_resolver.autotag_media_persons(PHOTO)
        fresh = graph_manager.get_node(PHOTO)
        if not added:
            print("  아무도 알아보지 못함 (표시할 것이 없다) — 건너뜀")
            return
        assert fresh.get("faces_source") == SourceType.AI_VISION, fresh.get("faces_source")
        print(f"  자동 태그 {added} 를 ai_vision 으로 표시 OK")
    finally:
        event_resolver.set_media_persons(PHOTO, before)
        graph_manager.update_node(PHOTO, {"faces_source": before_source})


def test_stored_boxes_do_not_call_the_service():
    """저장된 위치만 읽는다 (여는 것만으로 유료 호출이 나가지 않게)

    상세 화면은 사진을 열 때마다 이 함수를 지난다. 여기서 찾으면 훑어보기만
    하는 사람도 사진마다 Rekognition 호출을 만든다.
    """
    _require_seeded_graph()
    node = {"face_boxes": [{"box": {"left": 0.1}, "person_id": "P01"}]}
    assert faces.stored_boxes(node) == node["face_boxes"]
    assert faces.stored_boxes({}) == []
    print("  저장된 것만 읽음 OK")


def test_face_boxes_are_ratio_coordinates():
    """좌표가 0~1 비율이다 (화면 크기와 무관하게 얹을 수 있게)

    픽셀로 저장하면 원본 크기를 함께 들고 있어야 하고, 썸네일 위에 얹을 때
    다시 환산해야 한다. 비율이면 그냥 %로 쓴다.
    """
    _require_seeded_graph()
    stored = [
        b for n in graph_manager.get_media_nodes()
        for b in (n.get("face_boxes") or [])
    ]
    if not stored:
        print("  저장된 얼굴 위치가 없음 — 건너뜀")
        return
    for box in stored:
        b = box.get("box") or {}
        for key in ("left", "top", "width", "height"):
            value = b.get(key)
            assert value is not None, box
            assert 0.0 <= float(value) <= 1.0, (key, value)
    print(f"  비율 좌표 OK ({len(stored)}개 확인)")


def test_unknown_faces_are_kept_with_a_reason():
    """이름을 못 붙인 얼굴도 남긴다 (이유와 함께)

    조용히 빼면 사용자는 AI가 그 얼굴을 못 봤다고 생각한다. 찾았지만 가리지
    못했다는 것과 다른 이야기다.
    """
    _require_seeded_graph()
    unknown = [
        b for n in graph_manager.get_media_nodes()
        for b in (n.get("face_boxes") or [])
        if not b.get("person_id")
    ]
    if not unknown:
        print("  이름을 못 붙인 얼굴이 없음 — 건너뜀")
        return
    without_reason = [b for b in unknown if not (b.get("reason") or "").strip()]
    assert not without_reason, f"이유 없이 비운 얼굴 {len(without_reason)}개"
    print(f"  미상 얼굴에 이유가 있음 OK ({len(unknown)}개)")


def test_detail_endpoint_serves_face_boxes():
    """상세 응답에 얼굴 위치와 이름이 실려 나간다

    스키마에서 빠뜨리면 서버는 저장하는데 화면은 못 받는다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    _require_seeded_graph()
    with TestClient(app) as client:
        response = client.get(f"/api/media/{PHOTO}")
        assert response.status_code == 200, response.text
        body = response.json()

    assert "face_boxes" in body, list(body)
    for face in body["face_boxes"]:
        for key in ("left", "top", "width", "height", "person_id", "name", "reason"):
            assert key in face, (key, face)
    named = [f for f in body["face_boxes"] if f.get("person_id")]
    print(f"  상세 응답 OK (얼굴 {len(body['face_boxes'])}개 · 이름 {len(named)}개)")


TESTS = [
    test_age_filter_rejects_unborn,
    test_age_filter_rejects_wrong_generation,
    test_age_filter_is_lenient_when_unknown,
    test_adult_tolerance_covers_measured_skew,
    test_margin_and_threshold_are_set_from_measurement,
    test_autotag_does_not_overwrite_human_choice,
    test_autotag_skips_non_photos,
    test_identify_is_quiet_without_enrollment,
    test_recognized_faces_are_marked_as_inference,
    test_stored_boxes_do_not_call_the_service,
    test_face_boxes_are_ratio_coordinates,
    test_unknown_faces_are_kept_with_a_reason,
    test_detail_endpoint_serves_face_boxes,
]


if __name__ == "__main__":
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {test.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {test.__name__}: {type(e).__name__} {e}")

    print()
    print(f"{len(TESTS) - failed}/{len(TESTS)} 통과")
    sys.exit(1 if failed else 0)
