"""TV Memory Journey Curator - 조건 기반 슬라이드쇼 큐레이션"""

from __future__ import annotations

import uuid
from typing import Optional

from backend.services import film_composer, llm_client
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

    # 4. Journey 구성
    journey = {
        "id": journey_id,
        "title": query,
        "slides": slides,
        "narration": narration,
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


def _motion_fields(media_id: str, clips: dict) -> dict:
    """이 사진에 미리 만들어 둔 클립이 있으면 슬라이드에 실어 준다

    Film과 같은 매니페스트를 읽는다 (film_composer.motion_clips). 만들어 둔 것을
    한 화면에서만 쓰면, 거실에서 보는 화면이 가장 좋은 재료를 못 쓰게 된다.

    항목이 없는 사진은 빈 값이 되고 화면은 지금까지처럼 카메라 움직임만 건다.
    """
    clip = clips.get(media_id)
    if not clip:
        return {}
    return {
        "motion_url": clip.get("file"),
        "motion_poster": clip.get("poster"),
        "subject_preserved": bool(clip.get("subject_preserved")),
    }


def _build_slides(conditions: dict, style: str) -> list[dict]:
    """조건에 맞는 슬라이드 목록 생성"""
    slides = []
    # 매니페스트는 파일 하나라 한 번만 읽는다 (film_composer가 캐시한다)
    clips = film_composer.motion_clips()

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


async def _generate_narration(query: str, slides: list[dict]) -> str:
    """EXAONE으로 내레이션 텍스트 생성"""
    if not slides or len(slides) <= 1:
        return ""

    slide_summary = []
    for s in slides[1:6]:  # 타이틀 제외, 최대 5개
        if s.get("caption"):
            slide_summary.append(s["caption"])

    if not llm_client.is_enabled():
        return _simulate_narration(query, slide_summary)

    messages = [
        {"role": "system", "content": "추억 사진 슬라이드쇼의 따뜻한 내레이션을 작성해. 2~3문장으로 짧게."},
        {"role": "user", "content": f"주제: {query}\n사진들: {', '.join(slide_summary)}"},
    ]

    narration = await llm_client.complete(messages, max_tokens=256)
    if narration is None:
        return _simulate_narration(query, slide_summary)
    return narration


def _simulate_narration(query: str, slide_summary: list[str]) -> str:
    """내레이션 시뮬레이션"""
    if slide_summary:
        return f"'{query}'에 대한 우리 가족의 소중한 기억들입니다. 함께한 순간들을 되돌아보며, 그때의 따뜻함을 다시 느껴보세요."
    return "우리 가족의 소중한 순간들을 모아봤어요."
