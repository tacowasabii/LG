"""사진첩 회귀 테스트

    python tests/test_album.py

사진첩은 가족 사진을 가장 많이, 가장 빠르게 내보내는 통로다. 그래서 여기서
보는 것은 "목록이 나오는가"가 아니라 아래 다섯 가지다.

  - 음성은 오지 않고, 촬영일을 모르는 사진도 빠지지 않는가
  - 연도·인물·추억·연결 상태·검색 필터가 함께 걸리는가
  - 추억별로 묶었을 때 한 추억의 사진이 흩어지지 않고, 페이지를 넘겨도 그대로인가
  - 인물 필터가 사람이 지목한 태그만 보는가 (AI가 사진을 누구 것으로 정하지 않는다)
  - 커서로 넘긴 페이지에 겹침도 빠짐도 없는가
  - 비공개 사진이 목록·개수·연도 목록에서 모두 빠지는가
  - 지운 원본이 목록·개수에서 빠지고, 남의 원본은 지워지지 않는가
  - 여러 장을 한 번에 지울 때 막힌 것만 남고 그 이유가 함께 오는가

그래프를 실제로 바꾸므로 끝에서 원래대로 되돌린다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import (  # noqa: E402
    Edge,
    EventNode,
    MediaNode,
    MediaType,
    RelationType,
    Visibility,
)
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend.routers.media import get_album  # noqa: E402
from backend.services import album  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

VIEWER = "P01"  # 김민수 (가족 관리자)
OTHER = "P03"  # 김하늘
PRIVATE_MEDIA = "E01_002"  # 1998 부산 여행 사진 하나를 비공개로 돌려 본다

# 테스트가 직접 넣는 기록. 시드에는 없는 상태(추억 미연결·음성)를 만들기 위한 것이다.
TEMP_UNLINKED = "album_test_unlinked"
TEMP_AUDIO = "album_test_audio"


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _make_temp_photo(
    media_id: str, exif_date: Optional[str], owner_id: str = VIEWER
) -> None:
    """시험용 사진 한 장

    file_path가 가리키는 파일은 없다. 삭제 시험이 실제 시드 사진을 지우면
    데모 데이터가 깨지므로, 지워도 되는 것만 지운다 (라우터는 파일이 없으면
    노드만 지운다).
    """
    graph_manager.add_media(
        MediaNode(
            id=media_id,
            media_type=MediaType.PHOTO,
            file_path=f"/media-files/{media_id}.jpg",
            original_filename=f"{media_id}.jpg",
            exif_date=exif_date,
            owner_id=owner_id,
        )
    )


def _drop(*media_ids: str) -> None:
    for media_id in media_ids:
        if graph_manager.get_node(media_id):
            graph_manager.delete_node(media_id)


def _setup():
    """시드에 없는 두 가지 상태를 만든다

    미분류 사진: 시드된 사진은 모두 추억에 붙어 있어 "미분류" 필터를 확인할 수 없다.
    음성:        사진첩에서 빠지는지 보려면 하나라도 있어야 한다.
    """
    _make_temp_photo(TEMP_UNLINKED, "2019-06-01T10:00:00+09:00")
    graph_manager.add_media(
        MediaNode(
            id=TEMP_AUDIO,
            media_type=MediaType.AUDIO,
            file_path="/media-files/album_test_audio.webm",
            original_filename="album_test_audio.webm",
            duration_sec=12.0,
            owner_id=VIEWER,
        )
    )


def _restore():
    """공개 범위를 원래대로 (테스트 중간에도 부른다)"""
    graph_manager.update_node(
        PRIVATE_MEDIA,
        {"visibility": Visibility.FAMILY.value, "allowed_ids": [], "owner_id": None},
    )


def _cleanup():
    """테스트가 넣은 기록을 걷어낸다 (맨 끝에서 한 번만)"""
    _restore()
    _drop(TEMP_UNLINKED, TEMP_AUDIO)


def _ids(result):
    return [item["id"] for item in result["items"]]


# --- 무엇이 사진첩에 오는가 ---------------------------------------------------


def test_album_has_photos_and_videos_only():
    """음성은 사진첩에 오지 않는다 (훑어볼 그림이 없다)"""
    result = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)
    types = {item["media_type"] for item in result["items"]}

    assert types <= {"photo", "video"}, types
    assert TEMP_AUDIO not in _ids(result), "음성이 사진첩에 들어왔다"
    assert "video" in types, "영상이 사진첩에서 빠졌다"
    print("  종류", types, "· 음성 제외 OK")


def test_undated_photos_are_kept_and_pushed_last():
    """촬영일을 모르는 기록도 누락되지 않고, 촬영일 순의 맨 뒤에 선다"""
    result = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)
    flags = [item["has_exif"] for item in result["items"]]
    undated = [item for item in result["items"] if not item["has_exif"]]

    assert undated, "촬영일이 없는 기록이 하나도 없어 확인할 수 없다 (시드 영상 확인)"
    # True들이 먼저, False들이 뒤에 — 섞이면 정렬이 무너진 것이다
    assert flags == sorted(flags, reverse=True), "촬영일 없는 기록이 중간에 섞였다"
    for item in undated:
        # 촬영일을 모를 때도 줄을 세울 값은 준다 (올린 시각)
        assert item["captured_at"], f"정렬할 값이 없다: {item['id']}"
    print("  촬영일 미상", len(undated), "건 · 맨 뒤 OK")


def test_captured_order_uses_exif_not_upload_time():
    """정렬 기준은 촬영일이다 (방금 올린 1998년 사진이 맨 앞에 오지 않는다)"""
    dated = [
        item
        for item in album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)["items"]
        if item["has_exif"]
    ]
    captured = [item["captured_at"] for item in dated]

    assert captured == sorted(captured, reverse=True), "촬영일 최신순이 아니다"

    oldest_first = [
        item["captured_at"]
        for item in album.query(viewer_id=VIEWER, sort="captured_asc", limit=album.MAX_LIMIT)[
            "items"
        ]
        if item["has_exif"]
    ]
    assert oldest_first == sorted(oldest_first), "오래된순이 아니다"
    print("  최신순", captured[0][:10], "→", captured[-1][:10])


# --- 필터 --------------------------------------------------------------------


def test_type_filter():
    """사진만 · 영상만"""
    photos = album.query(viewer_id=VIEWER, types="photo", limit=album.MAX_LIMIT)
    videos = album.query(viewer_id=VIEWER, types="video", limit=album.MAX_LIMIT)
    both = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)

    assert {i["media_type"] for i in photos["items"]} == {"photo"}
    assert {i["media_type"] for i in videos["items"]} == {"video"}
    assert photos["total"] + videos["total"] == both["total"]
    print(f"  사진 {photos['total']} · 영상 {videos['total']}")


def test_year_filter_uses_capture_year():
    """연도는 촬영 연도다. 올린 연도로 걸리면 1998년 사진이 2026년에 들어간다"""
    result = album.query(viewer_id=VIEWER, year=2015, limit=album.MAX_LIMIT)

    assert result["items"], "2015년 사진이 없다 (시드 확인)"
    for item in result["items"]:
        assert item["captured_at"][:4] == "2015", item["captured_at"]
        assert item["has_exif"], "촬영일을 모르는 기록이 연도 필터에 걸렸다"
    print("  2015년", result["total"], "건")


def test_year_options_survive_a_year_selection():
    """연도를 고른 뒤에도 다른 연도로 옮겨갈 수 있어야 한다"""
    all_years = album.query(viewer_id=VIEWER)["available_years"]
    picked = album.query(viewer_id=VIEWER, year=2015)["available_years"]

    assert picked == all_years, "연도를 고르자 나머지 연도가 사라졌다"
    assert all_years == sorted(all_years, reverse=True), "연도가 최신순이 아니다"
    print("  연도", all_years)


def test_person_filter_only_uses_human_tags():
    """인물 필터는 사람이 지목한 태그만 본다 (AI가 사진 주인을 정하지 않는다)"""
    result = album.query(viewer_id=VIEWER, person_id="P05", limit=album.MAX_LIMIT)

    assert result["items"], "P05가 지목된 사진이 없다 (시드 확인)"
    for item in result["items"]:
        assert "P05" in [p["id"] for p in item["people"]], item["id"]

    # 아무도 지목되지 않은 사진은 어떤 인물 필터에도 걸리지 않는다
    untagged = album.query(viewer_id=VIEWER, q="album_test_unlinked")["items"]
    assert untagged and untagged[0]["people"] == [], "테스트 사진에 태그가 붙어 있다"
    assert TEMP_UNLINKED not in _ids(
        album.query(viewer_id=VIEWER, person_id="P05", limit=album.MAX_LIMIT)
    ), "태그 없는 사진이 인물 필터에 걸렸다"
    print("  P05", result["total"], "건 · 태그 없는 사진은 제외 OK")


def test_event_status_filter():
    """추억에 붙은 것 / 아직 안 붙은 것"""
    linked = album.query(viewer_id=VIEWER, event_status="linked", limit=album.MAX_LIMIT)
    unlinked = album.query(viewer_id=VIEWER, event_status="unlinked", limit=album.MAX_LIMIT)
    both = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)

    assert all(i["event"] for i in linked["items"]), "추억이 없는 기록이 섞였다"
    assert all(i["event"] is None for i in unlinked["items"]), "추억이 있는 기록이 섞였다"
    assert TEMP_UNLINKED in _ids(unlinked), "미분류 사진이 미분류 목록에 없다"
    assert linked["total"] + unlinked["total"] == both["total"]
    # 추억에 연결되지 않은 사진도 기본 목록에서 빠지지 않는다
    assert TEMP_UNLINKED in _ids(both), "미분류 사진이 전체 목록에서 빠졌다"
    print(f"  연결됨 {linked['total']} · 미분류 {unlinked['total']}")


def test_search_covers_filename_event_person_place():
    """검색은 파일명·추억 제목·인물 이름·장소명을 함께 본다"""
    sample = album.query(viewer_id=VIEWER, year=1998, limit=album.MAX_LIMIT)["items"][0]

    for label, needle in (
        ("파일명", sample["original_filename"]),
        ("추억 제목", sample["event"]["title"] if sample["event"] else None),
        ("인물", sample["people"][0]["name"] if sample["people"] else None),
        ("장소", sample["place"]["name"] if sample["place"] else None),
    ):
        if not needle:
            continue
        hit = album.query(viewer_id=VIEWER, q=needle, limit=album.MAX_LIMIT)
        assert sample["id"] in _ids(hit), f"{label}으로 찾지 못했다: {needle}"

    assert album.query(viewer_id=VIEWER, q="없을리없는말없음")["total"] == 0
    print("  파일명 · 추억 · 인물 · 장소 검색 OK")


def test_filters_combine():
    """필터는 함께 걸린다 (하나가 다른 하나를 덮지 않는다)"""
    combined = album.query(
        viewer_id=VIEWER,
        types="photo",
        year=1998,
        person_id="P01",
        event_status="linked",
        limit=album.MAX_LIMIT,
    )

    assert combined["items"], "조건에 맞는 사진이 없다 (시드 확인)"
    for item in combined["items"]:
        assert item["media_type"] == "photo"
        assert item["captured_at"][:4] == "1998"
        assert "P01" in [p["id"] for p in item["people"]]
        assert item["event"]
    print("  사진 + 1998 + P01 + 연결됨 =", combined["total"], "건")


# --- 추억별 ------------------------------------------------------------------


def test_event_filter_narrows_to_one_event():
    """추억 하나만 골라 본다"""
    result = album.query(viewer_id=VIEWER, event_id="E06", limit=album.MAX_LIMIT)

    assert result["items"], "E06에 붙은 사진이 없다 (시드 확인)"
    for item in result["items"]:
        assert item["event"] and item["event"]["id"] == "E06", item["id"]
    assert TEMP_UNLINKED not in _ids(result), "미분류 사진이 추억 필터에 걸렸다"

    # 다른 조건과 함께 걸린다 (하나가 다른 하나를 덮지 않는다)
    photos_only = album.query(
        viewer_id=VIEWER, event_id="E06", types="photo", limit=album.MAX_LIMIT
    )
    assert all(i["media_type"] == "photo" for i in photos_only["items"])
    assert photos_only["total"] <= result["total"], (photos_only["total"], result["total"])
    print("  E06", result["total"], "건 · 사진만", photos_only["total"], "건")


def test_event_options_survive_an_event_selection():
    """추억을 고른 뒤에도 다른 추억으로 옮겨갈 수 있어야 한다"""
    all_events = album.query(viewer_id=VIEWER)["available_events"]
    picked = album.query(viewer_id=VIEWER, event_id="E06")["available_events"]

    assert [e["id"] for e in picked] == [e["id"] for e in all_events], (
        "추억을 고르자 나머지 추억이 사라졌다"
    )
    dates = [e["date"] or "" for e in all_events]
    assert dates == sorted(dates, reverse=True), f"추억이 시간순이 아니다: {dates}"

    # 개수가 함께 온다 — 고르기 전에 몇 장인지 보여야 빈 화면을 누르지 않는다
    e06 = next(e for e in all_events if e["id"] == "E06")
    assert e06["count"] == album.query(viewer_id=VIEWER, event_id="E06")["total"]
    assert e06["date"], "추억 날짜가 비었다"
    print(f"  추억 {len(all_events)}개 · {e06['title']} {e06['count']}장")


def test_selected_event_stays_in_the_options_at_zero():
    """다른 조건 때문에 0장이 된 추억도 목록에 남는다

    사라지면 화면에서 그 추억 필터를 끄는 길이 없어진다 (고른 값은 주소에 있다).
    """
    facets = album.query(viewer_id=VIEWER, event_id="E01", year=2015)["available_events"]
    picked = [f for f in facets if f["id"] == "E01"]

    assert picked, "고른 추억이 목록에서 사라졌다"
    assert picked[0]["count"] == 0, picked
    print("  0장이 된 추억도 목록에 남음 OK")


def test_event_grouping_keeps_each_event_together():
    """추억별로 묶으면 한 추억의 사진이 흩어지지 않는다"""
    items = album.query(viewer_id=VIEWER, group_by="event", limit=album.MAX_LIMIT)["items"]
    assert items, "사진이 없다 (시드 확인)"

    order: list[str] = []
    for item in items:
        key = item["event"]["id"] if item["event"] else ""
        if not order or order[-1] != key:
            assert key not in order, f"{key or '미분류'} 묶음이 두 번 나왔다"
            order.append(key)

    # 어느 추억에도 붙지 않은 사진은 추억 묶음이 아니다 — 언제나 맨 뒤
    assert order[-1] == "", order
    assert items[-1]["id"] == TEMP_UNLINKED or items[-1]["event"] is None

    # 묶음의 순서는 추억 날짜 최신순
    dates = {e["id"]: e["date"] or "" for e in album.query(viewer_id=VIEWER)["available_events"]}
    grouped_dates = [dates[event_id] for event_id in order if event_id]
    assert grouped_dates == sorted(grouped_dates, reverse=True), grouped_dates
    print(f"  추억 {len(order) - 1}묶음 · 미분류 맨 뒤 OK")


def test_event_grouping_follows_the_chosen_sort():
    """오래된순을 고르면 추억 묶음도 오래된 것부터 온다

    사진은 오래된 것부터인데 추억은 최근 것부터면 화면을 위아래로 되짚어야 한다.
    """
    def group_order(sort: str) -> list[str]:
        items = album.query(
            viewer_id=VIEWER, group_by="event", sort=sort, limit=album.MAX_LIMIT
        )["items"]
        order: list[str] = []
        for item in items:
            key = item["event"]["id"] if item["event"] else ""
            if not order or order[-1] != key:
                order.append(key)
        return order

    newest = [event_id for event_id in group_order("captured_desc") if event_id]
    oldest = [event_id for event_id in group_order("captured_asc") if event_id]

    assert oldest == list(reversed(newest)), (newest, oldest)
    # 미분류는 정렬과 무관하게 맨 뒤다 (추억이 아니다)
    assert group_order("captured_asc")[-1] == ""
    print("  오래된순 추억 묶음", oldest[:3], "…")


def test_event_grouping_cursor_pages_have_no_overlap_or_gap():
    """추억별로 묶어 놓고 커서로 끝까지 넘겨도 겹침도 빠짐도 없다

    묶음의 순서까지 커서에 담기 때문에 여기서 어긋나면 페이지 경계에서 추억이
    토막나거나 같은 사진이 두 번 그려진다.
    """
    for sort in ("captured_desc", "captured_asc", "uploaded_desc"):
        full = _ids(
            album.query(viewer_id=VIEWER, group_by="event", sort=sort, limit=album.MAX_LIMIT)
        )
        walked: list[str] = []
        cursor = None
        for _ in range(40):  # 무한 루프 방어
            page = album.query(
                viewer_id=VIEWER, group_by="event", sort=sort, limit=3, cursor=cursor
            )
            walked.extend(_ids(page))
            cursor = page["next_cursor"]
            if not cursor:
                break

        assert cursor is None, f"{sort}: 커서가 끝나지 않았다"
        assert walked == full, f"{sort}: 커서로 걸은 순서가 전체 목록과 다르다"
        assert len(set(walked)) == len(walked), f"{sort}: 같은 사진이 두 번 나왔다"
    print("  세 정렬 × 3개씩 완주 · 겹침 없음")


def test_cursor_from_another_grouping_is_not_reused():
    """묶는 방식을 바꾸면 커서를 버리고 처음부터 준다

    연월의 다음 자리와 추억의 다음 자리는 전혀 다른 곳이다. 조용히 이어 주면
    화면에 사진이 겹치거나 빠진 채로 쌓인다.
    """
    first = album.query(viewer_id=VIEWER, limit=5)
    regrouped = album.query(
        viewer_id=VIEWER, limit=5, cursor=first["next_cursor"], group_by="event"
    )
    fresh = album.query(viewer_id=VIEWER, limit=5, group_by="event")

    assert _ids(regrouped) == _ids(fresh), "다른 묶음의 커서를 그대로 이어 붙였다"
    print("  묶음 바뀐 커서 → 처음부터 OK")


def test_event_without_a_date_falls_back_to_its_photos():
    """날짜가 적히지 않은 추억도 제자리에 선다

    추억에 날짜가 없으면 그 추억 사진의 촬영일로 줄을 세운다. 사진에도 날짜가
    없을 때만 날짜를 아는 추억들 뒤로 간다 — 촬영일 미상 사진과 같은 처리다.
    """
    from_photo, no_date = "album_test_ev_from_photo", "album_test_ev_no_date"
    photos = {
        "album_test_ev_p1": (from_photo, "1999-05-04T10:00:00+09:00"),
        "album_test_ev_p2": (no_date, None),
    }
    graph_manager.add_event(EventNode(id=from_photo, title="날짜 없는 추억 (사진은 1999)"))
    graph_manager.add_event(EventNode(id=no_date, title="추억도 사진도 날짜 미상"))
    try:
        for media_id, (event_id, exif_date) in photos.items():
            _make_temp_photo(media_id, exif_date)
            graph_manager.add_edge(
                Edge(
                    source=media_id,
                    target=event_id,
                    relation=RelationType.CAPTURED_DURING,
                )
            )

        items = album.query(viewer_id=VIEWER, group_by="event", limit=album.MAX_LIMIT)["items"]
        order: list[str] = []
        for item in items:
            key = item["event"]["id"] if item["event"] else ""
            if not order or order[-1] != key:
                order.append(key)

        # 사진의 촬영일(1999)로 2003(E02)과 1998(E01) 사이에 앉는다
        assert order.index("E02") < order.index(from_photo) < order.index("E01"), order
        # 사진마저 날짜가 없으면 날짜를 아는 추억 전부 뒤, 미분류 앞
        assert order.index("E01") < order.index(no_date) < order.index(""), order

        # 그 상태에서도 커서가 어긋나지 않는다
        walked: list[str] = []
        cursor = None
        for _ in range(40):
            page = album.query(viewer_id=VIEWER, group_by="event", limit=3, cursor=cursor)
            walked.extend(_ids(page))
            cursor = page["next_cursor"]
            if not cursor:
                break
        assert walked == [item["id"] for item in items], "날짜 없는 추억에서 커서가 어긋났다"
        print("  날짜 없는 추억 →", order.index(from_photo), "번째 묶음 · 커서 OK")
    finally:
        _drop(*photos, from_photo, no_date)


# --- 페이지 ------------------------------------------------------------------


def test_cursor_pages_have_no_overlap_or_gap():
    """커서로 끝까지 넘겨도 겹침도 빠짐도 없다"""
    full = _ids(album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT))
    assert len(full) > 6, "시드가 너무 적어 페이지를 확인할 수 없다"

    walked: list[str] = []
    cursor = None
    for _ in range(20):  # 무한 루프 방어
        page = album.query(viewer_id=VIEWER, limit=5, cursor=cursor)
        assert page["total"] == len(full), "페이지마다 전체 개수가 달라졌다"
        walked.extend(_ids(page))
        cursor = page["next_cursor"]
        if not cursor:
            break

    assert cursor is None, "커서가 끝나지 않았다"
    assert walked == full, "커서로 걸은 순서가 전체 목록과 다르다"
    assert len(set(walked)) == len(walked), "같은 사진이 두 번 나왔다"
    print("  5개씩", len(full), "건 완주 · 겹침 없음")


def test_limit_is_capped():
    """한 번에 60개를 넘겨주지 않는다 (500장이어도 원본을 다 부르지 않는다)"""
    result = album.query(viewer_id=VIEWER, limit=10_000)
    assert len(result["items"]) <= album.MAX_LIMIT, len(result["items"])
    print("  limit 상한", album.MAX_LIMIT, "적용 OK")


def test_cursor_from_another_sort_is_not_reused():
    """정렬을 바꾸면 커서를 버리고 처음부터 준다

    같은 id 다음 자리가 정렬에 따라 전혀 달라진다. 조용히 이어 주면 화면에
    사진이 겹치거나 빠진 채로 쌓인다.
    """
    first = album.query(viewer_id=VIEWER, limit=5)
    restarted = album.query(
        viewer_id=VIEWER, limit=5, cursor=first["next_cursor"], sort="captured_asc"
    )
    fresh = album.query(viewer_id=VIEWER, limit=5, sort="captured_asc")

    assert _ids(restarted) == _ids(fresh), "다른 정렬의 커서를 그대로 이어 붙였다"
    print("  정렬 바뀐 커서 → 처음부터 OK")


# --- 공개 범위 ---------------------------------------------------------------


def test_private_media_is_hidden_from_others():
    """비공개 사진은 목록·개수·연도 목록에서 모두 빠진다"""
    graph_manager.update_node(
        PRIVATE_MEDIA,
        {"visibility": Visibility.PRIVATE.value, "owner_id": VIEWER, "allowed_ids": []},
    )

    owner = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)
    other = album.query(viewer_id=OTHER, limit=album.MAX_LIMIT)

    assert PRIVATE_MEDIA in _ids(owner), "올린 사람이 자기 사진을 못 본다"
    assert PRIVATE_MEDIA not in _ids(other), "비공개 사진이 다른 가족에게 보인다"
    # 개수만 남아도 "무언가 있다"는 사실이 새어 나간다
    assert other["total"] == owner["total"] - 1, (owner["total"], other["total"])

    # 원본 경로가 응답에 실리지 않았다 — 목록에서 원본 주소를 얻을 길이 없다
    assert all(PRIVATE_MEDIA not in item["file_path"] for item in other["items"])
    print(f"  소유자 {owner['total']} · 다른 가족 {other['total']}")

    _restore()


def test_viewer_without_id_sees_family_shared_only():
    """누가 보는지 모르면 가족 전체 공개만 준다"""
    graph_manager.update_node(
        PRIVATE_MEDIA,
        {"visibility": Visibility.PRIVATE.value, "owner_id": VIEWER, "allowed_ids": []},
    )

    anonymous = album.query(viewer_id=None, limit=album.MAX_LIMIT)
    assert PRIVATE_MEDIA not in _ids(anonymous), "열람자를 모르는데 비공개 사진을 줬다"
    print("  열람자 미상 →", anonymous["total"], "건")

    _restore()


# --- 라우트 ------------------------------------------------------------------


def test_album_route_is_declared_before_media_id():
    """/album이 /{media_id}보다 먼저 선언돼 있어야 한다

    순서가 뒤바뀌면 FastAPI가 "album"을 media_id로 읽어 404를 준다.
    라우트 선언 순서는 코드를 읽어서는 놓치기 쉬우므로 여기서 잡는다.
    """
    client = TestClient(app)
    response = client.get("/api/media/album", params={"viewer_id": VIEWER, "limit": 5})

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 5, len(body["items"])
    assert body["total"] >= 5
    assert body["next_cursor"], "다음 페이지 커서가 없다"

    # 스키마가 사진첩 화면이 필요한 것을 실제로 담고 있는가
    item = body["items"][0]
    for key in (
        "id",
        "media_type",
        "file_path",
        "original_filename",
        "captured_at",
        "uploaded_at",
        "event",
        "people",
        "place",
        "visibility",
        "has_exif",
    ):
        assert key in item, f"응답에 {key}가 없다"

    # 미디어 상세는 그대로 열린다 (사진첩 라우트가 가로채지 않았다)
    detail = client.get(f"/api/media/{PRIVATE_MEDIA}", params={"viewer_id": VIEWER})
    assert detail.status_code == 200, detail.text
    print("  GET /api/media/album 200 ·", body["total"], "건")


def test_router_passes_every_filter_through():
    """라우터가 화면이 보낸 조건을 서비스에 그대로 넘기는가"""
    result = asyncio.run(
        get_album(
            cursor=None,
            limit=5,
            types="photo",
            year=1998,
            person_id="P01",
            event_id="E01",
            event_status="linked",
            sort="captured_asc",
            group_by="event",
            q=None,
            viewer_id=VIEWER,
        )
    )
    direct = album.query(
        viewer_id=VIEWER,
        types="photo",
        year=1998,
        person_id="P01",
        event_id="E01",
        event_status="linked",
        sort="captured_asc",
        group_by="event",
        limit=5,
    )
    assert result == direct, "라우터를 지나며 조건이 달라졌다"
    print("  라우터 → 서비스 인자 전달 OK")


# --- 삭제 --------------------------------------------------------------------


def _delete(client, media_id: str, actor: str):
    return client.delete(f"/api/media/{media_id}", headers={"X-Viewer-Id": actor})


def test_delete_removes_it_from_the_album():
    """지운 원본은 목록과 개수에서 함께 빠진다

    사진첩은 목록을 스스로 들고 있는 화면이라, 지운 뒤에도 칸이 남아 있으면
    없는 사진의 원본을 계속 부른다.
    """
    media_id = "album_test_delete"
    _make_temp_photo(media_id, "2013-07-01T10:00:00+09:00")
    try:
        before = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)
        assert media_id in _ids(before), "시험용 사진이 목록에 없다"

        with TestClient(app) as client:
            gone = _delete(client, media_id, VIEWER)
            assert gone.status_code == 200, gone.text

        after = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)
        assert media_id not in _ids(after), "지웠는데 목록에 남아 있다"
        assert after["total"] == before["total"] - 1, (before["total"], after["total"])
        assert 2013 not in after["available_years"], "지운 사진의 연도가 필터에 남았다"
        print(f"  {before['total']} → {after['total']} · 연도 목록에서도 빠짐 OK")
    finally:
        _drop(media_id)


def test_delete_refused_leaves_the_photo_in_place():
    """남이 올린 원본은 지워지지 않는다 (그리고 목록에 그대로 남는다)

    권한 규칙 자체는 tests/test_permissions.py가 본다. 여기서 보는 것은
    거절됐을 때 사진첩이 사진을 잃지 않는가다 — 화면이 먼저 지워 놓고 서버가
    거절하면 사진이 사라진 것처럼 보인다.
    """
    media_id = "album_test_delete_denied"
    _make_temp_photo(media_id, "2013-07-02T10:00:00+09:00", owner_id=VIEWER)
    try:
        with TestClient(app) as client:
            denied = _delete(client, media_id, OTHER)
            assert denied.status_code == 403, denied.status_code
            # 왜 못 지우는지를 서버가 말해 준다 (화면이 그 문장을 그대로 보여준다)
            assert denied.json().get("detail"), "거절 이유가 비었다"

        assert media_id in _ids(album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT))
        print("  남의 원본 삭제 403 · 목록 유지 OK")
    finally:
        _drop(media_id)


def test_cursor_survives_deleting_its_anchor():
    """커서가 가리킨 사진을 지워도 다음 페이지가 그 뒤에서 이어진다

    커서를 id로만 찾으면, 지워진 뒤 그 커서가 처음을 가리킨다. 이미 여러
    페이지를 받아 둔 화면은 아는 사진만 다시 받고 더 내려가지 못한다.
    """
    ids = ["album_test_c1", "album_test_c2", "album_test_c3"]
    for media_id, day in zip(ids, ("03", "02", "01")):
        _make_temp_photo(media_id, f"2013-09-{day}T10:00:00+09:00")
    try:
        first = album.query(viewer_id=VIEWER, year=2013, limit=2)
        assert _ids(first) == ids[:2], _ids(first)
        cursor = first["next_cursor"]
        assert cursor, "다음 페이지 커서가 없다"

        # 커서가 앉아 있던 사진을 지운다
        with TestClient(app) as client:
            assert _delete(client, ids[1], VIEWER).status_code == 200

        second = album.query(viewer_id=VIEWER, year=2013, limit=2, cursor=cursor)
        assert _ids(second) == [ids[2]], _ids(second)
        assert second["total"] == 2, second["total"]
        print("  커서 사진 삭제 후에도 다음 장부터 이어짐 OK")
    finally:
        _drop(*ids)


def test_bulk_delete_removes_all_of_them():
    """여러 장을 한 번에 지운다 (요청 하나로)"""
    ids = [f"album_test_bulk_{i}" for i in range(3)]
    for media_id, day in zip(ids, ("11", "12", "13")):
        _make_temp_photo(media_id, f"2012-05-{day}T10:00:00+09:00")
    try:
        before = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)
        assert set(ids) <= set(_ids(before))

        with TestClient(app) as client:
            response = client.post(
                "/api/media/bulk-delete",
                json={"media_ids": ids},
                headers={"X-Viewer-Id": VIEWER},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert sorted(body["deleted"]) == sorted(ids), body["deleted"]
        assert body["failed"] == [], body["failed"]

        after = album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT)
        assert not (set(ids) & set(_ids(after))), "지웠는데 목록에 남아 있다"
        assert after["total"] == before["total"] - len(ids)
        print(f"  {len(ids)}장 한 번에 · {before['total']} → {after['total']}")
    finally:
        _drop(*ids)


def test_bulk_delete_keeps_what_it_cannot_delete():
    """막힌 것만 남고 나머지는 지워진다 — 하나 때문에 전부 되돌리지 않는다

    남의 사진이 섞여 있는 것은 정상이다(가족이 함께 쓰는 공간이다). 그때
    "전부 실패"로 돌려주면 사용자는 어느 것이 남의 것인지 모른 채 다시 누른다.
    """
    mine = ["album_test_mine_1", "album_test_mine_2"]
    theirs = "album_test_theirs"
    for media_id, day in zip(mine, ("21", "22")):
        _make_temp_photo(media_id, f"2012-05-{day}T10:00:00+09:00")
    _make_temp_photo(theirs, "2012-05-23T10:00:00+09:00", owner_id=OTHER)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/media/bulk-delete",
                # 같은 id를 두 번 보내고 없는 id도 섞는다 (화면이 보낸 값이다)
                json={"media_ids": mine + [theirs, mine[0], "album_test_ghost"]},
                headers={"X-Viewer-Id": VIEWER},
            )
        assert response.status_code == 200, response.text
        body = response.json()

        assert sorted(body["deleted"]) == sorted(mine), body["deleted"]
        failed = {f["id"]: f["reason"] for f in body["failed"]}
        assert set(failed) == {theirs, "album_test_ghost"}, failed
        # 왜 막혔는지가 함께 와야 한다 (화면이 그 문장을 그대로 보여준다)
        assert all(reason for reason in failed.values()), failed

        assert graph_manager.get_node(theirs), "남의 사진이 지워졌다"
        assert theirs in _ids(album.query(viewer_id=VIEWER, limit=album.MAX_LIMIT))
        print(f"  지움 {len(body['deleted'])} · 막힘 {len(failed)} · 남의 사진 그대로")
    finally:
        _drop(*mine, theirs)


def test_bulk_delete_refuses_empty_and_oversized_requests():
    """고르지 않았거나 한 번에 너무 많으면 조용히 넘기지 않고 막는다

    상한을 넘겼을 때 앞의 200개만 지우면, 화면은 전부 지운 줄 알고 나머지를
    잃어버린 것처럼 보게 된다.
    """
    from backend.routers.media import MAX_BULK_DELETE

    with TestClient(app) as client:
        empty = client.post(
            "/api/media/bulk-delete", json={"media_ids": []}, headers={"X-Viewer-Id": VIEWER}
        )
        assert empty.status_code == 400, empty.status_code

        too_many = client.post(
            "/api/media/bulk-delete",
            json={"media_ids": [f"id_{i}" for i in range(MAX_BULK_DELETE + 1)]},
            headers={"X-Viewer-Id": VIEWER},
        )
        assert too_many.status_code == 400, too_many.status_code
        assert str(MAX_BULK_DELETE) in too_many.json()["detail"], too_many.text
    print(f"  빈 요청·{MAX_BULK_DELETE}개 초과 모두 400 OK")


TESTS = [
    test_album_has_photos_and_videos_only,
    test_undated_photos_are_kept_and_pushed_last,
    test_captured_order_uses_exif_not_upload_time,
    test_type_filter,
    test_year_filter_uses_capture_year,
    test_year_options_survive_a_year_selection,
    test_person_filter_only_uses_human_tags,
    test_event_status_filter,
    test_search_covers_filename_event_person_place,
    test_filters_combine,
    test_event_filter_narrows_to_one_event,
    test_event_options_survive_an_event_selection,
    test_selected_event_stays_in_the_options_at_zero,
    test_event_grouping_keeps_each_event_together,
    test_event_grouping_follows_the_chosen_sort,
    test_event_grouping_cursor_pages_have_no_overlap_or_gap,
    test_cursor_from_another_grouping_is_not_reused,
    test_event_without_a_date_falls_back_to_its_photos,
    test_cursor_pages_have_no_overlap_or_gap,
    test_limit_is_capped,
    test_cursor_from_another_sort_is_not_reused,
    test_private_media_is_hidden_from_others,
    test_viewer_without_id_sees_family_shared_only,
    test_album_route_is_declared_before_media_id,
    test_router_passes_every_filter_through,
    test_delete_removes_it_from_the_album,
    test_delete_refused_leaves_the_photo_in_place,
    test_cursor_survives_deleting_its_anchor,
    test_bulk_delete_removes_all_of_them,
    test_bulk_delete_keeps_what_it_cannot_delete,
    test_bulk_delete_refuses_empty_and_oversized_requests,
]


if __name__ == "__main__":
    _require_seeded_graph()
    _setup()

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

    _cleanup()
    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} 통과")
    sys.exit(1 if failures else 0)
