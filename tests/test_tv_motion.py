"""TV가 미리 만들어 둔 미세 모션 클립을 쓰는지 (기획안 06장 LG TV)

    python tests/test_tv_motion.py

Film과 TV가 같은 자산(data/motion/manifest.json)을 읽어야 한다. 만들어 둔 클립을
한 화면에서만 쓰면, 거실에서 보는 화면 — 이 기능이 가장 값을 내는 자리 — 이
가장 좋은 재료를 못 쓴다.

  - 매니페스트에 있는 사진의 슬라이드에 클립 경로가 실리는가
  - 없는 사진에는 아무것도 붙지 않는가 (화면이 카메라 움직임으로 떨어진다)
  - 인물 마스크를 쓴 클립임을 화면이 알 수 있는가 (라벨에 "인물은 원본"을 붙인다)
  - Film과 같은 매니페스트를 읽는가 (두 화면이 갈리지 않게)
  - 실제 HTTP 응답에도 실려 나가는가 (스키마에 빠뜨리면 화면이 못 본다)

배경 음악도 함께 본다. Film과 같은 낱말 표로 무드를 고르고(film_music), 여정
전체에 하나만 실린다 — 슬라이드마다 바꾸면 9초마다 곡이 갈린다.

매니페스트를 읽기만 하므로 그래프를 바꾸지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import film_composer, film_music, motion_clips, tv_curator  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

QUERY = "부산 여행"


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _journey(query: str = QUERY) -> dict:
    return asyncio.run(tv_curator.create_journey(query, "timeline"))


def _photo_slides(journey: dict) -> list[dict]:
    return [s for s in journey["slides"] if s.get("media_id")]


def test_manifest_clips_reach_the_slides():
    """매니페스트에 있는 사진의 슬라이드에 클립 경로가 실린다

    클립이 하나도 없는 저장소에서도 이 테스트는 성립해야 한다 (아직 안 만든
    상태가 정상이다). 그때는 "실린 것이 없다"를 확인하고 넘어간다.
    """
    clips = motion_clips.manifest()
    slides = _photo_slides(_journey())
    assert slides, "사진 슬라이드가 없다 (시드 확인)"

    with_clip = [s for s in slides if s.get("motion_url")]

    if not clips:
        assert not with_clip, "매니페스트가 비었는데 클립이 실렸다"
        print("  매니페스트가 비어 있음 — 클립 없이 동작 OK")
        return

    for slide in slides:
        expected = clips.get(slide["media_id"])
        if expected:
            assert slide["motion_url"] == expected["file"], slide
        else:
            assert not slide.get("motion_url"), slide

    print(f"  클립 {len(with_clip)}개가 슬라이드에 실림 OK")


def test_slides_without_clip_carry_nothing():
    """클립이 없는 사진에는 아무것도 붙지 않는다

    빈 문자열이나 원본 경로를 넣으면 화면이 그것을 클립으로 알고 <video>에
    물린다. 없으면 없어야 한다 — 화면은 그때 카메라 움직임으로 떨어진다.
    """
    clips = motion_clips.manifest()
    slides = _photo_slides(_journey())

    bare = [s for s in slides if s["media_id"] not in clips]
    assert bare, "모든 사진에 클립이 있어 이 경우를 확인할 수 없다"

    for slide in bare:
        assert not slide.get("motion_url"), slide
        assert not slide.get("motion_poster"), slide
        assert slide.get("subject_preserved") in (False, None), slide

    print(f"  클립 없는 사진 {len(bare)}개에 빈 값 OK")


def test_subject_preserved_flag_is_carried():
    """인물 마스크를 쓴 클립임을 화면이 알 수 있다

    마스크를 쓴 클립은 인물 영역이 원본 픽셀이다. 화면이 라벨에 "인물은 원본"을
    붙일 근거가 이 값이고, 빠뜨리면 생성물과 원본을 구분해 밝힐 수 없다.
    """
    clips = motion_clips.manifest()
    masked = {mid for mid, c in clips.items() if c.get("subject_preserved")}
    if not masked:
        print("  마스크를 쓴 클립이 없음 — 건너뜀")
        return

    slides = {s["media_id"]: s for s in _photo_slides(_journey())}
    checked = 0
    for media_id in masked:
        slide = slides.get(media_id)
        if not slide:
            continue
        assert slide.get("subject_preserved") is True, slide
        checked += 1

    print(f"  마스크 표시가 실림 OK ({checked}개 확인)")


def test_tv_and_film_read_the_same_manifest():
    """두 화면이 같은 자산을 읽는다

    각자 목록을 들면 한쪽만 갱신되어 Film에서는 움직이고 TV에서는 안 움직이는
    상태가 된다. 실제로 TV가 클립을 아예 안 쓰던 기간이 있었다.
    """
    clips = motion_clips.manifest()
    if not clips:
        print("  매니페스트가 비어 있음 — 건너뜀")
        return

    media_id = next(iter(clips))
    board = asyncio.run(film_composer.compose("E01"))
    film_urls = {s["media_id"]: s.get("motion_url") for s in board["scenes"]}

    slides = {s["media_id"]: s.get("motion_url") for s in _photo_slides(_journey())}

    if media_id in film_urls and media_id in slides:
        assert film_urls[media_id] == slides[media_id], (film_urls[media_id], slides[media_id])
        print(f"  Film과 TV가 같은 경로를 씀 OK: {slides[media_id]}")
    else:
        # 같은 사진이 두 화면에 다 나오지 않을 수 있다. 그때는 매니페스트 값과 대조한다.
        expected = clips[media_id]["file"]
        for source in (film_urls, slides):
            if media_id in source and source[media_id]:
                assert source[media_id] == expected, source[media_id]
        print("  각 화면이 매니페스트 값과 일치 OK")


def test_journey_carries_one_music_mood():
    """여정에는 무드가 하나 실린다 (슬라이드마다 바뀌지 않는다)

    소리는 화면이 만든다. 서버가 정하는 것은 무드와 그것을 고른 근거뿐이고,
    Film과 같은 표를 쓴다 — 표가 갈라지면 같은 추억이 거실에서 다르게 들린다.
    """
    journey = _journey()
    music = journey["music"]

    assert music, "여정에 배경 음악 무드가 없다"
    assert music["mood"] in film_music.MOOD_LABEL, music
    assert music["label"] == film_music.MOOD_LABEL[music["mood"]], music
    assert music["reason"], "무드를 고른 근거가 없다"
    # 슬라이드에는 음악을 싣지 않는다. 장면마다 있으면 장면마다 바꾸게 된다.
    for slide in journey["slides"]:
        assert "music" not in slide, slide
    print(f"  {QUERY}: {music['label']} · {music['reason']}")


def test_a_memorial_record_in_the_journey_wins():
    """추모하는 기록이 하나라도 섞이면 그쪽 소리로 깔린다

    성묘 사진 한 장이 든 여정에 밝은 음악을 깔면, 그 한 장이 지나갈 동안만
    어울리지 않는 것이 아니라 그 사진을 그런 소리로 덮은 것이 된다.
    """
    bright = {"id": "T1", "title": "2017 첫 가족 캠핑", "date_start": "2017-05-04"}
    warm = {"id": "T2", "title": "2024 부모님 환갑 가족모임", "date_start": "2024-10-05"}
    memorial = {"id": "T3", "title": "2023 할아버지 성묘", "date_start": "2023-09-28"}

    without = film_music.pick_journey([bright, warm], today=date(2026, 8, 21))
    with_memorial = film_music.pick_journey([bright, warm, memorial], today=date(2026, 8, 21))

    assert without["mood"] != "solemn", without
    assert with_memorial["mood"] == "solemn", with_memorial
    assert "성묘" in with_memorial["reason"], with_memorial["reason"]
    print("  캠핑+환갑 ->", without["label"], "· 성묘가 섞이면 ->", with_memorial["label"])


def test_music_counts_events_not_photos():
    """무드는 사진 수가 아니라 추억 수로 센다

    사진이 열 장인 추억과 한 장인 추억이 같은 무게여야 한다. 사진으로 세면 앨범이
    두꺼운 추억 하나가 여정 전체의 소리를 혼자 정한다.
    """
    journey = _journey("아빠와의 추억")
    events, _places = tv_curator._slide_events(journey["slides"])
    event_ids = [e["id"] for e in events]

    assert len(event_ids) == len(set(event_ids)), f"같은 추억을 여러 번 셌다: {event_ids}"
    photo_count = len([s for s in journey["slides"] if s.get("media_id")])
    assert photo_count >= len(event_ids), (photo_count, len(event_ids))
    print(f"  사진 {photo_count}장 -> 추억 {len(event_ids)}개로 셈")


def test_http_response_carries_music():
    """배경 음악이 실제 HTTP 응답에 실려 나간다

    라우터의 _journey가 필드를 하나씩 적는다. 빠뜨리면 서버는 무드를 고르는데
    화면은 못 받아 음악 없이 재생한다 — 미세 모션 필드에서 실제로 그랬다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        response = client.post("/api/tv/journey", json={"query": QUERY, "style": "timeline"})
        assert response.status_code == 200, response.text
        music = response.json().get("music")

    assert music, "응답에 music이 없다"
    assert music["mood"] in film_music.MOOD_LABEL, music
    assert music["label"] and music["reason"], music
    print("  HTTP 응답에 배경 음악 실림 OK:", music["label"])


