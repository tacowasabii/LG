"""사건의 대표 사진 고르기 — 어느 사진을 움직이게 만들지

사진이 상한보다 적으면 **전부** 만든다. 미세 모션은 파도가 치거나 머리카락·
옷자락이 살짝 흔들리는 정도라, 정적으로 보이는 사진도 만들면 살아난다. 세 장뿐인
사건에서 한 장만 고를 이유가 없다.

상한을 두는 것은 사진 백 장인 앨범 때문이다 (한 장에 약 $0.2). 그때는 대표를
골라 그만큼만 만든다. 고르는 데 모델을 쓴다 — 어느 사진이 그날을 대표하는지는
목록 순서보다 모델이 낫다.

한 번 고른 것은 지킨다. 고를 때마 달라지면 방문마다 다른 사진을 만들어 돈이
계속 나간다. 선택은 STATE_DIR에 남고, 그 사진이 사라지지 않는 한 다시 묻지
않는다.

모델이 없거나 답이 이상하면 앞에서부터 채운다. 키를 설정하지 않은 사람의 화면도
같은 방식으로 동작해야 한다.
"""

from __future__ import annotations

import json
import threading
from typing import Optional

from backend.config import MOTION_COVERS_FILE, MOTION_COVERS_PER_EVENT
from backend.services import llm_client

_lock = threading.Lock()


def _read() -> dict:
    try:
        data = json.loads(MOTION_COVERS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(event_id: str, media_ids: list[str], by: str, reason: str) -> None:
    with _lock:
        current = _read()
        # 이미 고른 것에 더한다. 정원이 남아 다시 고를 때 앞선 선택을 잃지 않는다.
        before = current.get(event_id, {}).get("media_ids", [])
        merged = list(dict.fromkeys([*before, *media_ids]))
        current[event_id] = {"media_ids": merged, "by": by, "reason": reason[:200]}
        MOTION_COVERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MOTION_COVERS_FILE.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def cached(event_id: str) -> Optional[dict]:
    """이 사건에 대해 이미 고른 것 (아직 묻지 않았으면 None)"""
    entry = _read().get(event_id)
    if isinstance(entry, dict) and isinstance(entry.get("media_ids"), list):
        return entry
    return None


async def _by_model(
    event: dict, photos: list[dict], place: Optional[str], limit: int
) -> Optional[tuple[list[str], str]]:
    """모델에게 고르게 한다

    사진을 보여주지 않는다 — EXAONE 게이트웨이는 이미지를 받지 않는다. 대신
    사진 설명을 읽게 한다. 그 설명 자체가 사진을 본 결과라서(scene_source가
    ai_vision) 한 다리를 건너 사진을 보는 셈이다.
    """
    if not llm_client.is_enabled("extract"):
        return None

    listing = "\n".join(
        f"{i + 1}. {photo['id']} — {photo.get('scene_description') or '설명 없음'}"
        for i, photo in enumerate(photos)
    )
    prompt = (
        f"사건: {event.get('title', '')}\n"
        f"장소: {place or '미상'}\n\n"
        f"사진 목록 ({len(photos)}장):\n{listing}\n\n"
        f"이 중에서 그날을 가장 잘 대표하는 사진 {limit}장을 고르세요.\n"
        "이 사진들은 짧은 영상으로 만들어 화면에서 살짝 움직이게 됩니다.\n\n"
        "고르는 기준 (순서대로):\n"
        "1. 그날이 어떤 날이었는지 한 장으로 보여주는가 — 함께한 사람들이 나오고,\n"
        "   장소와 상황이 읽히는 사진\n"
        "2. 비슷한 사진이 여러 장이면 그중 하나만 고르세요 (같은 장면 반복 금지)\n"
        "3. 위 조건이 비슷하면, 물·불꽃·바람처럼 저절로 움직이는 것이 있는 사진을\n"
        "   우선하세요 — 영상으로 만들 때 더 살아납니다\n\n"
        f"반드시 {limit}장을 고르세요. media_ids는 위 목록에 있는 id만 씁니다.\n"
        "JSON만 답하세요.\n"
        '{"media_ids": ["..."], "reason": "한 문장"}'
    )
    result = await llm_client.complete_json(
        [
            {"role": "system", "content": "사진 설명을 읽고 대표를 고르는 도구다. JSON만 답한다."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=300,
        purpose="extract",
    )
    if not isinstance(result, dict) or not isinstance(result.get("media_ids"), list):
        return None

    known = {photo["id"] for photo in photos}
    # 모델이 목록에 없는 id를 만들어 낼 수 있다. 있는 것만 남긴다.
    picked = list(dict.fromkeys(
        media_id for media_id in result["media_ids"]
        if isinstance(media_id, str) and media_id in known
    ))[:limit]
    if not picked:
        return None
    return picked, str(result.get("reason") or "")


async def pick(
    event: dict,
    photos: list[dict],
    place: Optional[str] = None,
    limit: int = MOTION_COVERS_PER_EVENT,
) -> list[str]:
    """이 사건에서 움직이게 만들 사진을 고른다

    photos는 아직 클립이 없는 후보만 넘긴다. limit은 남은 정원이다.
    """
    if not photos or limit <= 0:
        return []

    # 후보가 정원 안에 들어오면 고를 것이 없다 — 전부가 대표다. 모델을 부르지
    # 않는다. "셋 중 셋을 고르라"고 묻는 것은 값만 쓰고 답이 정해진 질문이다.
    if len(photos) <= limit:
        return [photo["id"] for photo in photos]

    known = {photo["id"] for photo in photos}
    remembered = cached(event["id"])
    if remembered:
        kept = [media_id for media_id in remembered["media_ids"] if media_id in known]
        if len(kept) >= limit:
            return kept[:limit]
        # 골라 둔 것이 정원보다 적으면 (만들어진 것이 빠져 정원이 남았다)
        # 남은 자리만 다시 고른다. 앞선 선택은 그대로 지킨다.
        limit -= len(kept)
        photos = [photo for photo in photos if photo["id"] not in kept]
        if not photos:
            return kept
    else:
        kept = []

    chosen = await _by_model(event, photos, place, limit)
    if chosen:
        media_ids, reason = chosen
        by = "llm"
    else:
        # 앞에서부터 채운다. 목록 순서는 시간순이라 아무 기준이 없는 것은 아니다.
        media_ids = [photo["id"] for photo in photos[:limit]]
        reason = "모델 없이 앞에서부터 골랐다"
        by = "rule"

    _write(event["id"], media_ids, by, reason)
    return [*kept, *media_ids]
