"""Memory Film 구성 (기획안 02장 CORE · STORY)

한 사건에 연결된 사진·영상·음성을 30~60초 이야기로 묶는다.

기획안의 "진정성 원칙"을 데이터 구조로 지킨다.
  - 장면마다 원본 기록 id와 출처 문구를 들고 있다 (되짚을 수 있어야 한다)
  - 적용된 효과를 ai_effects에 남긴다. 화면은 이 목록을 반드시 노출한다
  - 무엇을 걸지는 서버만 정한다 (motion). 화면이 따로 고르면 라벨과 어긋난다
  - 카메라 움직임과 생성된 움직임은 라벨을 나눈다. 앞은 원본 픽셀을 옮긴 것이고
    뒤는 없던 픽셀이 생긴 것이라, 같은 문구로 덮으면 구분이 사라진다
  - 원본 영상은 효과를 걸지 않는다 (ai_effects가 빈 배열)
  - 내레이션은 확인된 기록 안에서만 쓴다. LLM이 없으면 사실만 적는다

세대별 옵션(child/adult/elder)은 장면 길이와 내레이션 어투를 바꾼다.
어르신에게는 전환을 늦추고, 아이에게는 문장을 짧게 한다.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from backend.config import MEDIA_DIR, MOTION_COVERS_PER_EVENT
from backend.services import cover_picker, llm_client, motion_clips, visibility
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

# 사진에 걸리는 카메라 움직임. 원본 픽셀을 옮기는 것뿐이고 없던 것을 만들지 않는다.
#
# (화면이 적용할 key, 사람이 읽을 라벨) 쌍으로 묶어 둔다. 예전에는 라벨만 여기 있고
# 실제 효과는 화면이 따로 골랐는데, 두 목록의 순서가 달라서 표시와 적용이 전부
# 어긋나 있었다 — "미세 배경 움직임"이라 적힌 장면에서 줌 아웃이 걸렸다.
# 무엇을 걸지 한 자리에서 정해야 ai_effects가 사실이 된다.
CAMERA_MOTIONS = [
    ("zoom-in", "느린 줌 인"),
    ("pan-left", "느린 패닝"),
    ("zoom-out", "느린 줌 아웃"),
    ("pan-right", "느린 패닝"),
]

# 미리 만들어 둔 클립을 재생하는 장면의 라벨. 카메라 움직임과 구분해서 적는다 —
# 이쪽은 원본에 없던 픽셀이 생긴 것이고, 둘을 같은 문구로 덮으면 "무엇이 원본이고
# 무엇이 생성인지" 화면에서 읽히게 한다는 진정성 원칙이 무의미해진다.
#
# 무엇이 움직이는지까지 적지 않는다. 사진마다 다르고(파도 · 랜턴 불꽃 · 촛불)
# 틀리게 적으면 없는 것을 밝힌 셈이 된다. 무엇을 넣었는지는 manifest의 prompt에
# 남아 있고, 화면에서 필요한 구분은 "생성이냐 아니냐"까지다.
GENERATED_MOTION_LABEL = "AI 생성 미세 움직임"
# 인물 영역을 원본 픽셀로 되돌린 클립에만 붙인다 (build_motion_covers.py의 마스크)
SUBJECT_PRESERVED_NOTE = " · 인물은 원본"

# 화면에 나갈 수 있는 효과 문구 전체. Trust Harness와 tests/test_film.py가
# 이것으로 검사한다 — 라벨을 늘릴 때 허용 목록도 같이 늘어나게 한 자리에 둔다.
ALLOWED_EFFECTS = frozenset(
    {label for _, label in CAMERA_MOTIONS}
    | {GENERATED_MOTION_LABEL, GENERATED_MOTION_LABEL + SUBJECT_PRESERVED_NOTE}
)


def generated_label(clip: dict) -> str:
    """생성 클립을 재생하는 장면의 AI 라벨

    화면이 나중에 클립을 바꿔 끼울 때도 이 값을 받아 쓴다. 라벨을 화면에서
    조립하면 서버가 붙이는 것과 갈라지고, 그게 정확히 예전에 표시와 적용이
    어긋났던 원인이다.
    """
    label = GENERATED_MOTION_LABEL
    if clip.get("subject_preserved"):
        label += SUBJECT_PRESERVED_NOTE
    return label


def _photo_file(photo: dict) -> Path:
    """서빙되는 사진의 실제 경로

    file_path는 URL(/media-files/…)이라 그대로는 열 수 없다. 이름만 떼어
    MEDIA_DIR에서 찾는다 — 시드가 넣은 것이든 사용자가 올린 것이든 거기 있다.
    """
    return MEDIA_DIR / Path(photo.get("file_path", "")).name


def _request_clip(photo: dict, event: dict, place_name: Optional[str]) -> bool:
    """이 사진의 클립을 만들어 달라고 맡긴다 (즉시 돌아온다)

    무엇이 움직일지는 사진 설명·사건 제목·장소 이름에서 고른다. 그래프에는
    메타데이터의 tags가 남지 않아서(시드가 옮기지 않는다) 문장에서 찾는다.
    """
    prompt = motion_clips.motion_prompt([
        photo.get("scene_description"),
        event.get("title"),
        event.get("description"),
        place_name,
    ])
    return motion_clips.request(photo["id"], _photo_file(photo), prompt)


async def compose(
    event_id: str,
    length_sec: int = 45,
    audience: str = "adult",
    viewer_id: Optional[str] = None,
) -> Optional[dict]:
    """사건 하나로 Film 스토리보드를 만든다

    보는 사람이 볼 수 없는 원본은 장면으로도, 내레이션의 근거로도 쓰지 않는다.
    비공개로 바꾼 사진이 영상에서 다시 나오면 설정이 무의미해진다 (기획안 08장).
    """
    event = graph_manager.get_node(event_id)
    if not event or event.get("node_type") != NodeType.EVENT:
        return None

    connected = graph_manager.get_connected_nodes(event_id)
    media = visibility.filter_media(
        [n for n in connected if n.get("node_type") == NodeType.MEDIA], viewer_id
    )
    memories = visibility.filter_memories(
        [n for n in connected if n.get("node_type") == NodeType.MEMORY], viewer_id
    )
    persons = [n for n in connected if n.get("node_type") == NodeType.PERSON]
    place = graph_manager.get_node(event.get("location_id") or "")

    photos = [m for m in media if m.get("media_type") == MediaType.PHOTO]
    videos = [m for m in media if m.get("media_type") == MediaType.VIDEO]
    audios = [m for m in media if m.get("media_type") == MediaType.AUDIO]

    pace = AUDIENCE_PACE.get(audience, 1.0)
    date_label = _date_label(event.get("date_start"))
    place_name = place.get("name") if place else None

    scenes: list[dict] = []
    clips = motion_clips.manifest()

    # 어느 사진을 움직이게 만들지 먼저 정한다.
    #
    # 사진이 상한보다 적으면 전부 만든다 — 미세 모션은 정적으로 보이는 사진도
    # 살리므로 세 장뿐인 사건에서 골라낼 이유가 없다. 상한은 사진 백 장인
    # 앨범 때문에 있다 (한 장에 약 $0.2).
    #
    # 이미 클립이 있는 사진이 그 자리를 차지한다. 미리 만들어 둔 것이 있으면
    # 그만큼 정원이 줄어 같은 사건에 또 만들지 않는다.
    covers: set[str] = set()
    already = sum(1 for photo in photos if photo["id"] in clips)
    room = MOTION_COVERS_PER_EVENT - already
    if motion_clips.enabled() and room > 0:
        candidates = [photo for photo in photos if photo["id"] not in clips]
        covers = set(await cover_picker.pick(event, candidates, place_name, limit=room))

    # 첫 장면은 언제·어디인지 밝힌다. 이야기가 시작되는 자리다.
    for index, photo in enumerate(photos):
        scene_voice = audios[index] if index < len(audios) else None
        duration = round(PHOTO_SEC * pace)
        if scene_voice and scene_voice.get("duration_sec"):
            # 목소리가 잘리지 않게 그 장면만 늘린다
            duration = max(duration, int(scene_voice["duration_sec"]) + 1)

        thumb = photo.get("thumbnail_path") or photo.get("file_path", "")
        clip = clips.get(photo["id"])
        if clip and clip.get("file"):
            # 미리 만든 클립이 있으면 그것을 재생하고 카메라 움직임은 걸지 않는다.
            # 화면 안에서 이미 무언가 움직이는데 프레임까지 밀면 어지럽다.
            motion = None
            motion_url = clip["file"]
            label = generated_label(clip)
            # 클립의 첫 프레임을 정지 이미지로 쓴다. 자동재생이 막힌 환경(iOS
            # 저전력 모드)에서 보이는 것이 이것이고, 썸네일(300x300 크롭)보다
            # 클립과 어긋나지 않는다.
            thumb = clip.get("poster") or thumb
        else:
            # 클립이 없는 사진은 지금까지처럼 카메라만 움직인다.
            # 순서대로 돌려 써서 같은 효과가 연달아 붙지 않게 한다.
            motion, label = CAMERA_MOTIONS[index % len(CAMERA_MOTIONS)]
            motion_url = None
            # 대표로 뽑힌 사진만 만들어 달라고 맡긴다. 즉시 돌아오고, 준비되면
            # 화면이 되물어 바꿔 끼운다 — 40초를 응답에서 기다리게 하지 않는다.
            if photo["id"] in covers:
                _request_clip(photo, event, place_name)

        scenes.append({
            "media_id": photo["id"],
            "thumb": thumb,
            "file_path": photo.get("file_path", ""),
            "subtitle": _subtitle(index, photo, date_label, place_name),
            "note": photo.get("scene_description") or "",
            "duration_sec": duration,
            "source_label": _source_label(photo),
            "ai_effects": [label],
            "motion": motion,
            "motion_url": motion_url,
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
            # 원본 영상에는 아무 효과도 걸지 않는다. motion을 비워 두지 않으면
            # 화면이 "원본 그대로"라고 적어 놓고 썸네일을 움직이게 된다.
            "ai_effects": [],
            "motion": None,
            "motion_url": None,
            "voice_id": None,
        })

    if not scenes:
        return None

    fitted = _fit(scenes, length_sec)
    narration = await _narration(event, memories, persons, place_name, audience)

    # 지금 만들고 있는 것 중 이 화면에 실제로 나오는 장면만 알린다. 방금 맡긴
    # 것과 앞선 요청으로 이미 돌고 있는 것이 모두 여기 들어온다.
    in_flight = set(motion_clips.pending_ids())
    pending = [s["media_id"] for s in fitted if s["media_id"] in in_flight]

    return {
        "event_id": event_id,
        "title": _title(event, memories),
        "subtitle": " · ".join([p for p in (date_label, place_name) if p]),
        "narration": narration,
        "scenes": fitted,
        # 아직 만들고 있는 사진. 화면은 이게 비어 있지 않으면 잠시 뒤 되묻는다.
        "motion_pending": pending,
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
