"""Memory Film 구성 (기획안 02장 CORE · STORY)

한 사건에 연결된 사진·영상·음성을 30~60초 이야기로 묶는다.

기획안의 "진정성 원칙"을 데이터 구조로 지킨다.
  - 장면마다 원본 기록 id와 출처 문구를 들고 있다 (되짚을 수 있어야 한다)
  - 적용된 효과를 ai_effects에 남긴다. 화면은 이 목록을 반드시 노출한다
  - 원본 영상은 효과를 걸지 않는다 (ai_effects가 빈 배열)
  - 내레이션은 확인된 기록 안에서만 쓴다. LLM이 없으면 사실만 적는다

세대별 옵션(child/adult/elder)은 장면 길이와 내레이션 어투를 바꾼다.
어르신에게는 전환을 늦추고, 아이에게는 문장을 짧게 한다.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from backend.services import llm_client
from backend.services.graph_manager import graph_manager
from backend.models.graph_models import MediaType, NodeType

# 사진 한 장이 화면에 머무는 기본 시간 (초)
PHOTO_SEC = 8
VIDEO_SEC = 10

# 대상 세대별 장면 길이 배수 — 어르신은 천천히, 아이는 빠르게
AUDIENCE_PACE = {
    "child": 0.75,
    "adult": 1.0,
    "elder": 1.35,
}

AUDIENCE_TONE = {
    "child": "아이에게 말하듯 짧고 쉬운 문장으로. 인물 이름을 불러 준다.",
    "adult": "사건의 배경과 관계를 담아 담담하게.",
    "elder": "천천히 읽히도록 문장을 길게 끊고, 당시 호칭을 그대로 쓴다.",
}

# 사진에 허용된 움직임. 기획안이 정한 범위를 넘지 않는다.
ALLOWED_MOTIONS = ["느린 패닝", "느린 줌 인", "미세 배경 움직임", "느린 줌 아웃"]


async def compose(
    event_id: str,
    length_sec: int = 45,
    audience: str = "adult",
) -> Optional[dict]:
    """사건 하나로 Film 스토리보드를 만든다"""
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    connected = graph_manager.get_connected_nodes(event_id)
    media = [n for n in connected if n.get("node_type") == NodeType.MEDIA]
    memories = [n for n in connected if n.get("node_type") == NodeType.MEMORY]
    persons = [n for n in connected if n.get("node_type") == NodeType.PERSON]
    place = graph_manager.get_node(event.get("location_id") or "")

    photos = [m for m in media if m.get("media_type") == MediaType.PHOTO]
    videos = [m for m in media if m.get("media_type") == MediaType.VIDEO]
    audios = [m for m in media if m.get("media_type") == MediaType.AUDIO]

    pace = AUDIENCE_PACE.get(audience, 1.0)
    date_label = _date_label(event.get("date_start"))
    place_name = place.get("name") if place else None

    scenes: list[dict] = []

    # 첫 장면은 언제·어디인지 밝힌다. 이야기가 시작되는 자리다.
    for index, photo in enumerate(photos):
        scene_voice = audios[index] if index < len(audios) else None
        duration = round(PHOTO_SEC * pace)
        if scene_voice and scene_voice.get("duration_sec"):
            # 목소리가 잘리지 않게 그 장면만 늘린다
            duration = max(duration, int(scene_voice["duration_sec"]) + 1)

        scenes.append({
            "media_id": photo["id"],
            "thumb": photo.get("thumbnail_path") or photo.get("file_path", ""),
            "file_path": photo.get("file_path", ""),
            "subtitle": _subtitle(index, photo, date_label, place_name),
            "note": photo.get("scene_description") or "",
            "duration_sec": duration,
            "source_label": _source_label(photo),
            # 사진에만 움직임을 준다. 순서대로 돌려 써서 같은 효과가 붙지 않게 한다.
            "ai_effects": [ALLOWED_MOTIONS[index % len(ALLOWED_MOTIONS)]],
            "voice_id": scene_voice["id"] if scene_voice else None,
        })

    # 원본 영상은 손대지 않고 그대로 끼운다
    for video in videos:
        scenes.append({
            "media_id": video["id"],
            "thumb": video.get("thumbnail_path") or (photos[0].get("file_path") if photos else ""),
            "file_path": video.get("file_path", ""),
            "subtitle": date_label or event.get("title", ""),
            "note": "원본 영상 구간",
            "duration_sec": round(VIDEO_SEC * pace),
            "source_label": "원본 영상 · " + (video.get("original_filename") or video["id"]),
            "ai_effects": [],
            "voice_id": None,
        })

    if not scenes:
        return None

    fitted = _fit(scenes, length_sec)
    narration = await _narration(event, memories, persons, place_name, audience)

    return {
        "event_id": event_id,
        "title": _title(event, memories),
        "subtitle": " · ".join([p for p in (date_label, place_name) if p]),
        "narration": narration,
        "scenes": fitted,
        "total_sec": sum(s["duration_sec"] for s in fitted),
        "audience": audience,
        "requested_sec": length_sec,
        # 요청한 길이에 맞추려고 뺀 장면 수. 화면이 "몇 장면이 빠졌다"고 밝힐 수 있게.
        "omitted_scenes": len(scenes) - len(fitted),
    }


def _fit(scenes: list[dict], target: int) -> list[dict]:
    """요청한 길이를 넘지 않게 장면을 자른다 (최소 한 장면은 남긴다)"""
    picked: list[dict] = []
    total = 0
    for scene in scenes:
        if picked and total + scene["duration_sec"] > target:
            break
        picked.append(scene)
        total += scene["duration_sec"]
    return picked


def _date_label(date_start: Optional[str]) -> Optional[str]:
    if not date_start:
        return None
    parts = date_start.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}년 {int(parts[1])}월"
    return parts[0]


def _subtitle(index: int, photo: dict, date_label: Optional[str], place: Optional[str]) -> str:
    """자막. 첫 장면은 시점·장소를, 이후는 장면 설명을 쓴다"""
    if index == 0:
        return " · ".join([p for p in (date_label, place) if p]) or (
            photo.get("scene_description") or ""
        )

    description = photo.get("scene_description") or ""
    # 자막은 한 줄로 읽혀야 한다. 설명이 길면 첫 구절만 쓴다.
    if len(description) > 28:
        return description[:28].rstrip() + "…"
    return description


def _source_label(photo: dict) -> str:
    exif = photo.get("exif_date")
    if exif:
        return "원본 사진 · EXIF " + exif[:10]
    return "원본 사진 · " + (photo.get("original_filename") or photo["id"])


def _title(event: dict, memories: list[dict]) -> str:
    """제목은 사건 제목을 쓰되, 기억 문장이 있으면 그쪽이 더 이야기답다

    다만 지어내지는 않는다. 가족이 실제로 남긴 문장에서만 가져온다.
    """
    title = event.get("title", "")
    if not memories:
        return title

    content = (memories[0].get("content") or "").strip()
    if not content:
        return title

    # 첫 문장이 짧으면 제목으로 쓸 만하다
    first = content.split(".")[0].strip()
    if 6 <= len(first) <= 28:
        return first
    return title


async def _narration(
    event: dict,
    memories: list[dict],
    persons: list[dict],
    place: Optional[str],
    audience: str,
) -> str:
    """내레이션. 확인된 기록 안에서만 쓰고, LLM이 없으면 사실만 적는다"""
    facts = [
        f"사건: {event.get('title', '')}",
        f"날짜: {event.get('date_start') or '미상'}",
        f"장소: {place or '미상'}",
        f"참여: {', '.join(p.get('name', '') for p in persons) or '미상'}",
    ]
    for memory in memories[:3]:
        speaker = graph_manager.get_node(memory.get("contributor_id") or "")
        name = speaker.get("name") if speaker else "가족"
        facts.append(f"{name}의 기억: {memory.get('content', '')}")

    if not llm_client.is_enabled():
        return _plain_narration(event, memories, persons, place)

    messages = [
        {
            "role": "system",
            "content": (
                "가족 기억 영상의 내레이션을 쓴다. 아래 [기록]에 있는 사실만 쓴다.\n"
                "기록에 없는 감정·장면·대화를 만들어내지 마라. 2~3문장.\n"
                + AUDIENCE_TONE.get(audience, AUDIENCE_TONE["adult"])
            ),
        },
        {"role": "user", "content": "[기록]\n" + "\n".join(facts)},
    ]

    narration = await llm_client.complete(messages, max_tokens=300)
    if not narration:
        return _plain_narration(event, memories, persons, place)
    return narration.strip()


def _plain_narration(
    event: dict,
    memories: list[dict],
    persons: list[dict],
    place: Optional[str],
) -> str:
    """LLM 없이 쓰는 내레이션 — 사실만 잇는다"""
    parts = []
    date_label = _date_label(event.get("date_start"))
    if date_label:
        parts.append(date_label)
    if place:
        parts.append(place)

    head = ", ".join(parts)
    names = ", ".join(p.get("name", "") for p in persons if p.get("name"))

    sentences = []
    if head:
        sentences.append(f"{head}의 기록입니다.")
    if names:
        sentences.append(f"{names}이(가) 함께했습니다.")
    if memories:
        speaker = graph_manager.get_node(memories[0].get("contributor_id") or "")
        name = speaker.get("name") if speaker else "가족"
        sentences.append(f"{name}은 이렇게 기억합니다. “{memories[0].get('content', '')}”")

    return " ".join(sentences)


def anniversaries(today: Optional[date] = None, limit: int = 4) -> list[dict]:
    """다가오는 기념일 (기획안: 기념일·명절 자동 큐레이션)

    사건 날짜의 월·일이 다시 돌아오는 날을 세어 가까운 순으로 돌려준다.
    """
    today = today or date.today()
    items = []

    for event in graph_manager.get_events():
        date_start = event.get("date_start")
        if not date_start:
            continue

        try:
            year, month, day = (int(v) for v in date_start.split("-")[:3])
            anniversary = date(today.year, month, day)
            if anniversary < today:
                anniversary = date(today.year + 1, month, day)
        except (ValueError, TypeError):
            continue

        years = anniversary.year - year
        media_count = sum(
            1
            for n in graph_manager.get_connected_nodes(event["id"])
            if n.get("node_type") == NodeType.MEDIA
        )

        items.append({
            "date": anniversary.isoformat(),
            "label": f"{event.get('title', '')} {years}주년",
            "event_id": event["id"],
            "days_left": (anniversary - today).days,
            "reason": f"{date_start} 기록이 있습니다 · 자료 {media_count}개",
        })

    items.sort(key=lambda item: item["days_left"])
    return items[:limit]