def test_http_response_carries_motion_fields():
    """실제 HTTP 응답에 실려 나간다

    라우터 함수를 직접 부르면 응답 모델 직렬화를 건너뛴다. TVSlide 스키마에
    필드를 빠뜨리면 서버는 채우는데 화면은 못 받는다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        response = client.post("/api/tv/journey", json={"query": QUERY, "style": "timeline"})
        assert response.status_code == 200, response.text
        slides = response.json()["slides"]

    keys = {"motion_url", "motion_poster", "subject_preserved"}
    photo = [s for s in slides if s.get("media_id")]
    assert photo, "사진 슬라이드가 없다"
    for slide in photo:
        missing = keys - set(slide)
        assert not missing, f"응답에 빠진 필드: {missing}"

    print("  HTTP 응답에 모션 필드 실림 OK")


TESTS = [
    test_manifest_clips_reach_the_slides,
    test_slides_without_clip_carry_nothing,
    test_subject_preserved_flag_is_carried,
    test_tv_and_film_read_the_same_manifest,
    test_http_response_carries_motion_fields,
    test_journey_carries_one_music_mood,
    test_a_memorial_record_in_the_journey_wins,
    test_music_counts_events_not_photos,
    test_http_response_carries_music,
]


if __name__ == "__main__":
    _require_seeded_graph()

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
