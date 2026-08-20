"""TV Memory Journey Curator - 조건 기반 슬라이드쇼 큐레이션"""

from __future__ import annotations

import uuid
from typing import Optional

from backend.services import (
    film_composer,
    film_music,
    llm_client,
    memory_context,
    motion_clips,
)
from backend.models.graph_models import NodeType
from backend.services.graph_manager import graph_manager


# 생성된 Journey 캐시 (MVP: in-memory)
_journeys: dict[str, dict] = {}


async def create_journey(query: str, style: str = "timeline") -> dict:
    """TV Journey 생성

    query: "우리 가족의 2015년", "부산 여행", "아빠와의 추억" 등
    style: "timeline" | "story" | "people"
    """
    journey_id = str(uuid.uuid4())

    # 1. 쿼리에서 조건 추출
    conditions = _parse_query(query)

    # 2. 조건에 맞는 미디어/이벤트 검색
    slides = _build_slides(conditions, style)

    # 3. 내레이션 생성
    narration = await _generate_narration(query, slides)

    # 4. 배경 음악의 무드. 소리는 화면이 만든다 (frontend/src/lib/filmMusic.ts).
    #
    # 여정 전체에 하나만 정한다 — 슬라이드마다 바꾸면 9초마다 곡이 갈린다.
    # Film과 같은 함수를 쓴다: 낱말 표가 갈라지면 같은 사건이 거실에서 다르게
    # 들리고, 무엇을 왜 깔았는지 적어 둔 문구가 두 화면에서 어긋난다.
    events, places = _slide_events(slides)
    music = film_music.pick_journey(events, places)

    # 5. Journey 구성
    journey = {
        "id": journey_id,
        "title": query,
        "slides": slides,
        "narration": narration,
        # 없을 수 있다 (사건에 연결되지 않은 사진만 모인 여정). 그때 화면은 음악
        # 없이 재생한다 — 근거가 없는데 아무 소리나 얹지 않는다.
        "music": music,
        "total_duration_sec": len(slides) * 5,  # 슬라이드당 5초
    }

    _journeys[journey_id] = journey
    return journey


def get_journey(journey_id: str) -> Optional[dict]:
    """저장된 Journey 조회"""
    return _journeys.get(journey_id)


def _parse_query(query: str) -> dict:
    """쿼리에서 검색 조건 추출 (간단한 규칙 기반)"""
    conditions = {
        "year": None,
        "person": None,
        "place": None,
        "keywords": [],
    }

    # 연도 추출
    import re
    year_match = re.search(r"(19|20)\d{2}", query)
    if year_match:
        conditions["year"] = year_match.group()

    # 인물 매칭
    persons = graph_manager.get_persons()
    for person in persons:
        name = person.get("name", "")
        if name and name in query:
            conditions["person"] = person["id"]
            break
        relation = person.get("relation", "")
        if relation and relation in query:
            conditions["person"] = person["id"]
            break

    # 장소 매칭
    places = graph_manager.get_places()
    for place in places:
        name = place.get("name", "")
        if name and name in query:
            conditions["place"] = place["id"]
            break

    # 키워드
    conditions["keywords"] = [w for w in query.split() if len(w) >= 2]

    return conditions


def _slide_events(slides: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """슬라이드가 가리키는 사건과 그 장소 이름 (중복 없이, 나온 순서대로)

    배경 음악의 무드를 사건에서 고르므로 여정에 실제로 담긴 사건만 본다. 슬라이드가
    스무 장이어도 사건은 몇 개뿐이고, 같은 사건을 여러 번 세면 사진이 많은 사건이
    무드를 혼자 정하게 된다 — 사진 수가 아니라 사건 수로 센다.
    """
    events: list[dict] = []
    places: dict[str, str] = {}
    seen: set[str] = set()

    for slide in slides:
        event_id = slide.get("event_id")
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)
        event = graph_manager.get_node(event_id)
        if not event:
            continue
        events.append(event)
        place = graph_manager.get_node(event.get("location_id") or "")
        if place and place.get("name"):
            places[event_id] = place["name"]

    return events, places


