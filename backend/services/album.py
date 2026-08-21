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

묶는 방식은 두 가지다. 촬영 연월(month)과 사건(event). 사건별은 화면에서 나눌
수 없다 — 한 페이지 60장 안에서만 묶으면 같은 사건이 페이지마다 토막나고, 뒤
페이지에 있는 사진은 어느 묶음에도 못 들어간다. 그래서 사건 묶음의 순서까지
서버가 세워 커서에 담는다.

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
# 무엇으로 묶어 보는가. 연월은 사진을 훑는 순서고, 사건은 "그때 무슨 일이었나"다.
GROUP_BYS = ("month", "event")

# 사건 묶음을 줄 세우는 값에서 날짜와 사건 id를 가르는 글자. 날짜·id에 쓰이는
# 어떤 글자보다 작아서(0x23), 이어 붙인 문자열을 견주는 것이 (날짜, id) 짝을
# 견주는 것과 같은 순서가 된다 — 정렬과 커서가 같은 값을 쓰기 위한 것이다.
_KEY_SEP = "#"


class MediaLinks:
    """미디어에 붙은 사건·인물·장소를 한 번만 색인한다

    미디어마다 get_connected_nodes나 get_node를 부르지 않는다. Postgres에서는
    그 한 번이 질의 한 번이라(stores/pg_store.get_node) 사진 500장이면 질의가
    수천 번이 된다. 엣지 한 번 + 사건·장소·인물 목록 한 번씩만 읽는다.
    """

    __slots__ = ("events", "places", "people", "persons", "event_nodes")

    def __init__(self) -> None:
        # 사건 전부. 사진이 하나도 안 붙은 사건도 들고 있는다 — 고른 사건의
        # 이름은 그 사건에 사진이 없어도 화면에 적어야 한다 (_event_facets).
        self.event_nodes: dict[str, dict] = {
            node["id"]: {
                "id": node["id"],
                "title": node.get("title", ""),
                # 사건 묶음을 줄 세우는 날짜. 화면은 묶음 머리에 이걸 적는다.
                "date": node.get("date_start") or None,
            }
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
                if source not in self.events and target in self.event_nodes:
                    self.events[source] = self.event_nodes[target]
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
    event_id: Optional[str] = None,
    event_status: str = "all",
    sort: str = "captured_desc",
    group_by: str = "month",
    q: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """사진첩 한 페이지

    Returns: {"items", "next_cursor", "total", "available_years", "available_events"}
      total          지금 조건에 맞는 전체 개수 (이 페이지 개수가 아니다)
      available_years 연도 필터만 뺀 조건에서 고를 수 있는 연도들.
                      고른 연도 때문에 나머지 연도가 사라지면 되돌아갈 수 없다.
      available_events 사건 필터만 뺀 조건에서 고를 수 있는 사건들 (사진 수까지).
                      같은 이유다 — 사건 하나를 고른 뒤에도 다른 사건으로 옮겨간다.

    group_by="event"면 사건 묶음의 순서까지 여기서 정한다. 화면이 페이지마다
    다시 묶으면 같은 사건이 페이지 경계에서 토막난다.
    """
    sort = sort if sort in SORTS else "captured_desc"
    group_by = group_by if group_by in GROUP_BYS else "month"
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

    def matching(*, with_year: bool = True, with_event: bool = True) -> list[dict]:
        return [
            row
            for row in rows
            if _matches(
                row,
                wanted_types,
                year if with_year else None,
                person_id,
                event_id if with_event else None,
                event_status,
                q,
            )
        ]

    # 고를 수 있는 것은 그 조건 하나만 뺀 데서 센다. 연도를 고르면 연도 목록이,
    # 사건을 고르면 사건 목록이 그 선택 때문에 줄어들어 되돌아갈 수 없게 된다.
    available_years = sorted(
        {row["_year"] for row in matching(with_year=False) if row["_year"] is not None},
        reverse=True,
    )
    available_events = _event_facets(matching(with_event=False), links, event_id)

    matched = matching()
    event_keys = _event_keys(matched, links) if group_by == "event" else {}
    ordered = _order(matched, sort, group_by, event_keys)
    total = len(ordered)

    start = _cursor_position(ordered, cursor, sort, group_by, event_keys)
    page = ordered[start : start + limit]
    next_cursor = (
        _encode_cursor(sort, group_by, page[-1], event_keys)
        if start + limit < total and page
        else None
    )

    return {
        "items": [_public(row) for row in page],
        "next_cursor": next_cursor,
        "total": total,
        "available_years": available_years,
        "available_events": available_events,
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
    event_id: Optional[str],
    event_status: str,
    q: Optional[str],
) -> bool:
    if row["media_type"] not in wanted_types:
        return False

    if year is not None and row["_year"] != year:
        return False

    if person_id and person_id not in row["_person_ids"]:
        return False

    # 사건 하나만 보기. event_status와 함께 걸린다 — 사건을 고른 채 "미분류"를
    # 누르면 0장이 맞다 (필터가 서로를 덮지 않는다).
    if event_id and (not row["event"] or row["event"]["id"] != event_id):
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


# --- 사건 --------------------------------------------------------------------


def _event_facets(rows: Iterable[dict], links: MediaLinks, selected_id: Optional[str]) -> list[dict]:
    """고를 수 있는 사건과 그 개수 (사건 조건만 뺀 데서 센 것)

    개수를 함께 주는 이유: 인물·연도·검색이 걸린 상태에서 사건을 고르면 몇 장이
    남는지 미리 보여야 한다. 0장인 사건까지 목록에 두면 빈 화면을 누르게 된다.

    고른 사건은 0장이어도 남긴다. 다른 조건 때문에 남는 사진이 없어지면 그
    사건이 목록에서 사라지고, 화면에서 되돌릴(끄는) 길이 없어진다.
    """
    counts: dict[str, int] = {}
    for row in rows:
        event = row["event"]
        if event:
            counts[event["id"]] = counts.get(event["id"], 0) + 1

    if selected_id and selected_id not in counts and selected_id in links.event_nodes:
        counts[selected_id] = 0

    facets = [
        {
            "id": event_id,
            "title": links.event_nodes[event_id]["title"],
            "date": links.event_nodes[event_id]["date"],
            "count": count,
        }
        for event_id, count in counts.items()
        if event_id in links.event_nodes
    ]
    # 사진이 많은 순이 아니라 시간순이다. 사진첩은 개수를 세는 화면이 아니다.
    facets.sort(key=lambda facet: (facet["date"] or "", facet["id"]), reverse=True)
    return facets


def _event_keys(rows: Iterable[dict], links: MediaLinks) -> dict[str, str]:
    """사건 묶음을 줄 세울 값

    사건에 적힌 날짜(date_start)를 먼저 쓴다. 없으면 그 사건에 걸린 사진 중
    가장 이른 촬영일을 대신 쓴다 — 날짜가 없는 사건을 전부 한 칸에 몰아 두면
    사진에는 1998년이 적혀 있는데 묶음은 맨 뒤에 놓인다.

    사진에도 촬영일이 없으면 빈 값으로 남긴다. 그 묶음은 날짜를 아는 사건들
    뒤로 간다 (_order · _position의 event_rank).
    """
    earliest: dict[str, str] = {}
    for row in rows:
        event = row["event"]
        if not event or not row["has_exif"] or not row["captured_at"]:
            continue
        current = earliest.get(event["id"])
        if current is None or row["captured_at"] < current:
            earliest[event["id"]] = row["captured_at"]

    keys: dict[str, str] = {}
    for row in rows:
        event = row["event"]
        if not event or event["id"] in keys:
            continue
        event_id = event["id"]
        node = links.event_nodes.get(event_id) or {}
        keys[event_id] = node.get("date") or earliest.get(event_id, "")
    return keys


def _event_sort_key(event_id: str, event_keys: dict[str, str]) -> str:
    """사건 묶음의 자리. 정렬과 커서가 같은 값을 본다

    날짜를 모르는 사건은 id만 남긴다 — 그 묶음은 event_rank로 이미 뒤에 있고,
    빈 날짜를 앞에 붙이면 날짜를 아는 사건과 섞여 견주게 된다.
    """
    date = event_keys.get(event_id) or ""
    return f"{date}{_KEY_SEP}{event_id}" if date else event_id


# --- 정렬 --------------------------------------------------------------------


def _order(
    rows: Iterable[dict],
    sort: str,
    group_by: str = "month",
    event_keys: Optional[dict[str, str]] = None,
) -> list[dict]:
    """정렬. 사건별이면 사건 묶음을 세운 뒤 묶음 안에서 다시 시간순으로 세운다

    묶음의 순서도 고른 정렬을 따른다 — "오래된순"에서 사진은 오래된 것부터인데
    사건은 최근 것부터면 화면을 위아래로 되짚어야 한다.
    """
    rows = list(rows)
    if group_by != "event":
        return _order_by_time(rows, sort)

    keys = event_keys or {}
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["event"]["id"] if row["event"] else "", []).append(row)

    reverse = sort != "captured_asc"
    # 날짜를 아는 사건이 먼저. 모르는 사건을 빈 날짜로 섞으면 오래된순의 맨 앞이
    # "날짜 모르는 사건"이 된다 (촬영일 미상 사진과 같은 처리다).
    dated = sorted(
        (event_id for event_id in groups if event_id and keys.get(event_id)),
        key=lambda event_id: _event_sort_key(event_id, keys),
        reverse=reverse,
    )
    undated = sorted(
        (event_id for event_id in groups if event_id and not keys.get(event_id)),
        key=lambda event_id: _event_sort_key(event_id, keys),
        reverse=reverse,
    )

    ordered: list[dict] = []
    for event_id in [*dated, *undated]:
        ordered.extend(_order_by_time(groups[event_id], sort))
    # 어느 추억에도 붙지 않은 사진은 사건 묶음이 아니다 — 언제나 맨 뒤
    ordered.extend(_order_by_time(groups.get("", []), sort))
    return ordered


