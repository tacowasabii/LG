"""사진·영상에서 추억 초안 만들기 (기획안 05·06·08)

올린 기록에서 읽을 수 있는 것만 모아 초안을 쓴다. 사용자는 그것을 고치거나
그대로 저장하고, 다른 가족의 승인은 받지 않는다.

    읽는 것            어디서 오는가
    촬영 시점          EXIF DateTimeOriginal (media_analyzer)
    좌표               EXIF GPS
    장소               좌표에서 가장 가까운 기존 장소 (없으면 좌표만)
    등장인물           지목된 사람 + 기존 기록에서의 동시 등장 추정
    주요 내용          scene_description — 모델이 사진을 보고 쓴다 (services/vision.py)
    기존 가족 기록     비슷한 날짜·같은 장소·같은 사람의 사건

네 가지를 지킨다.

0. 어떤 사진이 같은 사건인지 사용자에게 묻지 않는다. 한 번에 올린 사진이 여러
   사건에 걸쳐 있는 것이 정상이고(첫 사용자는 앨범에서 아무 사진이나 고른다),
   날짜와 좌표를 읽을 수 있는 쪽이 갈라야 한다. `draft_groups`가 묶음마다 초안
   하나를 만든다. 갈린 결과가 틀렸으면 화면에서 전부 하나로 합칠 수 있다.
1. 없는 것을 만들지 않는다. 날짜를 못 읽으면 비워 두고 화면이 묻는다.
2. 자동으로 확정하지 않는다. 인물 추정은 "이분이 엄마인가요?"로 되묻고,
   기존 추억과의 연결도 사용자가 고른다 (자동 병합 금지).
3. 모델이 없어도 초안이 나온다. 제목·설명은 LLM이 쓰지만, 실패하면 읽어낸
   사실만으로 규칙 기반 문장을 만든다. 발표 중 키가 죽어도 화면은 돈다.

확장 지점 — 지금 등장인물 추정은 얼굴 임베딩이 아니라 **동시 등장 통계**다.
같은 날·같은 장소의 기존 사진에 누가 함께 있었는지로 순위를 매긴다. 데이터가
쌓일수록 정확해지는 구조이고(기획안 06), 실제 얼굴 인식이 붙으면
`_person_candidates`의 점수 항목 하나로 들어간다 — 호출부는 바뀌지 않는다.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from backend.models.graph_models import MediaType, NodeType
from backend.services import llm_client, vision
from backend.services.graph_manager import graph_manager


# 같은 사건으로 볼 만한 시간 범위 (일)
NEAR_DAYS = 3
# 같은 장소로 볼 거리 (km)
NEAR_KM = 5.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _day(value: Optional[str]) -> Optional[str]:
    return value[:10] if value else None


def _days_between(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    try:
        return abs((datetime.fromisoformat(a[:10]) - datetime.fromisoformat(b[:10])).days)
    except (ValueError, TypeError):
        return None


def _when_phrase(date_str: Optional[str]) -> str:
    """올해 · 작년 · 재작년 · N년 전 (가족이 실제로 쓰는 말)"""
    if not date_str:
        return ""
    try:
        year = int(date_str[:4])
    except (ValueError, TypeError):
        return ""
    delta = datetime.now().year - year
    if delta <= 0:
        return "올해"
    if delta == 1:
        return "작년"
    if delta == 2:
        return "재작년"
    return f"{year}년"


def _people_phrase(persons: list[dict]) -> str:
    """엄마아빠 / 엄마와 하늘이 — 호칭이 있으면 호칭을 쓴다

    가족은 이름보다 호칭으로 부른다. 관계가 비어 있는 사람만 이름으로 적는다.
    """
    labels = [(p.get("relation") or p.get("name") or "").strip() for p in persons]
    labels = [label for label in labels if label]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        # 엄마 + 아빠는 붙여 쓰는 것이 자연스럽다
        joined = "".join(labels) if all(len(x) <= 3 for x in labels) else "와 ".join(labels)
        return joined
    return ", ".join(labels[:-1]) + " " + labels[-1]


# --- 인물 추정 ---------------------------------------------------------------


def _person_candidates(
    media_nodes: list[dict],
    already: list[str],
    day: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
) -> list[dict]:
    """이 사진에 누가 있을지 추정한다 (확정하지 않는다)

    같은 시기·같은 장소의 기존 기록에 함께 있던 사람일수록 점수가 높다.
    근거를 문장으로 함께 돌려주므로 화면이 "왜 그렇게 봤는지" 밝힐 수 있다.
    """
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    def bump(person_id: str, amount: float, reason: str) -> None:
        if person_id in already:
            return
        scores[person_id] = scores.get(person_id, 0) + amount
        if reason not in reasons.setdefault(person_id, []):
            reasons[person_id].append(reason)

    # 비슷한 시기·같은 장소의 기존 사진에 함께 있던 사람.
    # 이번에 올린 기록에 이미 지목된 사람은 already로 들어와 후보에서 빠진다.
    for other in graph_manager.get_media_nodes():
        if other["id"] in {m["id"] for m in media_nodes}:
            continue
        faces = other.get("detected_faces") or []
        if not faces:
            continue

        gap = _days_between(day, other.get("exif_date") or other.get("created_at"))
        near_day = gap is not None and gap <= NEAR_DAYS
        same_year = (
            day
            and (other.get("exif_date") or "")[:4] == day[:4]
        )

        near_place = False
        if (
            lat is not None
            and lng is not None
            and other.get("exif_lat") is not None
            and other.get("exif_lng") is not None
        ):
            near_place = _haversine_km(lat, lng, other["exif_lat"], other["exif_lng"]) <= NEAR_KM

        for person_id in faces:
            if near_day and near_place:
                bump(person_id, 4, "같은 날 같은 장소의 사진에 있던 사람")
            elif near_day:
                bump(person_id, 3, "같은 시기 사진에 있던 사람")
            elif near_place:
                bump(person_id, 2, "같은 장소 사진에 있던 사람")
            elif same_year:
                bump(person_id, 1, "같은 해 사진에 있던 사람")

    candidates = []
    for person_id, score in scores.items():
        person = graph_manager.get_node(person_id)
        if not person or person.get("node_type") != NodeType.PERSON:
            continue
        candidates.append({
            "id": person_id,
            "name": person.get("name", ""),
            "relation": person.get("relation", ""),
            "thumbnail_url": person.get("thumbnail_url"),
            "score": round(score, 1),
            # 확정하지 않는다. 화면은 이 값으로 묻는 말투를 정한다.
            "confidence": "likely" if score >= 4 else "maybe",
            "reason": reasons.get(person_id, [""])[0],
        })

    candidates.sort(key=lambda c: (-c["score"], c["name"]))
    return candidates[:4]


# --- 기존 추억과의 연결 (기획안 08) -----------------------------------------


def related_memories(
    day: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
    person_ids: list[str],
    limit: int = 3,
) -> list[dict]:
    """이 기록이 기존 추억과 관련 있어 보이는지

    자동으로 붙이지 않는다. "이 사진은 기존 '부산 가족여행'과 관련 있어 보여요"를
    화면에 띄우고, 기존 추억에 추가할지 새로 만들지는 사용자가 고른다.
    """
    results = []

    for event in graph_manager.get_events():
        score = 0
        reasons = []

        gap = _days_between(day, event.get("date_start"))
        if gap is not None:
            if gap <= NEAR_DAYS:
                score += 4
                reasons.append("날짜가 거의 같아요")
            elif gap <= 30:
                score += 2
                reasons.append("같은 달의 기록이에요")
            elif gap <= 365 and (event.get("date_start") or "")[:4] == (day or "")[:4]:
                score += 1
                reasons.append("같은 해의 기록이에요")

        place = graph_manager.get_node(event.get("location_id") or "")
        if (
            place
            and lat is not None
            and lng is not None
            and place.get("lat") is not None
            and place.get("lng") is not None
        ):
            distance = _haversine_km(lat, lng, place["lat"], place["lng"])
            if distance <= NEAR_KM:
                score += 4
                reasons.append(f"장소가 같아요 ({place.get('name', '')})")
            elif distance <= 50:
                score += 1
                reasons.append("가까운 장소예요")

        if person_ids:
            participants = {
                node["id"]
                for node in graph_manager.get_connected_nodes(event["id"])
                if node.get("node_type") == NodeType.PERSON
            }
            shared = participants & set(person_ids)
            if shared:
                score += min(len(shared), 3)
                names = [
                    (graph_manager.get_node(pid) or {}).get("name", "")
                    for pid in sorted(shared)
                ]
                reasons.append("함께한 가족이 겹쳐요 (" + ", ".join(n for n in names if n) + ")")

        if score < 4 or not reasons:
            continue

        results.append({
            "event_id": event["id"],
            "title": event.get("title", ""),
            "date_start": event.get("date_start"),
            "place": place.get("name") if place else None,
            "score": score,
            "reason": " · ".join(reasons[:2]),
        })

    results.sort(key=lambda r: -r["score"])
    return results[:limit]


# --- 초안 ---------------------------------------------------------------------


def _nearest_place(lat: Optional[float], lng: Optional[float]) -> Optional[dict]:
    """좌표에 가장 가까운 기존 장소 (없으면 None)

    새 장소를 여기서 만들지 않는다. 초안은 제안일 뿐이고, 저장하는 순간에
    memories.create_memory가 장소를 정한다.
    """
    if lat is None or lng is None:
        return None
    best = None
    best_distance = NEAR_KM
    for place in graph_manager.get_places():
        if place.get("lat") is None or place.get("lng") is None:
            continue
        distance = _haversine_km(lat, lng, place["lat"], place["lng"])
        if distance <= best_distance:
            best = place
            best_distance = distance
    if not best:
        return None
    return {"id": best["id"], "name": best.get("name", ""), "distance_km": round(best_distance, 2)}


def _fallback_text(
    when: str,
    place_name: Optional[str],
    persons: list[dict],
    scenes: list[str],
    media_count: int,
) -> tuple[str, str]:
    """모델 없이 제목·설명을 만든다 (읽어낸 사실만 쓴다)"""
    people = _people_phrase(persons)

    parts = [p for p in (when, (people + "와 함께한") if people else "", place_name or "") if p]
    title = " ".join(parts).strip() or "새 추억"

    lines = []
    if when or place_name:
        lines.append(" ".join(p for p in (when, place_name) if p) + "의 기록입니다.")
    if people:
        lines.append(f"{people}가 함께 있었습니다.")
    if scenes:
        lines.append(scenes[0])
    lines.append(f"사진·영상 {media_count}개를 함께 올렸습니다.")
    return title, " ".join(lines)


def cluster_media(media_nodes: list[dict]) -> list[list[dict]]:
    """올린 기록을 같은 사건으로 보이는 묶음으로 가른다

    예전에는 업로드 하나가 사건 하나였다. 그 가정에서 1998년 부산 사진과 2015년
    서울 사진을 함께 올리면 날짜는 1998년이 되고 좌표는 두 곳의 평균 —
    아무도 가 본 적 없는 지점 — 이 되어 그 근처 장소 이름이 붙었다.

    기준은 예전 자동 매칭이 쓰던 것과 같다 (±3일, 5km). 다른 것은 결과의 용도다.
    여기서 나온 묶음은 그대로 저장되지 않고 초안이 되어 사용자에게 보인다.
    자동 병합이 아니라 초안 분리다.

    촬영 시점이 없는 기록(스캔한 옛 사진, 올린 음성)은 시간으로 잴 수 없으므로
    따로 한 묶음으로 모은다. 날짜를 아는 사람이 화면에서 채운다.
    """
    dated = []
    undated = []
    for node in media_nodes:
        if node.get("exif_date"):
            dated.append(node)
        else:
            undated.append(node)

    dated.sort(key=lambda n: n.get("exif_date") or "")

    groups: list[list[dict]] = []
    for node in dated:
        if not groups:
            groups.append([node])
            continue

        current = groups[-1]
        gap = _days_between(node.get("exif_date"), current[-1].get("exif_date"))
        near_day = gap is not None and gap <= NEAR_DAYS

        # 좌표가 양쪽에 있을 때만 장소로 가른다. 한쪽만 있으면 날짜만 본다 —
        # GPS가 없는 사진을 다른 사건으로 밀어내지 않기 위해서다.
        far_place = False
        anchor = next(
            (n for n in reversed(current) if n.get("exif_lat") is not None), None
        )
        if anchor is not None and node.get("exif_lat") is not None:
            far_place = _haversine_km(
                node["exif_lat"], node["exif_lng"], anchor["exif_lat"], anchor["exif_lng"]
            ) > NEAR_KM

        if near_day and not far_place:
            current.append(node)
        else:
            groups.append([node])

    if undated:
        groups.append(undated)

    return groups


async def draft_groups(
    media_ids: list[str],
    author_id: Optional[str] = None,
    merge: bool = False,
) -> list[dict]:
    """올린 기록을 갈라서 묶음마다 초안 하나

    merge=True면 가르지 않고 전부 한 추억으로 본다. 화면의 "전부 하나의 추억으로"
    가 이 경로다 — AI가 잘못 갈랐을 때 사용자가 되돌릴 수 있어야 한다.
    """
    media_nodes = []
    for media_id in media_ids or []:
        node = graph_manager.get_node(media_id)
        if node and node.get("node_type") == NodeType.MEDIA:
            media_nodes.append(node)

    if not media_nodes:
        return []

    groups = [media_nodes] if merge else cluster_media(media_nodes)
    return [await draft([node["id"] for node in group], author_id) for group in groups]


async def draft(media_ids: list[str], author_id: Optional[str] = None) -> dict:
    """올린 기록들로 추억 초안을 만든다

    Returns:
        화면이 그대로 폼에 채울 수 있는 초안. 못 읽은 값은 빈 채로 둔다 —
        추측해서 채우면 사용자는 그것이 사실인지 추정인지 구분할 수 없다.
    """
    media_nodes = []
    for media_id in media_ids or []:
        node = graph_manager.get_node(media_id)
        if node and node.get("node_type") == NodeType.MEDIA:
            media_nodes.append(node)

    if not media_nodes:
        return {
            "media": [],
            "title": "",
            "date_start": None,
            "place": None,
            "person_ids": [],
            "person_candidates": [],
            "description": "",
            "evidence": [],
            "related": [],
            "ai_used": False,
        }

    # 사진에 무엇이 담겼는지 아직 모르면 여기서 읽는다. 위 표의 "주요 내용"이
    # 이 값이고, 채우던 경로가 없어져서 늘 비어 있었다 — 초안이 사진을 보지 않고
    # 제목을 쓰고 있었다. 자격증명이 없으면 조용히 지나간다 (services/vision.py).
    #
    # 상한을 준다. 아래에서 실제로 쓰는 설명은 세 개(scenes[:3])이고, 사용자는
    # 이 함수가 끝나기를 기다리고 있다.
    await vision.describe_missing(media_nodes, limit=vision.DRAFT_LIMIT)

    dates = sorted(
        _day(node.get("exif_date")) for node in media_nodes if node.get("exif_date")
    )
    day = dates[0] if dates else None
    last_day = dates[-1] if dates else None

    coords = [
        (node["exif_lat"], node["exif_lng"])
        for node in media_nodes
        if node.get("exif_lat") is not None and node.get("exif_lng") is not None
    ]
    lat = sum(c[0] for c in coords) / len(coords) if coords else None
    lng = sum(c[1] for c in coords) / len(coords) if coords else None

    tagged: list[str] = []
    for node in media_nodes:
        for person_id in node.get("detected_faces") or []:
            if person_id not in tagged and graph_manager.get_node(person_id):
                tagged.append(person_id)

    persons = [graph_manager.get_node(pid) or {} for pid in tagged]
    place = _nearest_place(lat, lng)
    scenes = [node["scene_description"] for node in media_nodes if node.get("scene_description")]
    candidates = _person_candidates(media_nodes, tagged, day, lat, lng)

    # 무엇을 근거로 이 초안을 썼는지. 화면이 그대로 보여준다 — AI가 조용히
    # 채우면 사용자는 어디까지가 사실인지 알 수 없다.
    evidence = []
    if day:
        evidence.append({
            "label": "촬영 시점",
            "detail": day + (f" ~ {last_day}" if last_day and last_day != day else ""),
        })
    if coords:
        evidence.append({
            "label": "좌표",
            "detail": f"{lat:.4f}, {lng:.4f}" + (f" · {place['name']} 근처" if place else ""),
        })
    if persons:
        evidence.append({
            "label": "지목된 사람",
            "detail": ", ".join(p.get("name", "") for p in persons),
        })
    if scenes:
        evidence.append({"label": "기록 내용", "detail": scenes[0]})
    if not evidence:
        evidence.append({
            "label": "읽을 정보 없음",
            "detail": "촬영 시점·좌표가 없어 추측하지 않았습니다. 아는 것만 알려주세요.",
        })

    when = _when_phrase(day)
    title, description = _fallback_text(
        when, place["name"] if place else None, persons, scenes, len(media_nodes)
    )
    # 기존 추억 후보는 한 번만 계산한다. 프롬프트에도 같은 목록이 들어간다 —
    # 같은 여행을 두 번 다른 이름으로 부르지 않게 하려는 것이다 (기획안 05).
    related = related_memories(day, lat, lng, tagged)
    ai_used = False

    # 읽어낸 사실이 하나도 없으면 모델을 부르지 않는다. "사진·영상 1개"만 주면
    # 모델은 "사진을 아직 받지 못했습니다"라고 답하고, 그 답은 어차피 버려진다.
    has_facts = bool(day or coords or persons or scenes)

    if has_facts and llm_client.is_enabled("extract"):
        facts = []
        if day:
            facts.append(f"촬영 시점: {day}" + (f" ~ {last_day}" if last_day != day else ""))
            if when:
                facts.append(f"오늘 기준 시점 표현: {when}")
        if place:
            facts.append(f"장소: {place['name']}")
        elif coords:
            facts.append(f"좌표: {lat:.4f}, {lng:.4f}")
        if persons:
            facts.append(
                "함께한 가족: "
                + ", ".join(
                    f"{p.get('name', '')}({p.get('relation', '')})" for p in persons
                )
            )
        if scenes:
            facts.append("기록 내용: " + " / ".join(scenes[:3]))
        facts.append(f"사진·영상 {len(media_nodes)}개")

        if related:
            facts.append(
                "이미 있는 비슷한 추억: "
                + "; ".join(f"{r['title']}({r.get('date_start') or '날짜 미상'})" for r in related)
            )

        result = await llm_client.complete_json(
            [
                {
                    "role": "system",
                    "content": (
                        "너는 가족 사진에서 읽어낸 사실만으로 추억의 제목과 설명을 쓰는 기록자야.\n"
                        "규칙:\n"
                        "1. 주어진 사실에 없는 내용을 만들지 마. 감정을 부풀리지 마.\n"
                        "2. 제목은 12자 안팎의 한국어 한 줄. 가족이 부를 만한 말로."
                        " 예: '작년 엄마아빠와 부산여행'\n"
                        "3. 설명은 1~2문장. 담담하게.\n"
                        '4. 반드시 {"title": "...", "description": "..."} JSON만 출력해.'
                    ),
                },
                {"role": "user", "content": "\n".join(facts)},
            ],
            max_tokens=400,
            purpose="extract",
        )

        if result:
            drafted_title = str(result.get("title") or "").strip()
            drafted_desc = str(result.get("description") or "").strip()
            if drafted_title:
                title = drafted_title
                ai_used = True
            if drafted_desc:
                description = drafted_desc
                ai_used = True

    return {
        "media": [
            {
                "id": node["id"],
                "media_type": node.get("media_type", MediaType.PHOTO.value),
                "file_path": node.get("file_path", ""),
                "thumbnail_path": node.get("thumbnail_path"),
                "original_filename": node.get("original_filename", ""),
                "exif_date": node.get("exif_date"),
                "exif_lat": node.get("exif_lat"),
                "exif_lng": node.get("exif_lng"),
                # 모델이 이 사진에서 읽은 것. 화면이 근거로 펼쳐 보인다.
                "scene_description": node.get("scene_description"),
                "scene_source": node.get("scene_source"),
            }
            for node in media_nodes
        ],
        "title": title,
        "date_start": day,
        "date_end": last_day if last_day and last_day != day else None,
        "place": place,
        "lat": lat,
        "lng": lng,
        "person_ids": tagged,
        # "사진 속 이분이 엄마인가요?" — 확정하지 않고 되묻는다 (기획안 06)
        "person_candidates": candidates,
        "description": description,
        "evidence": evidence,
        "related": related,
        # 초안을 모델이 썼는지. 화면이 그 사실을 밝힌다.
        "ai_used": ai_used,
    }