def _motion_fields(media_id: str, clips: dict) -> dict:
    """이 사진에 만들어 둔 클립이 있으면 슬라이드에 실어 준다

    Film과 같은 목록을 읽는다 (motion_clips.manifest). 만들어 둔 것을 한 화면에서만
    쓰면, 거실에서 보는 화면이 가장 좋은 재료를 못 쓰게 된다. 미리 만들어 커밋한
    것과 Film에서 그때 만든 것이 모두 여기 들어온다.

    TV는 만들지 않는다. 거실 화면은 리모컨으로 넘기는 자리라 40초를 기다릴 수
    없고, 넘기는 것만으로 돈이 나가면 안 된다. Film이 만든 것을 쓰기만 한다.

    항목이 없는 사진은 빈 값이 되고 화면은 지금까지처럼 카메라 움직임만 건다.
    """
    clip = clips.get(media_id)
    if not clip:
        return {}
    return {
        "motion_url": clip.get("file"),
        "motion_poster": clip.get("poster"),
        "subject_preserved": bool(clip.get("subject_preserved")),
        # 라벨도 서버가 준다. Film과 같은 함수를 써서 두 화면의 문구가 갈라지지 않게.
        "motion_label": film_composer.generated_label(clip),
    }


def _context_fields(event: Optional[dict], media_id: str, cache: dict) -> dict:
    """이 슬라이드에 얹을 기억 맥락 (Film과 같은 문구를 쓴다)

    거실 화면에는 가족이 남긴 긴 문장을 그대로 띄우지 않는다. 3m 거리에서 읽을 수
    있는 것은 한 줄이고, 그 한 줄이 "엄마가 기억하는 부산 바다"다. 원문은 앱에서
    읽는다.

    사건마다 한 번만 읽는다 (cache). 슬라이드 스무 장이 같은 사건을 가리키는
    경우가 흔해서, 슬라이드마다 기억을 다시 읽으면 목록 하나에 그래프를 수십 번
    훑는다.

    이 사진을 가리키는 맥락이 없으면 사건의 대표 맥락을 올리되, 출처 문구에서
    "이 사진의 장면은 아닙니다"라고 밝힌다 — 자막이 사진 설명으로 읽히면
    사진에 없는 장면을 사실처럼 말하는 것이 된다.
    """
    if not event:
        return {}

    event_id = event.get("id")
    if event_id not in cache:
        cache[event_id] = memory_context.contexts_of(event_id)
    contexts = cache[event_id]
    if not contexts:
        return {}

    matched = memory_context.for_media(contexts, media_id)
    context = matched or memory_context.primary(contexts)
    if not context:
        return {}

    return {
        "context_caption": memory_context.caption(context),
        "context_contributor": memory_context.speaker_name(context),
        "context_source": (
            memory_context.source_note(context)
            if matched
            else memory_context.event_note(context)
        ),
        "context_media_ids": list(context.get("media_ids") or []) if matched else [],
    }


