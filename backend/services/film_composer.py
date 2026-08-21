"""Memory Film 구성 (기획안 02장 CORE · STORY)

한 추억에 연결된 사진·영상·음성을 30~60초 이야기로 묶는다.

기획안의 "진정성 원칙"을 데이터 구조로 지킨다.
  - 장면마다 원본 기록 id와 출처 문구를 들고 있다 (되짚을 수 있어야 한다)
  - 적용된 효과를 ai_effects에 남긴다. 화면은 이 목록을 반드시 노출한다
  - 무엇을 걸지는 서버만 정한다 (motion). 화면이 따로 고르면 라벨과 어긋난다
  - 카메라 움직임과 생성된 움직임은 라벨을 나눈다. 앞은 원본 픽셀을 옮긴 것이고
    뒤는 없던 픽셀이 생긴 것이라, 같은 문구로 덮으면 구분이 사라진다
  - 원본 영상은 효과를 걸지 않는다 (ai_effects가 빈 배열)
  - 내레이션은 확인된 기록 안에서만 쓴다. LLM이 없으면 사실만 적는다
  - 배경 음악은 무드만 정한다. 소리는 화면이 만들고, 그것이 원본 기록이 아니라는
    사실을 화면이 함께 밝힌다 (film_music)
  - 가족이 더한 기억에서 뽑은 맥락은 사진 선택·순서·자막·내레이션에만 얹는다
    (memory_context). 사진에서 확인되지 않은 행동을 사진의 내용으로 적지 않고,
    없던 장면을 만들지 않는다 — 맥락이 있어도 화면에 나가는 것은 원본 픽셀이다

세대별 옵션(child/adult/elder)은 장면 길이와 내레이션 어투를 바꾼다.
어르신에게는 전환을 늦추고, 아이에게는 문장을 짧게 한다.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Optional

from backend.config import MEDIA_DIR, MOTION_COVERS_PER_EVENT
from backend.services import (
    cover_picker,
    film_music,
    llm_client,
    memory_context,
    motion_clips,
    visibility,
)
from backend.services.graph_manager import graph_manager
from backend.models.graph_models import MediaType, NodeType

# 한 번 쓴 이야기는 다시 쓰지 않는다 — 같은 기록이면 같은 문장.
#
# Film을 다시 열거나 거실 화면(TV)이 같은 추억을 물을 때 새로 쓰면 문장이 매번
# 달라진다. 추모하는 자리에서 같은 기억이 매번 다르게 이야기되는 것은 이 제품이
# 지키려는 것과 정반대고, 모델을 부르는 값도 그만큼 나간다.
#
# 열쇠는 프롬프트에 실제로 들어간 것이다 (사실 목록 + 맥락 + 대상 세대). 기억이
# 더해지거나 고쳐지면 열쇠가 달라져 다시 쓴다. 공개 범위로 걸러진 뒤의 목록이라
# 보는 사람이 달라도 열쇠가 달라진다.
_stories: dict[str, str] = {}

# 사진 한 장이 화면에 머무는 기본 시간 (초)
PHOTO_SEC = 8
VIDEO_SEC = 10

# 사진 한 장이 머물 수 있는 최대 시간 — 기본 체류의 두 배 (대상 세대 배수가 함께 걸린다)
#
# 고른 길이를 채우려고 장면을 늘릴 때의 상한이다. 상한이 없으면 사진 두 장으로
# 60초를 채우려 한 장에 30초를 앉히게 되고, 그건 이야기가 아니라 정지 화면이다.
#
# 이 값이 곧 "이 추억으로 고를 수 있는 길이"를 정한다 (_ceiling -> max_sec).
# 화면은 채울 수 없는 길이를 잠근다 — 누를 수는 있는데 눌러도 영상이 그대로인
# 자리를 남기지 않는다.
PHOTO_MAX_SEC = 16

# 대상 세대별 장면 길이 배수 — 어르신은 천천히, 아이는 빠르게
AUDIENCE_PACE = {
    "child": 0.75,
    "adult": 1.0,
    "elder": 1.35,
}

AUDIENCE_TONE = {
    "child": "아이에게 말하듯 짧고 쉬운 문장으로. 인물 이름을 불러 준다.",
    "adult": "추억의 배경과 관계를 담아 담담하게.",
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

# 인물을 중심으로 들어가는 장면이 쓰는 쌍. 목록에서 꺼내 쓴다 — 문구를 여기서
# 새로 적으면 ALLOWED_EFFECTS와 갈라진다.
_MOTION_ZOOM_IN = CAMERA_MOTIONS[0]

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

    무엇이 움직일지는 사진 설명·추억 제목·장소 이름에서 고른다. 그래프에는
    메타데이터의 tags가 남지 않아서(시드가 옮기지 않는다) 문장에서 찾는다.
    """
    prompt = motion_clips.motion_prompt([
        photo.get("scene_description"),
        event.get("title"),
        event.get("description"),
        place_name,
    ])
    return motion_clips.request(photo["id"], _photo_file(photo), prompt)


