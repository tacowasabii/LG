"""Memory Film 구성 회귀 테스트

    python tests/test_film.py

기획안의 "진정성 원칙"이 데이터 구조에서 지켜지는지 본다.
  - 장면마다 원본 기록과 출처 문구가 붙는가
  - 사진에는 허용된 움직임만, 원본 영상에는 아무 효과도 붙지 않는가
  - 적어 놓은 효과가 화면이 실제로 거는 것과 같은가
  - 요청한 길이를 넘지 않고, 잘라낸 장면 수를 밝히는가
  - 내레이션이 기록에 있는 사실만 쓰는가 (LLM 없이도 성립해야 한다)
  - 배경 음악의 무드가 사건이 가진 말에서 나오고, 그 근거를 함께 밝히는가

LLM 키가 없어도 통과해야 한다. 내레이션은 폴백 경로로 검증한다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import film_composer, film_music  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행 (사진 3장 + 영상 1개)
# 세 길이 모두 채울 수 있는 사건. 자료가 적으면 긴 길이는 화면에서 잠긴다.
RICH_EVENT = "E07"  # 2021 하늘 결혼식 (사진 3장 + 영상 2개)


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
            assert effect in film_composer.ALLOWED_EFFECTS, effect
    print("  허용된 움직임만 사용:", {e for s in photo_scenes for e in s["ai_effects"]})


def test_effect_label_matches_the_motion_actually_applied():
    """적어 놓은 효과와 화면이 거는 효과가 같아야 한다

    예전에는 서버가 라벨만 정하고 화면이 장면 순서로 CSS를 따로 골라서, 두
    목록의 순서가 달라 네 경우 모두 어긋나 있었다 — "미세 배경 움직임"이라고
    적힌 장면에서 실제로는 줌 아웃이 걸렸다. 적힌 것이 사실이 아니면
    진정성 원칙이 장식이 된다.
    """
    board = asyncio.run(film_composer.compose(EVENT))
    labels = dict(film_composer.CAMERA_MOTIONS)

    for scene in board["scenes"]:
        if scene["motion_url"]:
            # 클립을 재생하는 장면에는 카메라 움직임을 겹치지 않는다
            assert scene["motion"] is None, scene
            assert scene["ai_effects"], "생성된 움직임을 밝히지 않았다"
            assert film_composer.GENERATED_MOTION_LABEL in scene["ai_effects"][0], scene
        elif scene["motion"]:
            assert scene["motion"] in labels, scene["motion"]
            assert scene["ai_effects"] == [labels[scene["motion"]]], scene
        else:
            # 움직임이 없으면 효과도 없다고 적혀 있어야 한다
            assert scene["ai_effects"] == [], scene
    print("  라벨과 적용 효과 일치 OK")


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


def test_selectable_lengths_each_make_a_different_film():
    """고를 수 있는 길이는 저마다 다른 영상이 된다

    사진 한 장이 머무는 시간에 상한이 있어서(PHOTO_MAX_SEC) 자료가 적으면 긴 길이를
    채울 수 없다. 그 길이는 max_sec 밖이라 화면에서 잠긴다. 잠기지 않은 길이끼리는
    총 길이가 서로 달라야 한다 — 같으면 눌러도 아무 일도 일어나지 않는 자리다.
    """
    boards = {
        sec: asyncio.run(film_composer.compose(RICH_EVENT, length_sec=sec))
        for sec in (30, 45, 60)
    }
    unlocked = [sec for sec, board in boards.items() if sec <= board["max_sec"]]
    assert unlocked == [30, 45, 60], f"이 사건은 60초까지 채워져야 한다: {unlocked}"

    totals = [boards[sec]["total_sec"] for sec in unlocked]
    assert len(set(totals)) == len(totals), f"길이를 바꿨는데 같은 영상이다: {totals}"

    # 뺀 장면이 없으면 고른 길이를 정확히 채운다 (남기지 않는다)
    for sec in unlocked:
        if boards[sec]["omitted_scenes"] == 0:
            assert boards[sec]["total_sec"] == sec, (sec, boards[sec]["total_sec"])
    print("  " + " · ".join(f"{s}초→{boards[s]['total_sec']}초" for s in unlocked))


def test_stretching_to_fill_respects_the_photo_cap():
    """길이를 채우려 사진을 늘려도 상한을 넘지 않는다 (정지 화면이 되는 자리)"""
    board = asyncio.run(film_composer.compose(RICH_EVENT, length_sec=60))
    cap = round(film_composer.PHOTO_MAX_SEC * film_composer.AUDIENCE_PACE["adult"])
    # 목소리가 붙은 장면은 그 길이에 맞추느라 상한을 넘을 수 있다 (줄이지 않는다)
    photos = [
        s
        for s in board["scenes"]
        if not s["media_id"].startswith("video_") and not s["voice_id"]
    ]
    assert photos, "사진 장면이 없다 (시드 확인)"
    assert max(s["duration_sec"] for s in photos) > round(
        film_composer.PHOTO_SEC * film_composer.AUDIENCE_PACE["adult"]
    ), "길이를 채우려 늘리지 않았다"
    for scene in photos:
        assert scene["duration_sec"] <= cap, (scene["media_id"], scene["duration_sec"], cap)
    print(f"  사진 최대 체류 {max(s['duration_sec'] for s in photos)}초 (상한 {cap}초)")


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


def test_music_carries_a_mood_and_its_reason():
    """배경 음악은 무드와 그것을 고른 근거를 함께 내려보낸다

    소리는 화면이 만든다 (frontend/src/lib/filmMusic.ts). 서버가 무드를 정하는
    이유는 화면에 적히는 근거와 실제로 나는 소리가 갈라지지 않게 하기 위해서다.
    """
    board = asyncio.run(film_composer.compose(EVENT))
    music = board["music"]

    assert music["mood"] in film_music.MOOD_LABEL, music
    # 라벨은 서버가 준 대로 쓴다. 화면이 조립하면 무드와 갈라진다.
    assert music["label"] == film_music.MOOD_LABEL[music["mood"]], music
    assert music["reason"], "무드를 고른 근거가 없다"
    print(f"  {EVENT} 음악: {music['label']} · {music['reason']}")


def test_memorial_records_never_get_bright_music():
    """추모하는 자리에는 밝은 음악을 깔지 않는다

    한 사건이 여러 낱말에 걸린다 — "추석 가족모임 겸 성묘"에는 잔치의 말과 추모의
    말이 함께 있다. 그때 추모가 이겨야 한다. 제사에 밝은 음악이 깔리는 것은 고치면
    되는 실수가 아니라 그 자리를 망치는 일이다.
    """
    event = {
        "title": "2019 할아버지 성묘",
        "description": "추석 가족모임 겸 성묘",
        "date_start": "2019-09-13",
    }
    picked = film_music.pick(event, place_name="경기 남양주 산소", today=date(2026, 8, 21))

    assert picked["mood"] == "solemn", picked
    print("  성묘 + 가족모임 ->", picked["label"], "·", picked["reason"])


def test_old_records_are_remembered_and_recent_ones_are_not():
    """한 세대가 지난 기록은 회상으로, 같은 자리라도 최근이면 그 자리의 소리로

    판단 순서를 못 박아 둔다. 20년이 넘은 기록은 그것 자체가 회상이라 낱말보다
    먼저 본다 — 순서를 정해 두지 않으면 같은 사건이 열 때마다 다르게 들린다.
    """
    today = date(2026, 8, 21)
    old = {"title": "1998 부산 가족여행", "date_start": "1998-08-13"}
    recent = {"title": "2025 부산 가족여행", "date_start": "2025-08-13"}

    assert film_music.pick(old, today=today)["mood"] == "nostalgic"
    assert film_music.pick(recent, today=today)["mood"] == "bright"
    print("  1998 여행 -> 회상하듯 · 2025 여행 -> 밝게")


def test_music_follows_the_audience_pace():
    """장면을 늦추면 음악도 늦춘다

    어르신에게 전환을 늦추면서 음악만 제 속도로 가면 화면과 소리가 갈라진다.
    """
    elder = asyncio.run(film_composer.compose(EVENT, audience="elder"))
    child = asyncio.run(film_composer.compose(EVENT, audience="child"))

    assert elder["music"]["pace"] > child["music"]["pace"], (
        elder["music"]["pace"],
        child["music"]["pace"],
    )
    print(f"  어르신 {elder['music']['pace']} > 아이 {child['music']['pace']}")


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
    test_effect_label_matches_the_motion_actually_applied,
    test_video_scenes_have_no_effects,
    test_length_is_respected_and_truncation_is_reported,
    test_selectable_lengths_each_make_a_different_film,
    test_stretching_to_fill_respects_the_photo_cap,
    test_audience_changes_pace,
    test_narration_uses_only_recorded_facts,
    test_music_carries_a_mood_and_its_reason,
    test_memorial_records_never_get_bright_music,
    test_old_records_are_remembered_and_recent_ones_are_not,
    test_music_follows_the_audience_pace,
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