def _build_slides(conditions: dict, style: str) -> list[dict]:
    """조건에 맞는 슬라이드 목록 생성"""
    slides = []
    # 목록은 파일 두 개(커밋된 것 + 런타임)라 슬라이드마다 읽지 않고 한 번만 읽는다
    clips = motion_clips.manifest()
    # 사건별 기억 맥락. 슬라이드를 만드는 동안 한 번씩만 읽는다.
    contexts_by_event: dict = {}

    # 타이틀 슬라이드
    slides.append({
        "type": "title",
        "media_id": None,
        "file_path": None,
        "caption": "",
        "event_id": None,
        "event_title": None,
        "date": None,
    })

    # 미디어 검색
    all_media = graph_manager.get_media_nodes()
    all_events = graph_manager.get_events()
    matched_media = []

    # 조건이 얼마나 구체적인지에 따라 최소 점수 결정
    has_year = bool(conditions.get("year"))
    has_person = bool(conditions.get("person"))
    has_place = bool(conditions.get("place"))
    specificity = sum([has_year, has_person, has_place])
    min_score = max(2, specificity + 1)  # 조건이 많을수록 엄격하게

    for media in all_media:
        score = _score_media(media, conditions)
        if score >= min_score:
            matched_media.append((score, media))

    # 엄격한 기준으로 매칭 안 되면 점수 1 이상으로 완화
    if not matched_media:
        for media in all_media:
            score = _score_media(media, conditions)
            if score > 0:
                matched_media.append((score, media))

    # 점수순 정렬
    matched_media.sort(key=lambda x: x[0], reverse=True)

    # 스타일에 따라 정렬 변경
    if style == "timeline":
        # 시간순 정렬
        matched_media.sort(
            key=lambda x: x[1].get("exif_date") or x[1].get("created_at") or "",
        )

    # 슬라이드 생성
    for _, media in matched_media[:20]:  # 최대 20장
        # 연결된 이벤트 찾기
        connected = graph_manager.get_connected_nodes(media["id"])
        event = next(
            (n for n in connected if n.get("node_type") == NodeType.EVENT),
            None,
        )

        caption = _generate_caption(media, event)

        slides.append({
            "type": media.get("media_type", "photo"),
            "media_id": media["id"],
            "file_path": media.get("file_path", ""),
            "caption": caption,
            "event_id": event.get("id") if event else None,
            "event_title": event.get("title") if event else None,
            "date": media.get("exif_date", media.get("created_at", "")),
            **_motion_fields(media["id"], clips),
            **_context_fields(event, media["id"], contexts_by_event),
        })

    # 매칭된 미디어가 없으면 전체에서 최신 순으로
    if len(slides) <= 1:
        for media in sorted(
            all_media,
            key=lambda m: m.get("exif_date") or m.get("created_at") or "",
            reverse=True,
        )[:10]:
            connected = graph_manager.get_connected_nodes(media["id"])
            event = next(
                (n for n in connected if n.get("node_type") == NodeType.EVENT),
                None,
            )
            slides.append({
                "type": media.get("media_type", "photo"),
                "media_id": media["id"],
                "file_path": media.get("file_path", ""),
                "caption": _generate_caption(media, event),
                "event_id": event.get("id") if event else None,
                "event_title": event.get("title") if event else None,
                "date": media.get("exif_date", media.get("created_at", "")),
                **_motion_fields(media["id"], clips),
                **_context_fields(event, media["id"], contexts_by_event),
            })

    return slides


def _score_media(media: dict, conditions: dict) -> int:
    """미디어가 조건에 맞는 정도 점수"""
    score = 0
    media_date = media.get("exif_date") or media.get("created_at") or ""

    # 연도 매칭
    if conditions.get("year") and media_date and conditions["year"] in media_date:
        score += 3

    # 인물 매칭 (미디어에 연결된 인물)
    if conditions.get("person"):
        connected = graph_manager.get_connected_nodes(media["id"])
        person_ids = [n["id"] for n in connected if n.get("node_type") == NodeType.PERSON]
        if conditions["person"] in person_ids:
            score += 3

    # 장소 매칭
    if conditions.get("place"):
        connected = graph_manager.get_connected_nodes(media["id"])
        place_ids = [n["id"] for n in connected if n.get("node_type") == NodeType.PLACE]
        if conditions["place"] in place_ids:
            score += 2

    # 키워드 매칭 (이벤트 제목/설명에서)
    if conditions.get("keywords"):
        connected = graph_manager.get_connected_nodes(media["id"])
        events = [n for n in connected if n.get("node_type") == NodeType.EVENT]
        for event in events:
            text = f"{event.get('title', '')} {event.get('description', '')}".lower()
            for kw in conditions["keywords"]:
                if kw.lower() in text:
                    score += 1

    return score


