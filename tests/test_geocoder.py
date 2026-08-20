"""좌표 -> 대략적인 지명 회귀 테스트

    python tests/test_geocoder.py

지명은 짐작이다. 그래서 "맞았는가"보다 "짐작인 것이 드러나는가"를 본다.
  - 아는 곳은 알아보는가 (해운대·경주·전주·제주)
  - 모르는 곳을 아는 척하지 않는가 (해외·먼바다는 None)
  - 이름만으로 갈리지 않는 곳에 시·도가 붙는가 (중구·고성·광주)
  - 너무 넓은 짐작("경북")을 장소 이름으로 쓰지 않는가
  - 초안의 근거 줄에 위도·경도 숫자가 남지 않는가

시드된 그래프가 필요하지 않다 — 표만 읽는다. 마지막 두 개만 그래프를 쓴다.
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import geocoder, memory_drafter, vision  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402
from backend.models.graph_models import MediaNode, MediaType, SourceType  # noqa: E402


class _NoModel:
    """모델을 부르지 않는 상태로 초안을 만든다

    여기서 확인하는 것은 좌표를 무엇으로 바꿔 보여주는지다. 제목 문장을
    누가 썼는지는 상관이 없고, 실제 호출을 끼우면 테스트가 네트워크와 요금에
    묶인다 — 키가 없는 자리에서도 같은 결과가 나와야 한다.
    """

    def __enter__(self):
        self._enabled = memory_drafter.llm_client.is_enabled
        self._describe = vision.describe_missing

        async def no_vision(media_nodes, limit=None):
            return 0

        memory_drafter.llm_client.is_enabled = lambda purpose=None: False
        vision.describe_missing = no_vision
        return self

    def __exit__(self, *exc):
        memory_drafter.llm_client.is_enabled = self._enabled
        vision.describe_missing = self._describe
        return False


def test_known_places_are_recognized():
    cases = [
        ((35.1587, 129.1604), "부산 해운대구"),
        ((37.5796, 126.9770), "서울 종로구"),
        ((35.7900, 129.3320), "경북 경주"),
        ((35.8150, 127.1530), "전북 전주"),
        ((33.4590, 126.9425), "제주 성산"),
        ((34.8330, 128.4360), "경남 통영"),
    ]
    for (lat, lng), expected in cases:
        got = geocoder.coarse_name(lat, lng)
        assert got == expected, f"{lat},{lng} -> {got} (기대: {expected})"


def test_unknown_coordinates_stay_unknown():
    """모르는 곳을 아는 척하지 않는다"""
    for lat, lng in [
        (35.6586, 139.7454),  # 도쿄
        (48.8584, 2.2945),  # 파리
        (37.5, 132.5),  # 동해 먼바다
        (0.0, 0.0),
    ]:
        assert geocoder.coarse_place(lat, lng) is None, f"{lat},{lng}에 이름이 붙었다"


def test_missing_and_broken_coordinates_are_safe():
    assert geocoder.coarse_place(None, None) is None
    assert geocoder.coarse_place(35.1, None) is None
    assert geocoder.coarse_place("여기", 129.0) is None
    assert geocoder.coarse_place(999.0, 129.0) is None


def test_ambiguous_names_carry_their_region():
    """이름만으로는 갈리지 않는 곳이 있다

    중구는 여섯 곳, 고성은 두 곳, 광주는 광역시와 경기도에 하나씩 있다.
    시·도를 떼면 지도의 점과 이름이 어긋난다.
    """
    assert geocoder.coarse_name(37.5640, 126.9970) == "서울 중구"
    assert geocoder.coarse_name(35.1060, 129.0320) == "부산 중구"
    assert geocoder.coarse_name(38.3810, 128.4680) == "강원 고성"
    assert geocoder.coarse_name(34.9730, 128.3220) == "경남 고성"
    assert geocoder.coarse_name(35.1520, 126.8900) == "광주 서구"
    assert geocoder.coarse_name(37.4300, 127.2550) == "경기 광주"


def test_wide_guesses_are_not_place_names():
    """시·도까지만 짚은 것은 장소 칸에 넣지 않는다

    "경북"은 장소가 아니다. 그 넓이를 이름으로 저장하면 지도에 찍힌 점과
    이름이 어긋난다.
    """
    # 오대산 서쪽 산악 지대. 표의 어느 시·군에서도 30km 넘게 떨어져 있어
    # 시·도까지만 짚힌다.
    guess = geocoder.coarse_place(37.70, 128.30)
    assert guess is not None, "국내 좌표인데 아무것도 짚지 못했다"
    assert guess.precision == "region", f"precision={guess.precision}"
    assert not guess.usable_as_place, "너무 넓은 짐작을 장소 이름으로 쓰려 한다"

    close = geocoder.coarse_place(35.1587, 129.1604)
    assert close is not None and close.usable_as_place


def _make_media(lat: float, lng: float) -> str:
    node = MediaNode(
        media_type=MediaType.PHOTO,
        file_path="/media-files/test_geocoder.jpg",
        original_filename="test_geocoder.jpg",
        source=SourceType.EXIF,
        exif_date="2024-05-04T10:00:00",
        exif_lat=lat,
        exif_lng=lng,
    )
    graph_manager.add_media(node)
    return node.id


def test_draft_evidence_has_no_raw_coordinates():
    """초안의 근거 줄에 위도·경도 숫자가 남지 않는다"""
    media_id = _make_media(35.1587, 129.1604)
    try:
        with _NoModel():
            draft = asyncio.run(memory_drafter.draft([media_id]))
    finally:
        graph_manager.delete_node(media_id)

    labels = [item["label"] for item in draft["evidence"]]
    assert "좌표" not in labels, f"좌표 줄이 그대로 있다: {labels}"

    location = next((item for item in draft["evidence"] if item["label"] == "위치"), None)
    assert location is not None, f"위치 줄이 없다: {labels}"
    assert "35.15" not in location["detail"], f"소수점이 남았다: {location['detail']}"
    assert "129.16" not in location["detail"], f"소수점이 남았다: {location['detail']}"
    assert "근처" in location["detail"], f"짐작임을 밝히지 않는다: {location['detail']}"


def test_draft_suggests_a_place_name_from_coordinates():
    """장소 칸에 채울 이름을 좌표에서 만들어 준다 (id는 없다)"""
    media_id = _make_media(35.8150, 127.1530)  # 전주
    try:
        with _NoModel():
            draft = asyncio.run(memory_drafter.draft([media_id]))
    finally:
        graph_manager.delete_node(media_id)

    # 그래프에 이미 가까운 장소가 있으면 그걸 쓴다. 그때는 짐작이 필요 없다.
    if draft.get("place"):
        assert draft.get("place_guess") is None, "기존 장소가 있는데 짐작까지 보냈다"
        return

    guess = draft.get("place_guess")
    assert guess is not None, "좌표가 있는데 장소 이름을 짐작하지 않았다"
    assert guess["name"] == "전북 전주", guess
    assert "id" not in guess, "짐작에 id를 붙이면 없는 장소를 가리킨다"


TESTS = [
    test_known_places_are_recognized,
    test_unknown_coordinates_stay_unknown,
    test_missing_and_broken_coordinates_are_safe,
    test_ambiguous_names_carry_their_region,
    test_wide_guesses_are_not_place_names,
    test_draft_evidence_has_no_raw_coordinates,
    test_draft_suggests_a_place_name_from_coordinates,
]


if __name__ == "__main__":
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
