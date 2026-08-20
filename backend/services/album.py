"""사진첩 조회 (기획안 사진첩 09장 GET /api/media/album)

사진첩은 사건도 이야기도 거치지 않고 사진 자체를 훑는 자리다. 기존
`GET /api/media`는 목록에 사건·인물·장소·공개 범위를 붙여 주지 않고
페이지도 나누지 않아서, 사진첩을 그 응답으로 그리면 화면이 목록 하나로
수백 장의 원본을 부르게 된다. 응답 구조를 바꾸면 이미 그 목록을 쓰는
홈·인물·채팅·TV가 함께 깨지므로, 사진첩이 필요한 것만 여기서 따로 만든다.

AI는 쓰지 않는다. 목록·정렬·연도·인물·페이지는 전부 데이터 처리다 —
여기에 모델을 끼우면 느려지고 같은 조건에 다른 결과가 나온다. 인물 필터도
사람이 직접 지목한 태그(DEPICTS · detected_faces)만 본다. 얼굴 인식이 없는
상태에서 사진을 임의로 누군가의 사진으로 분류하지 않는다.

두 가지를 특별히 다룬다.

  촬영일    exif_date가 있으면 그것이 촬영일이다. 없으면 created_at(올린
            시각)으로 줄을 세우되 has_exif=False로 밝힌다. 올린 시각을
            촬영일이라고 말하면 1998년 사진이 2026년 칸에 들어간다. 화면은
            이 값으로 "날짜를 알 수 없는 사진"을 따로 묶는다.

  공개 범위  visibility.filter_media()를 반드시 지난다. 사진첩은 가족 사진을
            가장 많이, 가장 빠르게 내보내는 통로여서 여기를 빼먹으면 08장의
            동의가 사실상 없는 것이 된다.
"""

from __future__ import annotations

import base64
import binascii
from typing import Iterable, Optional

from backend.models.graph_models import MediaType, RelationType
from backend.services import visibility
from backend.services.graph_manager import graph_manager

# 사진첩에 나오는 것. 음성은 여기 오지 않는다 — 훑어볼 그림이 없고,
# 목소리는 홈·인물·추억 상세에서 재생 목록으로 듣는 것이 자리에 맞는다.
ALBUM_TYPES = (MediaType.PHOTO.value, MediaType.VIDEO.value)

# 한 번에 내려주는 최대 개수. 500장이 있어도 원본 500장을 한 번에 부르지 않는다.
MAX_LIMIT = 60
DEFAULT_LIMIT = 60

SORTS = ("captured_desc", "captured_asc", "uploaded_desc")
EVENT_STATUSES = ("all", "linked", "unlinked")


class MediaLinks:
    """미디어에 붙은 사건·인물·장소를 한 번만 색인한다

    미디어마다 get_connected_nodes나 get_node를 부르지 않는다. Postgres에서는
    그 한 번이 질의 한 번이라(stores/pg_store.get_node) 사진 500장이면 질의가
    수천 번이 된다. 엣지 한 번 + 사건·장소·인물 목록 한 번씩만 읽는다.
    """

    __slots__ = ("events", "places", "people", "persons")

    def __init__(self) -> None:
        events = {
            node["id"]: {"id": node["id"], "title": node.get("title", "")}
            for node in graph_manager.get_events()
        }
        places = {
            node["id"]: {"id": node["id"], "name": node.get("name", "")}
            for node in graph_manager.get_places()
        }
        self.persons: dict[str, dict] = {
            node["id"]: {
                "id": node["id"],
                "name": node.get("name", ""),
                "relation": node.get("relation") or None,
                "thumbnail_url": node.get("thumbnail_url"),
            }
            for node in graph_manager.get_persons()
        }

        self.events: dict[str, dict] = {}
        self.places: dict[str, dict] = {}
        self.people: dict[str, list[str]] = {}

        for edge in graph_manager.get_all_edges():
            relation = edge["relation"]
            source, target = edge["source"], edge["target"]

            if relation == RelationType.CAPTURED_DURING:
                # 사진 하나가 두 사건에 걸리는 일은 없다. 있어도 먼저 붙은 것을 쓴다.
                if source not in self.events and target in events:
                    self.events[source] = events[target]
            elif relation == RelationType.TAKEN_AT:
                if source not in self.places and target in places:
                    self.places[source] = places[target]
            elif relation == RelationType.DEPICTS:
                people = self.people.setdefault(source, [])
                if target not in people:
                    people.append(target)

    def event_of(self, media_id: str) -> Optional[dict]:
        return self.events.get(media_id)

    def place_of(self, media_id: str) -> Optional[dict]:
        return self.places.get(media_id)

    def person_ids_of(self, node: dict) -> list[str]:
        """이 기록에 지목된 사람들

        엣지(DEPICTS)와 노드 필드(detected_faces)를 함께 본다. 둘은 함께
        맞춰지지만(event_resolver.set_media_persons) 시드·이전 데이터에서는
        한쪽만 있는 경우가 있어, 한쪽만 읽으면 인물 필터에서 사진이 빠진다.
        """
        ids = [pid for pid in self.people.get(node["id"], ()) if pid in self.persons]
        for person_id in node.get("detected_faces") or []:
            if person_id in self.persons and person_id not in ids:
                ids.append(person_id)
        return ids

    def people_of(self, node: dict) -> list[dict]:
        """지목된 사람들의 이름까지 (인물 칩·상세 화면이 그대로 쓴다)"""
        return [self.persons[pid] for pid in self.person_ids_of(node)]