def _record(event_id: str, viewer_id: Optional[str] = None) -> Optional[dict]:
    """이 추억의 기록 — 장면과 이야기가 같은 것을 본다

    보는 사람이 볼 수 없는 원본은 장면으로도, 내레이션의 근거로도 쓰지 않는다
    (기획안 08장). 그래서 걸러내는 자리는 하나여야 한다 — 이야기만 따로 뽑는
    story()가 다른 목록을 보면, 화면에 없는 사진을 근거로 이야기하게 된다.
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

    return {
        "event": event,
        "media": media,
        "memories": memories,
        "persons": [n for n in connected if n.get("node_type") == NodeType.PERSON],
        "place": graph_manager.get_node(event.get("location_id") or ""),
        "contexts": memory_context.from_memories(memories, {m["id"] for m in media}),
    }


async def story(
    event_id: str,
    audience: str = "adult",
    viewer_id: Optional[str] = None,
) -> str:
    """이 추억의 Film 이야기 — 문장만

    compose()를 부르지 않는다. 그쪽은 장면을 짜고 미세 모션 클립 생성까지
    맡기는데(40초·비용), TV는 만들지 않는다. 필요한 것은 문장뿐이다.

    같은 기록이면 같은 문장이 나온다 (_narration의 캐시). 그래서 앱에서 본 Film과
    거실에서 듣는 이야기가 글자까지 같다 — 같은 추억을 두 화면이 다르게
    이야기하면, 어느 쪽이 그 가족의 기억인지 알 수 없다.
    """
    record = _record(event_id, viewer_id)
    if not record:
        return ""

    place = record["place"]
    return await _narration(
        record["event"],
        record["memories"],
        record["persons"],
        place.get("name") if place else None,
        audience,
        record["contexts"],
    )


async def compose(
    event_id: str,
    length_sec: int = 45,
    audience: str = "adult",
    viewer_id: Optional[str] = None,
) -> Optional[dict]:
    """추억 하나로 Film 스토리보드를 만든다

    보는 사람이 볼 수 없는 원본은 장면으로도, 내레이션의 근거로도 쓰지 않는다.
    비공개로 바꾼 사진이 영상에서 다시 나오면 설정이 무의미해진다 (기획안 08장).
    """
    record = _record(event_id, viewer_id)
    if not record:
        return None

    event = record["event"]
    media = record["media"]
    memories = record["memories"]
    persons = record["persons"]
    place = record["place"]
    # 가족이 기억을 더할 때 그 문장에서 뽑아 둔 맥락 (services/memory_context.py).
    # 없으면 지금까지와 똑같이 동작한다 — 맥락은 얹히는 값이고 전제가 아니다.
    contexts = record["contexts"]

    photos = [m for m in media if m.get("media_type") == MediaType.PHOTO]
    videos = [m for m in media if m.get("media_type") == MediaType.VIDEO]
    audios = [m for m in media if m.get("media_type") == MediaType.AUDIO]
    # 맥락이 가리키는 사진을 앞으로 옮긴다. 빼지는 않는다 (memory_context.prioritize).
    photos = memory_context.prioritize(photos, contexts)

    pace = AUDIENCE_PACE.get(audience, 1.0)
    date_label = _date_label(event.get("date_start"))
    place_name = place.get("name") if place else None

    scenes: list[dict] = []
    clips = motion_clips.manifest()

    # 어느 사진을 움직이게 만들지 먼저 정한다.
    #
    # 사진이 상한보다 적으면 전부 만든다 — 미세 모션은 정적으로 보이는 사진도
    # 살리므로 세 장뿐인 추억에서 골라낼 이유가 없다. 상한은 사진 백 장인
    # 앨범 때문에 있다 (한 장에 약 $0.2).
    #
    # 이미 클립이 있는 사진이 그 자리를 차지한다. 미리 만들어 둔 것이 있으면
    # 그만큼 정원이 줄어 같은 추억에 또 만들지 않는다.
    #
    # 기본값에서는 기능을 켠 뒤에 생긴 추억만 만든다. 이미 쌓여 있던 앨범 전체를
    # 한꺼번에 만들면 지출이 한 번에 튄다 — 그쪽은 스크립트로 미리 만든다.
    covers: set[str] = set()
    already = sum(1 for photo in photos if photo["id"] in clips)
    room = MOTION_COVERS_PER_EVENT - already
    if motion_clips.enabled() and motion_clips.is_new_event(event_id) and room > 0:
        candidates = [photo for photo in photos if photo["id"] not in clips]
        covers = set(await cover_picker.pick(event, candidates, place_name, limit=room))

    # 첫 장면은 언제·어디인지 밝힌다. 이야기가 시작되는 자리다.
    for index, photo in enumerate(photos):
        scene_voice = audios[index] if index < len(audios) else None
        duration = round(PHOTO_SEC * pace)
        if scene_voice and scene_voice.get("duration_sec"):
            # 목소리가 잘리지 않게 그 장면만 늘린다
            duration = max(duration, int(scene_voice["duration_sec"]) + 1)

        # 이 사진을 가리키는 맥락과, 그 맥락의 인물이 사진에서 있는 자리.
        # 자리를 아는 것은 저장된 얼굴 위치뿐이고(MediaNode.face_boxes) 없는
        # 사진에서는 None이다 — 그때는 지금까지와 같은 움직임이 걸린다.
        context = memory_context.for_media(contexts, photo["id"])
        focus = memory_context.focus_of(context, photo)

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
            #
            # 맥락의 인물이 어디 있는지 아는 사진은 그 사람을 중심으로 천천히
            # 들어간다 (focus를 화면이 확대의 중심으로 쓴다). 라벨은 그대로
            # CAMERA_MOTIONS의 것을 쓴다 — 문구를 새로 만들면 허용 목록과 갈라진다.
            motion, label = (
                _MOTION_ZOOM_IN if focus else CAMERA_MOTIONS[index % len(CAMERA_MOTIONS)]
            )
            motion_url = None
            # 대표로 뽑힌 사진만 만들어 달라고 맡긴다. 즉시 돌아오고, 준비되면
            # 화면이 되물어 바꿔 끼운다 — 40초를 응답에서 기다리게 하지 않는다.
            if photo["id"] in covers:
                _request_clip(photo, event, place_name)

        scenes.append({
            "media_id": photo["id"],
            "thumb": thumb,
            "file_path": photo.get("file_path", ""),
            "subtitle": _subtitle(index, photo, date_label, place_name, context),
            "note": photo.get("scene_description") or "",
            "duration_sec": duration,
            "source_label": _source_label(photo, context),
            "ai_effects": [label],
            "motion": motion,
            "motion_url": motion_url,
            "voice_id": scene_voice["id"] if scene_voice else None,
            # --- 가족이 더한 기억에서 온 것 (없으면 빈 값) ---
            "context_caption": memory_context.caption(context) if context else "",
            "context_source": memory_context.source_note(context) if context else "",
            "context_contributor": memory_context.speaker_name(context),
            # 화면이 확대의 중심으로 쓸 지점 (0~1 비율). 원본 픽셀을 옮기는 것뿐이다.
            "focus": focus,
            # 나중에 image-to-video를 붙일 자리. 지금 들어가는 값은 인물 중심
            # 확대(subject-focus)뿐이고, 생성된 표현이 들어가면 그때는 라벨을
            # 나눠 적는다 (GENERATED_MOTION_LABEL과 같은 방식).
            "visual_treatment": "subject-focus" if focus else None,
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

    # 늘리는 것은 사진뿐이라 어느 장면이 사진인지 들고 간다. 장면 순서로 가르지
    # 않는 것은, 순서에 기대면 위쪽 조립 순서가 바뀔 때 조용히 어긋나기 때문이다.
    photo_ids = {photo["id"] for photo in photos}
    # _ceiling은 자르기 전 전체를 보고 잰다 — _stretch가 복사본을 늘리므로
    # scenes는 그대로 남지만, 순서를 바꿀 이유는 없다.
    max_sec = _ceiling(scenes, pace, photo_ids)
    # 자른 뒤에는 언제나 남은 시간을 채운다.
    #
    # 예전에는 뺀 장면이 없을 때만 채웠다. 남은 시간이 뺀 장면 몫이라고 봤는데,
    # 뺀 장면은 어느 쪽이든 나오지 않으므로 그 시간은 아무에게도 가지 않고 그냥
    # 사라졌다 — 45초를 골라도 33초짜리가 나오고(어르신용 · 자료가 많은 추억),
    # 화면에서는 45초 버튼이 켜진 채였다. 고른 길이가 지켜지지 않으면 길이를
    # 고르는 자리가 거짓말을 한다.
    #
    # 늘어나는 것은 사진 체류뿐이고 상한(PHOTO_MAX_SEC)도 그대로다. 영상만으로
    # 이루어진 추억은 늘릴 사진이 없어 여전히 목표에 못 미칠 수 있다 — 원본 영상의
    # 길이는 원본이 가진 것이라 늘리지 않는다. 그때 실제 길이는 total_sec이 밝힌다.
    fitted = _stretch(_fit(scenes, length_sec), length_sec, pace, photo_ids)
    narration = await _narration(event, memories, persons, place_name, audience, contexts)
    # 무엇을 깔지만 정한다. 소리는 화면이 만든다 (frontend/src/lib/filmMusic.ts).
    # 장면 배수를 함께 넘긴다 — 어르신에게 장면을 늦추면서 음악만 제 속도로 가면
    # 화면과 소리가 갈라진다.
    music = film_music.pick(event, place_name, pace=pace)

    # 지금 만들고 있는 것 중 이 화면에 실제로 나오는 장면만 알린다. 방금 맡긴
    # 것과 앞선 요청으로 이미 돌고 있는 것이 모두 여기 들어온다.
    in_flight = set(motion_clips.pending_ids())
    pending = [s["media_id"] for s in fitted if s["media_id"] in in_flight]

    return {
        "event_id": event_id,
        "title": _title(event, memories),
        "subtitle": " · ".join([p for p in (date_label, place_name) if p]),
        "narration": narration,
        # 배경 음악의 무드와 그것을 고른 근거. 화면이 이 무드로 소리를 만들고,
        # 앱이 만든 소리라는 사실을 근거와 함께 적는다.
        "music": music,
        "scenes": fitted,
        # 아직 만들고 있는 사진. 화면은 이게 비어 있지 않으면 잠시 뒤 되묻는다.
        "motion_pending": pending,
        "total_sec": sum(s["duration_sec"] for s in fitted),
        "audience": audience,
        "requested_sec": length_sec,
        # 이 추억·대상으로 채울 수 있는 최대 길이. 화면이 그보다 긴 선택지를 잠근다.
        "max_sec": max_sec,
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


def _stretch(
    scenes: list[dict],
    target: int,
    pace: float,
    photo_ids: set[str],
) -> list[dict]:
    """남은 시간을 사진 장면에 1초씩 나눠 담아 고른 길이를 채운다

    자르는 것만으로는 길이 선택이 절반만 동작했다. 사진 세 장뿐인 추억은
    30·45·60초 중 무엇을 골라도 24초 그대로여서, 고르는 자리가 있는데 고른 것이
    화면에 나타나지 않았다.

    늘리는 것은 사진뿐이다. 사진이 몇 초 머무는지는 우리가 정하는 것이지만,
    원본 영상의 길이는 원본이 가진 것이고 늘리면 없는 프레임을 채우는 셈이 된다.

    한 장의 상한은 PHOTO_MAX_SEC이다. 상한에 걸려 목표에 못 미치면 못 미친 채로
    돌려준다 — 그 길이는 애초에 화면에서 잠겨 있다 (_ceiling).
    """
    cap = round(PHOTO_MAX_SEC * pace)
    # 원본을 건드리지 않는다. 호출한 쪽이 같은 장면 목록으로 상한을 다시 잰다.
    grown = [dict(scene) for scene in scenes]
    room = [s for s in grown if s["media_id"] in photo_ids and s["duration_sec"] < cap]
    total = sum(s["duration_sec"] for s in grown)

    # 한 장에 몰지 않고 돌아가며 1초씩 얹는다 — 장면 길이가 고르게 벌어진다
    while room and total < target:
        for scene in room:
            if total >= target:
                break
            scene["duration_sec"] += 1
            total += 1
        room = [s for s in room if s["duration_sec"] < cap]

    return grown


def _ceiling(scenes: list[dict], pace: float, photo_ids: set[str]) -> int:
    """자료를 다 쓰고 사진을 상한까지 세워 뒀을 때 나오는 길이 (초)

    화면이 고를 수 있는 길이의 한계다. 목소리가 길어 이미 상한을 넘는 장면은
    그 길이가 그대로 한계에 들어간다 (줄이지는 않으므로).
    """
    cap = round(PHOTO_MAX_SEC * pace)
    return sum(
        max(scene["duration_sec"], cap)
        if scene["media_id"] in photo_ids
        else scene["duration_sec"]
        for scene in scenes
    )


def _date_label(date_start: Optional[str]) -> Optional[str]:
    if not date_start:
        return None
    parts = date_start.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}년 {int(parts[1])}월"
    return parts[0]


def _subtitle(
    index: int,
    photo: dict,
    date_label: Optional[str],
    place: Optional[str],
    context: Optional[dict] = None,
) -> str:
    """자막. 첫 장면은 시점·장소를, 이후는 장면 설명을 쓴다

    맥락이 가리키는 사진은 그 맥락을 자막으로 쓴다 ("엄마가 기억하는 부산 바다").
    언제·어디인지는 이야기 머리에 이미 적혀 있어서(board.subtitle) 첫 장면에서도
    잃는 것이 없다. 자막 문구는 memory_context가 만든다 — TV도 같은 문구를 쓰고,
    두 화면이 각자 조립하면 조용히 갈라진다.
    """
    if context:
        return memory_context.caption(context)

    if index == 0:
        return " · ".join([p for p in (date_label, place) if p]) or (
            photo.get("scene_description") or ""
        )

    description = photo.get("scene_description") or ""
    # 자막은 한 줄로 읽혀야 한다. 설명이 길면 첫 구절만 쓴다.
    if len(description) > 28:
        return description[:28].rstrip() + "…"
    return description


def _source_label(photo: dict, context: Optional[dict] = None) -> str:
    """이 장면의 근거. 맥락이 얹혔으면 그것이 누구의 기억인지도 함께 적는다

    "엄마의 기억이 더해진 장면"까지가 이 문구의 몫이다. 사진에 그 장면이 있다고
    말하지 않는다 — 확인 여부는 memory_context.source_note가 문구 안에서 가른다.
    """
    exif = photo.get("exif_date")
    if exif:
        label = "원본 사진 · EXIF " + exif[:10]
    else:
        label = "원본 사진 · " + (photo.get("original_filename") or photo["id"])

    if context:
        label += " · " + memory_context.source_note(context)
    return label


def _title(event: dict, memories: list[dict]) -> str:
    """제목은 추억 제목을 쓰되, 기억 문장이 있으면 그쪽이 더 이야기답다

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
    contexts: Optional[list[dict]] = None,
) -> str:
    """내레이션. 확인된 기록 안에서만 쓰고, LLM이 없으면 사실만 적는다

    가족이 더한 기억에서 뽑은 맥락도 함께 넘긴다. 원문을 대신하지 않는다 — 원문과
    맥락을 같이 주는 이유는, 원문만 주면 모델이 어느 장면을 말하는지 놓치고
    맥락만 주면 사람이 실제로 쓴 말을 잃기 때문이다.
    """
    facts = [
        f"추억: {event.get('title', '')}",
        f"날짜: {event.get('date_start') or '미상'}",
        f"장소: {place or '미상'}",
        # 이름과 호칭을 함께 넘긴다 (memory_context.person_label). 이름만 주면
        # "김영희가 함께했습니다"가 나오는데, 가족이 그 사람을 찾는 말은
        # "할머니"다. 반대로 호칭만 주면 이야기에 누구인지 이름이 남지 않는다.
        f"참여: {', '.join(memory_context.person_labels(persons)) or '미상'}",
    ]
    for memory in memories[:3]:
        speaker = graph_manager.get_node(memory.get("contributor_id") or "")
        label = memory_context.person_label(speaker) if speaker else ""
        facts.append(f"{label or '가족'}의 기억: {memory.get('content', '')}")

    context_lines = "\n".join(memory_context.prompt_line(c) for c in contexts or [])

    key = hashlib.sha1(
        "\n".join([*facts, context_lines, audience]).encode("utf-8")
    ).hexdigest()
    if key in _stories:
        return _stories[key]

    if not llm_client.is_enabled():
        _stories[key] = _plain_narration(event, memories, persons, place, contexts)
        return _stories[key]

    messages = [
        {
            "role": "system",
            "content": (
                "가족 기억 영상의 내레이션을 쓴다. 아래 [기록]에 있는 사실만 쓴다.\n"
                "기록에 없는 감정·장면·대화를 만들어내지 마라. 2~3문장.\n"
                "[기록]의 참여자는 한 명도 빼지 말고 모두 불러라. 그 사람이 무엇을"
                " 했는지는 기록에 있는 것만 쓴다.\n"
                "사람은 '김민수(아빠)'처럼 이름과 호칭을 함께 적는다. [기록]에 적힌"
                " 모양 그대로 쓰면 된다 — 이름만 쓰거나 호칭만 쓰지 마라.\n"
                "가족의 기억은 그 사람의 관점이다. 사진에 그 장면이 있다고 쓰지 말고,"
                " '엄마는 하늘이가 물장구치던 순간을 기억합니다'처럼 기억의 주인을"
                " 밝혀라.\n"
                "대괄호로 묶은 제목은 자료를 나누는 표시다. 본문에 옮겨 적지 마라.\n"
                + AUDIENCE_TONE.get(audience, AUDIENCE_TONE["adult"])
            ),
        },
        {
            "role": "user",
            "content": "[기록]\n"
            + "\n".join(facts)
            + (f"\n\n[가족이 기억하는 것]\n{context_lines}" if context_lines else ""),
        },
    ]

    narration = await llm_client.complete(messages, max_tokens=300)
    if not narration:
        # 모델에 닿지 못한 것은 담아 두지 않는다. 사실만 적은 문장으로 이번 화면을
        # 채우고, 다음에는 다시 물어본다.
        return _plain_narration(event, memories, persons, place, contexts)
    # 프롬프트 제목과 넘긴 사실 목록을 베껴 오면 떼어낸다. 프롬프트에 "옮기지
    # 마라"를 적어도 막히지 않는다 (interview_engine._clean_question과 같은 판단).
    narration = memory_context.strip_prompt_marks(narration)
    # 모델이 "아빠 김민수"라고 쓴 것을 "김민수(아빠)"로 맞춘다. 모델이 쓴 산문에만
    # 쓴다 — 아래 폴백은 가족의 원문을 그대로 인용하므로 지나지 않는다.
    narration = memory_context.label_person_mentions(narration, persons)
    # 프롬프트에 "참여자를 빼지 마라"를 적어도 모델은 기억 문장에 나온 사람만
    # 부른다. 빠진 사람은 여기서 한 줄로 잇는다 — 사진에서 직접 지목한 사람이
    # 이야기에 나오지 않으면, 지목이 저장되지 않은 것으로 보인다.
    _stories[key] = memory_context.ensure_persons_named(narration, persons)
    return _stories[key]


