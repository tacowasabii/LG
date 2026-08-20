"""사진에서 장면 설명 읽기 (SourceType.AI_VISION)

`scene_description`은 사진이 가진 유일한 텍스트다 (stores/base.py 주석). 그런데
그 값을 채우던 유일한 경로(`POST /api/media/supplement`)가 추억 리팩터링에서
사라져서, 올린 사진은 영구히 비어 있게 됐다.

읽는 곳은 넷이다.
    추억 초안        memory_drafter — "주요 내용"
    채팅 컨텍스트    chat_engine    — "장면: …"
    검색 가중치      graph_search   — 사진을 내용으로 찾는다
    Postgres 색인    stores/base    — trigram 검색 대상

여기서 지키는 선 셋.

1. **사람을 식별하지 않는다.** 프롬프트로 막고, 구조로도 막는다 — 이 모듈은
   `scene_description` 한 필드만 쓰고 `detected_faces`에는 절대 손대지 않는다.
   가족 구성원 식별은 생체정보이고, 범용 모델이 틀리면 남의 사진에 엉뚱한 사람이
   붙는다. 누가 있는지는 사람이 지목한다 (event_resolver.set_media_persons).

2. **못 읽으면 비워 둔다.** 자격증명이 없거나 호출이 실패하면 아무것도 쓰지
   않는다. 규칙 기반으로 "사진 한 장" 같은 문장을 만들지 않는다 — 없는 것보다
   나쁘다.

3. **한 번만 읽는다.** 결과를 그래프에 저장하고, 이미 있는 사진은 건너뛴다.
   초안을 다시 만들 때마다 같은 사진을 다시 보지 않는다.

출처는 `scene_source`에 `ai_vision`으로 남는다. 노드 전체의 `source`(사진은
보통 exif)와 다른 축이다 — 날짜는 카메라가 적었고 설명은 모델이 썼다.
음성의 `transcript_source`와 같은 구조다.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Optional

from PIL import Image

from backend.config import MEDIA_DIR
from backend.models.graph_models import MediaType, NodeType, SourceType
from backend.services import llm_client
from backend.services.graph_manager import graph_manager

# 모델에 보내기 전에 줄이는 한 변 최대 길이.
# 장면을 알아보는 데 이보다 큰 그림이 필요하지 않고, 크게 보내면 느리고 비싸다.
MAX_SIDE = 1024

# 한 번에 동시에 볼 사진 수. 한 묶음이 수십 장일 수 있어 상한을 둔다.
CONCURRENCY = 4

# 초안을 만들 때 읽을 사진 수.
#
# 실측 장당 8초라서 상한이 없으면 사진 20장 묶음에서 초안이 2분 넘게 걸린다.
# 그런데 초안이 실제로 쓰는 설명은 세 개다 (memory_drafter: scenes[:3]).
# 나머지는 읽어도 초안에 들어가지 않으니 여기서 자른다.
#
# 검색·채팅은 모든 사진의 설명이 있으면 더 좋아진다. 그건 요청 안에서 할 일이
# 아니라 따로 돌린다 — scripts/describe_photos.py.
DRAFT_LIMIT = 3

BASE_RULES = """- 보이는 것만 적어라. 계절·감정·사연·장소 이름을 추측하지 마라.
- 글자가 찍혀 있으면 그대로 옮겨도 된다 (간판, 현수막 등).
- 설명만 답하라. "이 사진은"으로 시작하지 말고 머리말도 붙이지 마라."""

PROMPT = """이 사진에 무엇이 담겼는지 한국어 한두 문장으로 적어라.

지킬 것:
- 사람이 누구인지 말하지 마라. 이름도, 가족 관계도 추측하지 마라.
  사람이 있으면 "두 사람", "아이 한 명"처럼 수와 행동만 적는다.
""" + BASE_RULES


def _named_prompt(people: list[str]) -> str:
    """이 사진에 누가 있는지 아는 경우의 프롬프트

    얼굴 인식이 알아낸 사람(services/faces.py)이나 사람이 지목한 사람을 넣는다.
    모델이 얼굴을 보고 누구인지 판정하는 것이 아니라, **이미 확인된 이름을**
    문장에 쓰게 하는 것이다 — 그래서 "두 사람이"가 아니라 "아빠와 딸이"가 된다.

    여기서도 새 사람을 만들지 못하게 막는다. 준 목록에 없는 이름을 쓰면
    그래프에 없는 가족이 설명에 등장한다.
    """
    listed = " · ".join(people)
    return f"""이 사진에 무엇이 담겼는지 한국어 한두 문장으로 적어라.

이 사진에 있는 사람은 다음과 같다고 이미 확인되었다:
{listed}

지킬 것:
- 위 목록의 호칭을 그대로 써서 누가 무엇을 하고 있는지 적어라.
  예: "아빠와 딸이 해변에서 물놀이를 하고 있다."