def _order_by_time(rows: Iterable[dict], sort: str) -> list[dict]:
    """촬영일 순에서는 날짜를 모르는 사진을 맨 뒤로 보낸다

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


Position = tuple[int, int, str, int, str, str]


def _position(
    row: dict,
    sort: str,
    group_by: str = "month",
    event_keys: Optional[dict[str, str]] = None,
) -> Position:
    """정렬에서 이 사진이 앉은 자리 (커서가 그대로 담는 값)

    (bucket, event_rank, event_key, rank, key, id) 여섯 자리다. 앞의 셋은 사건별로
    묶어 볼 때만 쓰인다 — 연월 묶음에서는 늘 같은 값이라 뒤의 셋만 견주게 된다.

      bucket      사건에 붙은 사진(0)인가 미분류(1)인가. 미분류는 언제나 맨 뒤다.
      event_rank  그 사건이 날짜를 아는가(0) 모르는가(1).
      event_key   사건 묶음의 자리 (_event_sort_key)
      rank        이 사진이 촬영일을 아는가(0) 모르는가(1). 모르는 것은 묶음 안
                  에서 언제나 뒤이므로(_order_by_time) 날짜보다 먼저 본다.
    """
    if group_by == "event":
        event = row["event"]
        keys = event_keys or {}
        bucket = 0 if event else 1
        event_rank = 0 if event and keys.get(event["id"]) else 1
        event_key = _event_sort_key(event["id"], keys) if event else ""
    else:
        bucket, event_rank, event_key = 0, 0, ""

    if sort == "uploaded_desc":
        return (bucket, event_rank, event_key, 0, row["uploaded_at"] or "", row["id"])

    if row["has_exif"]:
        return (bucket, event_rank, event_key, 0, row["captured_at"] or "", row["id"])
    # 촬영일을 모르는 묶음은 올린 시각으로 줄을 선다
    return (bucket, event_rank, event_key, 1, row["uploaded_at"] or "", row["id"])


def _comes_after(row: Position, anchor: Position, sort: str) -> bool:
    """이 사진이 커서보다 뒤에 있는가

    앞자리부터 하나씩 견준다. 묶음을 가르는 자리는 늘 오름차순이고 날짜 자리는
    고른 정렬을 따라가므로, 여섯 자리를 한 번에 짝으로 견줄 수 없다.
    """
    if row[0] != anchor[0]:
        return row[0] > anchor[0]  # 미분류 사진은 언제나 뒤다
    if row[1] != anchor[1]:
        return row[1] > anchor[1]  # 날짜를 아는 사건이 언제나 앞이다

    # 오래된순만 오름차순이다 (사건 묶음의 순서도 사진과 같은 방향을 따른다)
    ascending = sort == "captured_asc"
    if row[2] != anchor[2]:
        return row[2] > anchor[2] if ascending else row[2] < anchor[2]

    if row[3] != anchor[3]:
        return row[3] > anchor[3]  # 촬영일을 아는 사진이 언제나 앞이다

    # 촬영일 미상 묶음은 오래된순에서도 최근에 올린 것부터다 (_order_by_time)
    if ascending and row[3] == 0:
        return row[4:] > anchor[4:]
    return row[4:] < anchor[4:]


def _encode_cursor(
    sort: str,
    group_by: str,
    row: dict,
    event_keys: Optional[dict[str, str]] = None,
) -> str:
    bucket, event_rank, event_key, rank, key, media_id = _position(
        row, sort, group_by, event_keys
    )
    raw = f"{sort}|{group_by}|{bucket}|{event_rank}|{event_key}|{rank}|{key}|{media_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> Optional[tuple[str, str, Position]]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        parts = base64.urlsafe_b64decode(padded).decode().split("|", 7)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if len(parts) != 8:
        return None

    sort, group_by, bucket, event_rank, event_key, rank, key, media_id = parts
    if not sort or not group_by or not media_id:
        return None
    if not (bucket.isdigit() and event_rank.isdigit() and rank.isdigit()):
        return None
    return (
        sort,
        group_by,
        (int(bucket), int(event_rank), event_key, int(rank), key, media_id),
    )


def _cursor_position(
    ordered: list[dict],
    cursor: Optional[str],
    sort: str,
    group_by: str = "month",
    event_keys: Optional[dict[str, str]] = None,
) -> int:
    """커서 다음 사진이 앉은 자리

    id를 찾는 것이 아니라 "그 자리보다 뒤인 첫 사진"을 찾는다. 커서가 가리키던
    사진이 지워져도 그 다음부터 이어진다 — id로만 찾으면 사진첩에서 사진을
    지운 뒤 다음 페이지가 처음으로 돌아가고, 이미 여러 페이지를 받아 둔 화면은
    새 사진을 하나도 받지 못한 채 멈춘다.

    커서에 정렬 방식과 묶는 방식을 함께 담는다. 둘 중 하나만 바뀌어도 같은
    자리가 전혀 다른 곳을 가리키므로, 어긋난 커서는 버리고 처음부터 준다 —
    조용히 이어 주면 화면에 사진이 겹치거나 빠진 채로 쌓인다.

    커서보다 앞에 새 사진이 올라오면 그 사진은 이 페이지에 없다. 목록을 처음부터
    다시 받으면 나타난다 (커서 방식이 원래 그렇다).
    """
    if not cursor:
        return 0

    decoded = _decode_cursor(cursor)
    if not decoded or decoded[0] != sort or decoded[1] != group_by:
        return 0

    anchor = decoded[2]
    for index, row in enumerate(ordered):
        if _comes_after(_position(row, sort, group_by, event_keys), anchor, sort):
            # ordered는 이미 줄이 서 있다 — 한 번 넘어가면 나머지도 모두 뒤다
            return index

    return len(ordered)