def _plain_narration(
    event: dict,
    memories: list[dict],
    persons: list[dict],
    place: Optional[str],
    contexts: Optional[list[dict]] = None,
) -> str:
    """LLM 없이 쓰는 내레이션 — 사실만 잇는다

    맥락이 있으면 그 한 줄도 잇는다. 문장의 주어는 기억한 사람이다
    (memory_context.narration_line) — 모델이 없을 때 사진에 없는 행동을 사진의
    내용처럼 적는 일이 가장 조용히 일어난다.
    """
    parts = []
    date_label = _date_label(event.get("date_start"))
    if date_label:
        parts.append(date_label)
    if place:
        parts.append(place)

    head = ", ".join(parts)
    # 이름과 호칭을 함께 적는다 ("김민수(아빠)"). 모델이 없을 때도 이야기에
    # 나오는 사람의 모양이 같아야 한다 — 같은 추억을 두 경로가 다르게 부르면
    # 어느 쪽이 그 가족의 말인지 알 수 없다.
    names = ", ".join(memory_context.person_labels(persons))

    sentences = []
    if head:
        sentences.append(f"{head}의 기록입니다.")
    if names:
        sentences.append(f"{names}이(가) 함께했습니다.")
    if memories:
        speaker = graph_manager.get_node(memories[0].get("contributor_id") or "")
        label = (memory_context.person_label(speaker) if speaker else "") or "가족"
        # 괄호로 끝나는 이름에는 은/는이 어색하다. 조사를 피해 적는다.
        sentences.append(f"{label}의 기억입니다. “{memories[0].get('content', '')}”")

    for context in (contexts or [])[:2]:
        line = memory_context.narration_line(context)
        if line and line not in sentences:
            sentences.append(line)

    return " ".join(sentences)


def anniversaries(today: Optional[date] = None, limit: int = 4) -> list[dict]:
    """다가오는 기념일 (기획안: 기념일·명절 자동 큐레이션)

    추억 날짜의 월·일이 다시 돌아오는 날을 세어 가까운 순으로 돌려준다.
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