- **목록에 없는 사람을 만들지 마라.** 사진에 사람이 더 보이면 "다른 사람들"처럼
  뭉뚱그리고 이름을 붙이지 마라.
- 목록에 있는 사람이 사진에서 안 보이면 억지로 넣지 마라.
- 누가 누구인지 새로 판정하지 마라. 위 목록이 사실이다.
""" + BASE_RULES


def _load_for_model(file_path: str) -> Optional[tuple[bytes, str]]:
    """사진을 모델에 보낼 크기로 줄여 JPEG 바이트로

    파일이 없거나 열리지 않으면 None. 여기서 실패하는 것은 정상 경로다 —
    지워진 파일, 지원하지 않는 형식이 섞여 들어온다.
    """
    name = Path(file_path or "").name
    if not name:
        return None

    path = MEDIA_DIR / name
    if not path.exists():
        return None

    try:
        with Image.open(path) as img:
            # 투명도·팔레트가 있는 이미지는 JPEG로 저장할 수 없다
            img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=85)
            return buffer.getvalue(), "jpeg"
    except Exception as e:
        print(f"[vision] {name} 을 읽지 못했습니다 ({type(e).__name__}: {e})", flush=True)
        return None


def _known_people(node: dict) -> list[str]:
    """이 사진에 있다고 확인된 사람들의 호칭 (없으면 빈 목록)

    얼굴 인식이 채웠거나 사람이 지목한 detected_faces를 읽는다. 관계를 함께
    적는다 — "김하늘"보다 "딸 김하늘"이 문장에 쓰기 쉽다.
    """
    labels = []
    for person_id in node.get("detected_faces") or []:
        person = graph_manager.get_node(person_id)
        if not person or person.get("node_type") != NodeType.PERSON:
            continue
        name = person.get("name") or ""
        relation = person.get("relation") or ""
        labels.append(f"{relation} {name}".strip() if relation else name)
    return [l for l in labels if l]


async def _describe_one(node: dict) -> bool:
    """사진 한 장의 설명을 채운다. 채웠으면 True"""
    loaded = _load_for_model(node.get("file_path", ""))
    if not loaded:
        return False

    image_bytes, fmt = loaded
    people = _known_people(node)
    prompt = _named_prompt(people) if people else PROMPT
    text = await llm_client.describe_image(image_bytes, fmt, prompt)
    if not text:
        return False

    # 모델이 문단으로 답하는 경우가 있어 한 줄로 모은다
    description = " ".join(text.split())

    graph_manager.update_node(node["id"], {
        "scene_description": description,
        "scene_source": SourceType.AI_VISION.value,
    })
    # 부르는 쪽이 방금 읽은 노드 dict를 그대로 쓰고 있으므로 함께 맞춘다
    node["scene_description"] = description
    node["scene_source"] = SourceType.AI_VISION.value
    return True


def _needs_description(node: dict) -> bool:
    return (
        node.get("media_type") == MediaType.PHOTO
        and not (node.get("scene_description") or "").strip()
    )


async def describe_missing(media_nodes: list[dict], limit: Optional[int] = None) -> int:
    """설명이 없는 사진들을 채운다

    이미 있는 사진, 사진이 아닌 기록, 파일이 없는 기록은 건너뛴다.
    자격증명이 없으면 아무것도 하지 않고 0을 돌려준다 (조용히 지나간다).

    Args:
        limit: 읽을 사진 수 상한. 사용자를 기다리게 하는 경로에서는 반드시 준다
            (DRAFT_LIMIT). None이면 전부 읽는다 — 스크립트에서만 쓴다.

    Returns:
        새로 채운 사진 수
    """
    targets = [node for node in media_nodes if _needs_description(node)]
    if limit is not None:
        targets = targets[:limit]
    if not targets or not llm_client.bedrock_enabled():
        return 0

    filled = 0

    # 첫 장은 혼자 보낸다. 이 망에서는 새 연결의 첫 요청이 자주 끊기는데
    # (llm_client._bedrock_client 주석), 동시에 여러 개를 열면 그 확률이 곱해진다.
    # 한 장으로 연결을 세워 두면 나머지는 그 연결을 나눠 쓴다.
    if await _describe_one(targets[0]):
        filled += 1
    rest = targets[1:]

    # 상한을 두고 나눠 돈다. 한 묶음에 사진 40장이 오면 동시에 40번 부를 수 없다.
    for start in range(0, len(rest), CONCURRENCY):
        batch = rest[start:start + CONCURRENCY]
        results = await asyncio.gather(
            *(_describe_one(node) for node in batch), return_exceptions=True
        )
        for result in results:
            if result is True:
                filled += 1
            elif isinstance(result, Exception):
                print(f"[vision] 설명 생성 중 예외 ({type(result).__name__}: {result})", flush=True)

    return filled
