"""TV 메뉴에서 고른 사건이 그대로 재생되는지 (기획안 06장 LG TV)

    python tests/test_tv_menu.py

거실 메뉴는 묶음 프리셋 한 줄과 모든 사건을 연대순으로 깐 한 줄로 되어 있다
(frontend/src/pages/TVViewPage.tsx). 예전에는 프리셋 여섯 개가 전부여서 그 묶음에
들지 못한 사건은 TV에서 누를 방법이 아예 없었다.

줄을 하나 더 깐 것만으로는 부족하다. 타일이 사건을 짚어 보내도 서버가 제목을
키워드로 다시 훑으면 엉뚱한 것이 섞인다 — "2003 하늘 초등학교 입학식"은 이름
"하늘"에 걸려 다른 해의 사진까지 끌어온다. 무엇을 고른 것인지 알 수 없어지고,
그건 리모컨밖에 없는 화면에서 가장 나쁜 실패다. 그래서 event_ids로 부르면 말을
다시 해석하지 않는다.

  - 시드된 사건 하나하나가 다 재생되는가 (메뉴에 오른 것이 다 열리는가)
  - 짚어 보낸 사건의 사진만 오는가 (같은 사람이 찍힌 다른 사건이 섞이지 않는가)
  - 사건 연대순 · 그 안에서 촬영순으로 오는가
  - 사진만 오는가 (거실 화면은 슬라이드를 <img>로 그린다)
  - 실제 HTTP 응답에도 실려 나가는가 (스키마에 빠뜨리면 화면이 못 받는다)
  - event_ids 없이 부르면 예전 경로가 그대로인가 (채팅·검색이 쓰는 길)

타이틀 화면에서 읽어 주는 이야기도 함께 본다. TV는 이야기를 따로 쓰지 않는다 —
Film이 [기록]으로 쓴 문장을 그대로 쓴다. 예전에는 캡션 목록만 넘겨 따로 썼고,
재료가 없으니 모델이 빈 곳을 스스로 메워 기록에 없는 장면이 거실 화면에서 사실처럼
읽혔다.

그래프를 읽기만 한다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import MediaType, NodeType  # noqa: E402
from backend.services import film_composer, memory_context, tv_curator  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _events() -> list[dict]:
    return sorted(graph_manager.get_events(), key=lambda e: e.get("date_start") or "")


def _photo_slides(slides: list[dict]) -> list[dict]:
    return [s for s in slides if s.get("media_id")]


def _slides(event_ids: list[str]) -> list[dict]:
    """고른 사건의 사진 슬라이드

    내레이션까지 만드는 create_journey를 부르지 않는다. 그건 사건마다 모델을 한 번
    부르는 일이라 이 파일이 몇 분씩 걸리고, 여기서 보려는 것은 "무엇이 슬라이드로
    오는가"다. 전체 경로는 아래 이야기·HTTP 테스트가 본다.
    """
    return _photo_slides(tv_curator._slides_for_events(event_ids))


def test_every_event_can_be_played():
    """메뉴에 오른 사건은 하나하나 다 열린다

    "모든 사건을 다 볼 수 있게"가 이 화면에서 뜻하는 것은, 목록에 보이는 것을
    누르면 무언가 재생된다는 것이다. 사진이 한 장도 오지 않는 사건이 있으면
    타일을 눌러도 아무 일이 없다.
    """
    for event in _events():
        slides = _slides([event["id"]])
        assert slides, f"{event['title']}: 사진 슬라이드가 없다"

    print(f"  사건 {len(_events())}개 전부 재생됨 OK")


def test_only_the_chosen_event_comes():
    """짚어 보낸 사건의 사진만 온다

    2003 입학식과 2015 졸업식은 둘 다 "하늘"이 주인공이다. 제목을 키워드로
    훑으면 서로 섞인다 — 입학식을 눌렀는데 졸업식 사진이 나오면 안 된다.
    """
    for event in _events():
        got = {s["event_id"] for s in _slides([event["id"]])}
        assert got == {event["id"]}, f"{event['title']}: 다른 사건이 섞였다 {got}"

    print("  고른 사건의 사진만 옴 OK")


def test_several_events_come_in_order():
    """여러 사건을 묶어 보내면 사건 연대순으로 온다

    프리셋(장소·사람 묶음)이 이렇게 부른다. 시간이 뒤섞이면 이야기가 아니라
    사진 더미가 된다.
    """
    events = _events()
    picked = [events[3]["id"], events[0]["id"], events[6]["id"]]  # 일부러 섞어서
    slides = _slides(picked)

    order: list[str] = []
    for slide in slides:
        if slide["event_id"] not in order:
            order.append(slide["event_id"])

    expected = [events[0]["id"], events[3]["id"], events[6]["id"]]
    assert order == expected, f"사건 순서가 어긋났다: {order}"

    dates = [s["date"] or "" for s in slides if s["event_id"] == expected[0]]
    assert dates == sorted(dates), f"한 사건 안의 촬영순이 어긋났다: {dates}"

    print(f"  사건 {len(expected)}개가 연대순으로 옴 OK")


def test_audio_and_video_are_not_slides():
    """사진만 슬라이드가 된다

    거실 화면은 슬라이드를 <img>로 그린다 (TVViewPage). 음성·영상 파일을 그
    자리에 넣으면 깨진 그림이 뜬다. 음성은 근거 화면에서 재생한다.
    """
    with_others = []
    for event in _events():
        kinds = {
            n.get("media_type")
            for n in graph_manager.get_connected_nodes(event["id"])
            if n.get("node_type") == NodeType.MEDIA
        }
        if kinds - {MediaType.PHOTO}:
            with_others.append(event)

    assert with_others, "사진 아닌 미디어가 붙은 사건이 없어 이 테스트는 아무것도 보지 않는다"

    for event in with_others:
        for slide in _slides([event["id"]]):
            media = graph_manager.get_node(slide["media_id"])
            assert media and media.get("media_type") == MediaType.PHOTO, (
                f"{event['title']}: 사진이 아닌 것이 슬라이드로 왔다 "
                f"({media.get('media_type') if media else '없음'})"
            )

    print(f"  사진 아닌 미디어가 붙은 사건 {len(with_others)}개, 슬라이드는 사진만 OK")


def test_the_story_is_the_film_story():
    """거실에서 듣는 이야기가 앱에서 보는 Film 이야기와 글자까지 같다

    두 화면이 같은 사건을 다르게 이야기하면 어느 쪽이 그 가족의 기억인지 알 수 없다.
    같은 기록이면 같은 문장이 나온다 (film_composer._stories).
    """
    event = _events()[0]
    journey = asyncio.run(
        tv_curator.create_journey(event["title"], "timeline", [event["id"]])
    )
    film = asyncio.run(film_composer.story(event["id"]))

    assert journey["narration"], "여정에 이야기가 없다"
    assert journey["narration"] == film, (
        "TV와 Film의 이야기가 갈렸다" + chr(10) + f"TV: {journey['narration']}" + chr(10) + f"Film: {film}"
    )

    print(f"  TV·Film 같은 이야기 OK ({len(film)}자)")


def test_the_record_table_is_not_copied_into_the_story():
    """넘긴 사실 목록을 본문에 베껴 오면 걷어낸다

    실제로 거실 화면의 이야기가 "사건: … / 날짜: … / 장소: … / 참여: …"로 시작했다.
    날짜·장소·사건명은 이미 자막에 있다. 이야기가 그것을 다시 나열하면 표가 된다.
    """
    leaked = chr(10).join(
        [
            "사건: 1998 부산 가족여행",
            "날짜: 1998-08-13",
            "장소: 부산 광안리 해수욕장",
            "참여: 김하늘, 박서연",
            "박서연의 기억: 하늘이가 물장구치던 게 제일 재미있었어",
            "",
            "엄마는 하늘이가 물장구치던 순간을 기억합니다.",
        ]
    )
    cleaned = memory_context.strip_prompt_marks(leaked)
    assert cleaned == "엄마는 하늘이가 물장구치던 순간을 기억합니다.", repr(cleaned)

    # 문장 안의 콜론은 건드리지 않는다 (사람이 쓴 기억에도 나온다)
    kept = "그날 아빠가 말했습니다: 바다가 잔잔하다."
    assert memory_context.strip_prompt_marks(kept) == kept, repr(kept)

    print("  베껴 온 사실 목록만 걷어냄 OK")


def test_http_accepts_event_ids():
    """실제 HTTP 응답에도 실려 나간다

    라우터 함수를 직접 부르면 요청 모델 파싱을 건너뛴다. TVJourneyRequest에
    event_ids를 빠뜨리면 화면이 보내는 것을 서버가 조용히 버린다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    event = _events()[1]
    with TestClient(app) as client:
        response = client.post(
            "/api/tv/journey",
            json={"query": event["title"], "style": "timeline", "event_ids": [event["id"]]},
        )
        assert response.status_code == 200, response.text
        slides = response.json()["slides"]

    got = {s["event_id"] for s in slides if s.get("media_id")}
    assert got == {event["id"]}, f"응답에 다른 사건이 섞였다: {got}"

    print(f"  HTTP로 event_ids 전달됨 OK ({event['title']})")


def test_query_path_still_works():
    """event_ids 없이 부르면 예전 경로 그대로

    채팅·검색은 문장으로 부른다 ("부산 여행"). 그 길을 막지 않았는지 본다.
    """
    journey = asyncio.run(tv_curator.create_journey("부산 여행", "timeline"))
    slides = _photo_slides(journey["slides"])
    assert slides, "문장으로 부른 여정에 사진이 없다"

    print(f"  문장으로 부른 여정 {len(slides)}장 OK")


TESTS = [
    test_every_event_can_be_played,
    test_only_the_chosen_event_comes,
    test_several_events_come_in_order,
    test_audio_and_video_are_not_slides,
    test_the_story_is_the_film_story,
    test_the_record_table_is_not_copied_into_the_story,
    test_http_accepts_event_ids,
    test_query_path_still_works,
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
