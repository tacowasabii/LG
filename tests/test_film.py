"""Memory Film 구성 회귀 테스트

    python tests/test_film.py

기획안의 "진정성 원칙"이 데이터 구조에서 지켜지는지 본다.
  - 장면마다 원본 기록과 출처 문구가 붙는가
  - 사진에는 허용된 움직임만, 원본 영상에는 아무 효과도 붙지 않는가
  - 요청한 길이를 넘지 않고, 잘라낸 장면 수를 밝히는가
  - 내레이션이 기록에 있는 사실만 쓰는가 (LLM 없이도 성립해야 한다)

LLM 키가 없어도 통과해야 한다. 내레이션은 폴백 경로로 검증한다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import film_composer  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행 (사진 3장 + 영상 1개)


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def test_scenes_carry_source_and_media_id():
    """장면에서 원본으로 되짚을 수 있어야 한다"""
    board = asyncio.run(film_composer.compose(EVENT))

    assert board, "스토리보드가 비었다"
    assert board["scenes"], "장면이 없다"
    for scene in board["scenes"]:
        assert graph_manager.get_node(scene["media_id"]), f"없는 원본: {scene['media_id']}"
        assert scene["source_label"], "출처 문구가 없다"
        assert scene["file_path"].startswith("/media-files/"), scene["file_path"]
    print("  장면", len(board["scenes"]), "개 · 원본 연결 OK")


def test_photo_effects_are_within_allowed_range():
    """사진에는 기획안이 허용한 움직임만 쓴다 (인물·행동을 만들지 않는다)"""
    board = asyncio.run(film_composer.compose(EVENT))

    photo_scenes = [s for s in board["scenes"] if s["ai_effects"]]
    assert photo_scenes, "효과가 붙은 장면이 없다"
    for scene in photo_scenes:
        for effect in scene["ai_effects"]:
            assert effect in film_composer.ALLOWED_MOTIONS, effect
    print("  허용된 움직임만 사용:", {e for s in photo_scenes for e in s["ai_effects"]})


def test_video_scenes_have_no_effects():
    """원본 영상은 손대지 않는다"""
    board = asyncio.run(film_composer.compose(EVENT))

    video_scenes = [s for s in board["scenes"] if s["media_id"].startswith("video_")]
    assert video_scenes, "이 사건에 영상이 없다 (시드 확인)"
    for scene in video_scenes:
        assert scene["ai_effects"] == [], scene["ai_effects"]
        assert "원본 영상" in scene["source_label"], scene["source_label"]
    print("  영상", len(video_scenes), "개 · 효과 없음 OK")


def test_length_is_respected_and_truncation_is_reported():
    """짧은 길이를 고르면 넘치지 않고, 몇 장면을 뺐는지 밝힌다"""
    short = asyncio.run(film_composer.compose(EVENT, length_sec=30))
    long = asyncio.run(film_composer.compose(EVENT, length_sec=60))

    assert short["total_sec"] <= 30, short["total_sec"]
    assert len(short["scenes"]) <= len(long["scenes"]), "짧은 쪽이 더 많다"
    if len(short["scenes"]) < len(long["scenes"]):
        assert short["omitted_scenes"] > 0, "잘라냈는데 밝히지 않았다"
    print(f"  30초: {short['total_sec']}초/{len(short['scenes'])}장면 (생략 {short['omitted_scenes']})")
    print(f"  60초: {long['total_sec']}초/{len(long['scenes'])}장면")


def test_audience_changes_pace():
    """어르신에게는 천천히, 아이에게는 빠르게 (같은 자료, 다른 호흡)"""
    child = asyncio.run(film_composer.compose(EVENT, length_sec=60, audience="child"))
    elder = asyncio.run(film_composer.compose(EVENT, length_sec=60, audience="elder"))

    child_first = child["scenes"][0]["duration_sec"]
    elder_first = elder["scenes"][0]["duration_sec"]
    assert elder_first > child_first, (child_first, elder_first)
    print(f"  아이용 {child_first}초 · 어르신용 {elder_first}초")


def test_narration_uses_only_recorded_facts():
    """내레이션은 기록에 있는 것만 쓴다 (LLM 폴백 경로 검증)"""
    event = graph_manager.get_node(EVENT)
    memories = [
        n
        for n in graph_manager.get_connected_nodes(EVENT)
        if n.get("node_type") == "memory"
    ]
    persons = [
        n
        for n in graph_manager.get_connected_nodes(EVENT)
        if n.get("node_type") == "person"
    ]

    plain = film_composer._plain_narration(event, memories, persons, "부산 광안리 해수욕장")

    assert "1998년 8월" in plain, plain
    assert "부산 광안리 해수욕장" in plain, plain
    # 기억 문장은 그대로 인용한다 (요약하거나 바꿔 쓰지 않는다)
    assert memories[0]["content"] in plain, plain
    print("  폴백 내레이션 OK:", plain[:60], "…")


def test_missing_event_returns_none():
    """자료가 없는 사건은 억지로 만들지 않는다"""
    assert asyncio.run(film_composer.compose("없는-사건")) is None
    print("  없는 사건 처리 OK")


def test_anniversaries_are_upcoming_and_sorted():
    """기념일은 다가오는 것만, 가까운 순으로"""
    items = film_composer.anniversaries(limit=8)

    assert items, "기념일이 비었다"
    assert all(item["days_left"] >= 0 for item in items), "지난 날짜가 섞였다"
    assert items == sorted(items, key=lambda i: i["days_left"]), "정렬이 어긋났다"
    for item in items:
        assert graph_manager.get_node(item["event_id"]), item["event_id"]
        assert "주년" in item["label"], item["label"]
    print("  기념일", len(items), "개 · 가장 가까운 것:", items[0]["label"], items[0]["days_left"], "일 남음")


def test_http_film_endpoints():
    """실제 HTTP에서 응답 모델이 그대로 나가는지"""
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        res = client.post("/api/film", json={"event_id": EVENT, "length_sec": 45, "audience": "adult"})
        assert res.status_code == 200, res.text
        board = res.json()
        assert board["scenes"], board
        assert board["title"], board

        missing = client.post("/api/film", json={"event_id": "없는-사건"})
        assert missing.status_code == 404, missing.status_code

        anniv = client.get("/api/film/anniversaries")
        assert anniv.status_code == 200, anniv.text
        assert anniv.json(), "기념일이 비었다"
    print("  HTTP 응답 OK: POST /api/film · GET /api/film/anniversaries")


TESTS = [
    test_scenes_carry_source_and_media_id,
    test_photo_effects_are_within_allowed_range,
    test_video_scenes_have_no_effects,
    test_length_is_respected_and_truncation_is_reported,
    test_audience_changes_pace,
    test_narration_uses_only_recorded_facts,
    test_missing_event_returns_none,
    test_anniversaries_are_upcoming_and_sorted,
    test_http_film_endpoints,
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

    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} 통과")
    sys.exit(1 if failures else 0)