def _generate_caption(media: dict, event: Optional[dict]) -> str:
    """슬라이드 캡션 생성"""
    parts = []

    # 날짜
    date = media.get("exif_date", "")
    if date:
        parts.append(date[:10])

    # 이벤트 제목
    if event:
        parts.append(event.get("title", ""))

    return " - ".join(parts) if parts else media.get("original_filename", "")


def _journey_contexts(slides: list[dict], limit: int = 3) -> list[dict]:
    """이 여정에 담긴 사건들의 기억 맥락 (중복 없이, 나온 순서대로)

    내레이션이 쓸 재료다. 슬라이드에 실은 자막(context_caption)만으로는 무엇을
    기억한다는 것인지 모델에게 전해지지 않는다 — 자막은 한 줄로 줄인 것이고,
    여기서는 장면·대상·행동과 "사진에서 확인됐는지"까지 넘긴다.
    """
    picked: list[dict] = []
    seen: set[str] = set()
    events: set[str] = set()

    for slide in slides:
        event_id = slide.get("event_id")
        if not event_id or event_id in events:
            continue
        events.add(event_id)
        for context in memory_context.contexts_of(event_id):
            key = context.get("memory_id") or ""
            if key in seen:
                continue
            seen.add(key)
            picked.append(context)
            if len(picked) >= limit:
                return picked
    return picked


async def _generate_narration(query: str, slides: list[dict]) -> str:
    """EXAONE으로 내레이션 텍스트 생성"""
    if not slides or len(slides) <= 1:
        return ""

    slide_summary = []
    for s in slides[1:6]:  # 타이틀 제외, 최대 5개
        if s.get("caption"):
            slide_summary.append(s["caption"])

    # 가족이 더한 기억에서 뽑은 맥락. Film과 같은 값을 쓴다 (memory_context) —
    # 거실에서 듣는 이야기와 앱에서 보는 이야기가 갈라지지 않게.
    contexts = _journey_contexts(slides)

    if not llm_client.is_enabled():
        return _simulate_narration(query, slide_summary, contexts)

    context_lines = "\n".join(memory_context.prompt_line(c) for c in contexts)
    messages = [
        {
            "role": "system",
            "content": (
                "추억 사진 슬라이드쇼의 따뜻한 내레이션을 작성해. 2~3문장으로 짧게.\n"
                "[기억 맥락]은 가족이 기억하는 관점이다. [사진에서 확인되지 않음]이"
                " 붙은 것은 사진에 그 장면이 있다고 쓰지 말고, '하늘이가 물장구치던"
                " 순간을 엄마는 가장 좋아했어요'처럼 기억의 주인을 밝혀서 써.\n"
                "주어진 것에 없는 사실을 만들지 마."
            ),
        },
        {
            "role": "user",
            "content": f"주제: {query}\n사진들: {', '.join(slide_summary)}"
            + (f"\n\n[기억 맥락]\n{context_lines}" if context_lines else ""),
        },
    ]

    narration = await llm_client.complete(messages, max_tokens=256)
    if narration is None:
        return _simulate_narration(query, slide_summary, contexts)
    return narration


def _simulate_narration(
    query: str,
    slide_summary: list[str],
    contexts: Optional[list[dict]] = None,
) -> str:
    """내레이션 시뮬레이션

    맥락이 있으면 그 한 줄을 붙인다. 모델이 없어도 가족이 남긴 관점이 거실
    화면에서 사라지지 않아야 하고, 문장의 주어는 기억한 사람이다
    (memory_context.narration_line).
    """
    lines = [
        memory_context.narration_line(context) for context in (contexts or [])[:2]
    ]
    tail = " ".join(line for line in lines if line)

    if slide_summary:
        head = (
            f"'{query}'에 대한 우리 가족의 소중한 기억들입니다."
            " 함께한 순간들을 되돌아보며, 그때의 따뜻함을 다시 느껴보세요."
        )
    else:
        head = "우리 가족의 소중한 순간들을 모아봤어요."

    return f"{head} {tail}".strip() if tail else head