def query(
    *,
    viewer_id: Optional[str] = None,
    types: Optional[str] = None,
    year: Optional[int] = None,
    person_id: Optional[str] = None,
    event_status: str = "all",
    sort: str = "captured_desc",
    q: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """사진첩 한 페이지

    Returns: {"items", "next_cursor", "total", "available_years"}
      total          지금 조건에 맞는 전체 개수 (이 페이지 개수가 아니다)
      available_years 연도 필터만 뺀 조건에서 고를 수 있는 연도들.
                      고른 연도 때문에 나머지 연도가 사라지면 되돌아갈 수 없다.
    """
    sort = sort if sort in SORTS else "captured_desc"
    event_status = event_status if event_status in EVENT_STATUSES else "all"
    limit = max(1, min(limit or DEFAULT_LIMIT, MAX_LIMIT))

    wanted_types = _parse_types(types)
    links = MediaLinks()

    # 공개 범위를 가장 먼저 지난다. 그 뒤의 개수·연도 목록까지 모두 이 사람이
    # 볼 수 있는 것만으로 세어야, 가려진 사진의 존재가 숫자로 새어 나가지 않는다.
    visible = visibility.filter_media(
        (m for m in graph_manager.get_media_nodes() if m.get("media_type") in ALBUM_TYPES),
        viewer_id,
    )

    rows = [_to_item(node, links) for node in visible]

    # 연도를 뺀 조건까지 걸러 둔 뒤 연도 목록을 뽑는다
    without_year = [
        row
        for row in rows
        if _matches(row, wanted_types, None, person_id, event_status, q)
    ]
    available_years = sorted(
        {row["_year"] for row in without_year if row["_year"] is not None}, reverse=True
    )

    matched = (
        without_year
        if year is None
        else [row for row in without_year if row["_year"] == year]
    )

    ordered = _order(matched, sort)
    total = len(ordered)

    start = _cursor_position(ordered, cursor, sort)
    page = ordered[start : start + limit]
    next_cursor = (
        _encode_cursor(sort, page[-1]["id"]) if start + limit < total and page else None
    )

    return {
        "items": [_public(row) for row in page],
        "next_cursor": next_cursor,
        "total": total,
        "available_years": available_years,
    }


# --- 한 건 만들기 -------------------------------------------------------------


def _to_item(node: dict, links: MediaLinks) -> dict:
    """미디어 노드 하나를 사진첩 항목으로

    _year와 _search는 걸러내기·정렬에만 쓰고 응답에서는 뺀다 (_public).
    """
    exif_date = node.get("exif_date")
    uploaded_at = node.get("created_at") or ""
    event = links.event_of(node["id"])
    place = links.place_of(node["id"])
    people = links.people_of(node)

    filename = node.get("original_filename", "")
    haystack = " ".join(
        part
        for part in (
            filename,
            event["title"] if event else "",
            place["name"] if place else "",
            *(p["name"] for p in people),
        )
        if part
    ).lower()

    return {
        "id": node["id"],
        "media_type": node.get("media_type", MediaType.PHOTO.value),
        "file_path": node.get("file_path", ""),
        "thumbnail_path": node.get("thumbnail_path"),
        "original_filename": filename,
        # 촬영일. exif가 없으면 올린 시각으로 줄을 세우되 has_exif로 밝힌다.
        "captured_at": exif_date or uploaded_at or None,
        "uploaded_at": uploaded_at,
        "duration_sec": node.get("duration_sec"),
        "event": event,
        "people": people,
        "place": place,
        "visibility": node.get("visibility") or "family",
        "owner_id": node.get("owner_id"),
        "has_exif": bool(exif_date),
        # --- 내부용 ---
        # 연도는 EXIF가 있을 때만 정한다. 올린 시각의 연도를 촬영 연도로 쓰면
        # 1998년 사진이 "2026년"에 걸린다 — 연도 필터가 거짓말을 하게 된다.
        "_year": _year_of(exif_date),
        "_search": haystack,
        "_person_ids": [p["id"] for p in people],
    }


def _public(row: dict) -> dict:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _year_of(value: Optional[str]) -> Optional[int]:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def _parse_types(types: Optional[str]) -> set[str]:
    """"photo,video" -> {"photo", "video"}. 비면 사진첩에 나올 것 전부.

    사진첩에 없는 종류(음성)만 골라 보내면 필터를 걸지 않은 것으로 본다.
    sort·event_status의 모르는 값과 같은 처리다 — 손으로 주소를 고친 결과가
    빈 화면이 되면 무엇이 잘못됐는지 알 수 없다.
    """
    if not types:
        return set(ALBUM_TYPES)
    wanted = {t.strip() for t in types.split(",") if t.strip()} & set(ALBUM_TYPES)
    return wanted or set(ALBUM_TYPES)


# --- 걸러내기 ----------------------------------------------------------------


def _matches(
    row: dict,
    wanted_types: set[str],
    year: Optional[int],
    person_id: Optional[str],
    event_status: str,
    q: Optional[str],
) -> bool:
    if row["media_type"] not in wanted_types:
        return False

    if year is not None and row["_year"] != year:
        return False

    if person_id and person_id not in row["_person_ids"]:
        return False

    if event_status == "linked" and not row["event"]:
        return False
    if event_status == "unlinked" and row["event"]:
        return False

    if q:
        needle = q.strip().lower()
        if needle and needle not in row["_search"]:
            return False

    return True


# --- 정렬 --------------------------------------------------------------------


def _order(rows: Iterable[dict], sort: str) -> list[dict]:
    """정렬. 촬영일 순에서는 날짜를 모르는 사진을 맨 뒤로 보낸다

    촬영일이 없는 사진을 올린 시각으로 섞어 놓으면, "최신순"의 맨 앞이 방금
    올린 1998년 사진이 된다. 오래된순에서도 뒤에 둔다 — 모르는 것은 가장
    오래된 것이 아니다.
    """
    rows = list(rows)

    if sort == "uploaded_desc":
        return sorted(rows, key=lambda r: (r["uploaded_at"] or "", r["id"]), reverse=True)

    dated = [r for r in rows if r["has_exif"]]
    undated = [r for r in rows if not r["has_exif"]]

    reverse = sort != "captured_asc"
    dated.sort(key=lambda r: (r["captured_at"] or "", r["id"]), reverse=reverse)
    # 날짜를 모르는 것끼리는 최근에 올린 것부터
    undated.sort(key=lambda r: (r["uploaded_at"] or "", r["id"]), reverse=True)

    return dated + undated


# --- 커서 --------------------------------------------------------------------


def _encode_cursor(sort: str, media_id: str) -> str:
    raw = f"{sort}|{media_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> Optional[tuple[str, str]]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        sort, _, media_id = base64.urlsafe_b64decode(padded).decode().partition("|")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if not sort or not media_id:
        return None
    return sort, media_id


def _cursor_position(ordered: list[dict], cursor: Optional[str], sort: str) -> int:
    """커서가 가리키는 다음 항목의 자리

    커서에 정렬 방식을 함께 담는다. 정렬을 바꾸면 순서가 달라져 같은 id 다음이
    전혀 다른 자리가 되므로, 어긋난 커서는 버리고 처음부터 준다 — 조용히
    이어 주면 화면에 사진이 겹치거나 빠진 채로 쌓인다.

    커서 이후에 새 사진이 올라오면 그 사진은 이 페이지에서 빠진다. 목록을
    처음부터 다시 받으면 나타난다.
    """
    if not cursor:
        return 0

    decoded = _decode_cursor(cursor)
    if not decoded or decoded[0] != sort:
        return 0

    _, media_id = decoded
    for index, row in enumerate(ordered):
        if row["id"] == media_id:
            return index + 1

    # 커서가 가리키던 사진이 지워졌거나 조건에서 빠졌다
    return 0
