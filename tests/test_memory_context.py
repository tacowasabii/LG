"""기억 맥락 회귀 테스트 (기억 이어가기 → Memory Film · TV)

    python tests/test_memory_context.py

가족이 이미 만들어진 추억에 기억을 더하면, 그 문장에서 작은 맥락을 뽑아
자막·내레이션·장면 선택에 얹는다. 지켜야 하는 약속은 일곱이다.

    1. 답변에서 말한 사람·대상·장면·행동이 뽑힌다 (원문에 있는 것만)
    2. 원문(content)은 바뀌지 않는다
    3. 사건의 제목·날짜·장소는 바뀌지 않는다
    4. 맥락이 추억 상세로 내려간다
    5. Film의 자막·내레이션에 맥락이 반영된다
    6. TV 슬라이드의 자막에 맥락이 반영된다
    7. 근거 없는 사진을 자동으로 잇지 않고, 사진에 없는 행동을 사진의 내용으로
       적지 않는다

LLM 키가 없어도 통과해야 한다. 모델이 줄 값은 normalize()에 직접 넣어 시험하고,
사건에 맥락을 붙이는 경로는 extract를 갈아 끼워 확인한다 — 추출 규칙과 모델
호출을 갈라 둔 이유가 이것이다.

그래프를 실제로 바꾸므로 만든 것은 끝에서 지운다. 데모 데이터를 더럽히지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import (  # noqa: E402
    film_composer,
    llm_client,
    memories,
    memory_context,
    tv_curator,
)
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행 (사진 3장 + 영상 1개 + 음성 1개)
SPEAKER = "P02"  # 박서연 · 엄마
SUBJECT = "P03"  # 김하늘 · 딸
# 미세 모션 클립이 없는 사진. 클립이 있는 사진은 카메라 움직임을 걸지 않으므로
# (film_composer) 인물 중심 확대를 확인할 수 없다.
PHOTO = "E01_003"

ANSWER = "부산 바다에서 하늘이가 물장구치던 게 제일 재미있었어."

# 모델이 준다고 가정하는 값. 실제 호출을 대신한다.
MODEL_OUTPUT = {
    "subjects": ["하늘이"],
    "scene": "부산 바다",
    "action": "물장구치던",
    "highlight": "가장 재미있게 기억하는 순간",
    "confidence": "explicit",
}

_created: list[str] = []


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _cleanup():
    for node_id in _created:
        graph_manager.delete_node(node_id)
    _created.clear()


def _photo(faces: list[str], description: str = "", media_id: str = "X") -> dict:
    return {
        "id": media_id,
        "media_type": "photo",
        "scene_description": description,
        "detected_faces": faces,
    }


def _add_memory_with_context(media_ids=None) -> dict:
    """기억을 하나 더하고, 모델이 준 값으로 맥락을 붙인다

    extract를 갈아 끼운다. 여기서 확인하려는 것은 모델의 성능이 아니라, 뽑힌 값이
    원문을 건드리지 않고 기억 노드에 붙는지와 사진 근거가 어떻게 정해지는지다.
    """
    memory = memories.add_contribution(
        EVENT, SPEAKER, ANSWER, media_ids=media_ids or []
    )
    assert memory, "기억을 더하지 못했다"
    _created.append(memory["id"])

    original = memory_context.extract

    async def fake_extract(content, speaker_id):
        return memory_context.normalize(MODEL_OUTPUT, content, speaker_id)

    memory_context.extract = fake_extract
    try:
        asyncio.run(memories.extract_context(EVENT, memory["id"]))
    finally:
        memory_context.extract = original

    return graph_manager.get_node(memory["id"])


# --- 1. 뽑아내기 -------------------------------------------------------------


def test_answer_yields_speaker_subject_scene_action():
    """답변에서 말한 사람 · 대상 · 장면 · 행동이 나온다"""
    context = memory_context.normalize(MODEL_OUTPUT, ANSWER, SPEAKER)

    assert context, "맥락이 비었다"
    assert context["speaker_id"] == SPEAKER, context["speaker_id"]
    assert context["subject_person_ids"] == [SUBJECT], context["subject_person_ids"]
    assert context["scene"] == "부산 바다", context["scene"]
    assert context["action"] == "물장구치던", context["action"]
    assert context["confidence"] == "explicit", context["confidence"]
    # 그래프에 없는 사람을 만들지 않는다
    assert context["unmatched"] == [], context["unmatched"]
    print("  추출 OK:", context["scene"], "·", context["action"])


def test_details_that_are_not_in_the_answer_are_dropped():
    """원문에 없는 사람·장소·행동은 버린다 (지어낸 값이 자막에 오르지 않게)"""
    invented = memory_context.normalize(
        {
            "subjects": ["아빠"],
            "scene": "생일 케이크",
            "action": "촛불을 끄던",
            "confidence": "explicit",
        },
        ANSWER,
        SPEAKER,
    )
    assert invented is None, invented

    half = memory_context.normalize(
        {"subjects": ["하늘이"], "scene": "제주도 바다", "action": "물장구치던"},
        ANSWER,
        SPEAKER,
    )
    assert half, "맞는 값까지 버렸다"
    assert half["scene"] is None, half["scene"]
    assert half["action"] == "물장구치던", half["action"]
    # 근거를 밝히지 않은 값은 inferred로 떨어진다
    assert half["confidence"] == "inferred", half["confidence"]
    print("  지어낸 값 버림 OK")


def test_unknown_person_is_reported_not_created():
    """그래프에 없는 호칭은 만들지 않고 밝힌다"""
    before = len(graph_manager.get_persons())
    context = memory_context.normalize(
        {"subjects": ["큰엄마"], "scene": "부산 바다"},
        "큰엄마도 부산 바다에 같이 있었어.",
        SPEAKER,
    )
    assert context, "맥락이 비었다"
    assert context["subject_person_ids"] == [], context["subject_person_ids"]
    assert "큰엄마" in context["unmatched"], context["unmatched"]
    assert len(graph_manager.get_persons()) == before, "인물을 새로 만들었다"
    print("  없는 사람 안 만듦 OK")


# --- 2 · 3. 원본과 사건은 그대로 ---------------------------------------------


def test_original_text_and_event_are_untouched():
    """원문도 사건의 제목·날짜·장소도 바뀌지 않는다"""
    before = graph_manager.get_node(EVENT)
    snapshot = (
        before.get("title"),
        before.get("date_start"),
        before.get("location_id"),
        before.get("description"),
    )

    memory = _add_memory_with_context()

    assert memory["content"] == ANSWER, memory["content"]
    # 맥락은 따로 붙는다. 원문을 대신하지 않는다.
    assert memory["context"], "맥락이 붙지 않았다"
    assert memory["context"]["scene"] == "부산 바다"

    after = graph_manager.get_node(EVENT)
    assert (
        after.get("title"),
        after.get("date_start"),
        after.get("location_id"),
        after.get("description"),
    ) == snapshot, "사건이 바뀌었다"
    print("  원문·사건 불변 OK")


# --- 4. 상세 화면 ------------------------------------------------------------


def test_context_reaches_memory_detail():
    """추억 상세에 원문 · 맥락 · 반영 여부가 함께 내려온다"""
    memory = _add_memory_with_context()
    detail = memories.detail(EVENT, SPEAKER)
    assert detail, "상세를 만들지 못했다"

    entry = next((m for m in detail["contributions"] if m["id"] == memory["id"]), None)
    assert entry, "더한 기억이 상세에 없다"
    assert entry["content"] == ANSWER, entry["content"]

    context = entry["context"]
    assert context, "맥락이 내려오지 않았다"
    assert context["speaker"]["id"] == SPEAKER, context["speaker"]
    assert [p["id"] for p in context["subjects"]] == [SUBJECT], context["subjects"]
    assert context["caption"], "자막 문구가 비었다"
    assert context["used_in_film"] and context["used_in_tv"], context
    print("  상세 반영 OK:", context["caption"])


# --- 5. Film ----------------------------------------------------------------


def test_film_narration_carries_the_context():
    """Film 내레이션에 맥락이 반영된다 (LLM 폴백 경로로 검증)"""
    _add_memory_with_context()

    event = graph_manager.get_node(EVENT)
    nodes = graph_manager.get_connected_nodes(EVENT)
    items = [n for n in nodes if n.get("node_type") == "memory"]
    persons = [n for n in nodes if n.get("node_type") == "person"]
    contexts = memory_context.from_memories(items)
    assert contexts, "맥락을 모으지 못했다"

    plain = film_composer._plain_narration(
        event, items, persons, "부산 광안리 해수욕장", contexts
    )

    assert "부산 바다" in plain, plain
    assert "물장구치던" in plain, plain
    # 사진에서 확인되지 않은 행동은 기억의 출처만 밝힌다
    assert "기억합니다" in plain, plain
    print("  Film 내레이션 OK:", plain[-48:])


def test_film_puts_the_remembered_photo_first_with_its_caption():
    """맥락이 가리키는 사진이 앞에 서고, 자막과 출처가 그 기억을 밝힌다"""
    _add_memory_with_context(media_ids=[PHOTO])

    board = asyncio.run(film_composer.compose(EVENT))
    assert board, "스토리보드가 비었다"

    scene = board["scenes"][0]
    assert scene["media_id"] == PHOTO, [s["media_id"] for s in board["scenes"]]
    assert scene["context_caption"], scene
    assert scene["subtitle"] == scene["context_caption"], scene["subtitle"]
    assert "엄마" in scene["source_label"], scene["source_label"]
    # 인물 위치를 알므로 그 사람을 중심으로 확대한다 (원본 픽셀을 옮기는 것뿐이다)
    assert scene["focus"], scene
    assert scene["visual_treatment"] == "subject-focus", scene["visual_treatment"]
    assert scene["motion"] == "zoom-in", scene["motion"]
    # 라벨은 허용 목록 안에 있어야 한다 — 맥락이 새 문구를 만들지 않는다
    for effect in scene["ai_effects"]:
        assert effect in film_composer.ALLOWED_EFFECTS, effect

    # 맥락이 없는 사진도 영상에서 빠지지 않는다 (앞으로 옮기기만 한다)
    assert len(board["scenes"]) >= 3, len(board["scenes"])
    print("  Film 장면 OK:", scene["subtitle"], "·", scene["source_label"][-24:])


# --- 6. TV ------------------------------------------------------------------


def test_tv_slides_carry_a_short_caption_and_its_source():
    """TV는 긴 문장을 띄우지 않는다. 짧은 자막과 그 출처만 올린다"""
    _add_memory_with_context(media_ids=[PHOTO])

    journey = asyncio.run(tv_curator.create_journey("부산 여행", "timeline"))
    slides = [s for s in journey["slides"] if s.get("media_id") == PHOTO]
    assert slides, "그 사진이 여정에 없다"

    slide = slides[0]
    assert slide.get("context_caption"), slide
    assert ANSWER not in slide["context_caption"], slide["context_caption"]
    assert slide.get("context_source"), slide
    assert slide.get("context_contributor") == "박서연", slide.get("context_contributor")
    assert PHOTO in (slide.get("context_media_ids") or []), slide
    print("  TV 자막 OK:", slide["context_caption"], "·", slide["context_source"])


# --- 7. 잘못된 연결과 단정을 막는다 ------------------------------------------


def test_photos_are_linked_only_when_there_is_a_reason():
    """근거가 없으면 사진을 잇지 않는다 (맥락만 저장한다)"""
    context = memory_context.normalize(MODEL_OUTPUT, ANSWER, SPEAKER)

    # 사건의 사진 전부에 그 사람이 있으면 가리키는 것이 없는 것과 같다
    everywhere = [
        _photo(["P01", "P02", "P03"], "해변에서 웃고 있다", "A"),
        _photo(["P01", "P02", "P03"], "물가에 앉아 있다", "B"),
    ]
    ids, basis = memory_context.relate_media(context, [], everywhere)
    assert ids == [] and basis is None, (ids, basis)

    # 한 장에만 있으면 그 사진을 가리킨다 — 다만 행동이 확인된 것은 아니다
    only_one = [
        _photo(["P01", "P02", "P03"], "해변에서 웃고 있다", "A"),
        _photo(["P01", "P02"], "어른들만 앉아 있다", "B"),
    ]
    ids, basis = memory_context.relate_media(context, [], only_one)
    assert ids == ["A"], ids
    assert basis == memory_context.BASIS_PERSON, basis
    assert not memory_context.shows_action({**context, "media_basis": basis})

    # 사진 설명에 그 행동이 적혀 있으면 사진에서 확인된 것이다
    described = [
        _photo(["P03"], "아이가 물장구를 치며 놀고 있다", "A"),
        _photo(["P01"], "어른이 파라솔 아래 앉아 있다", "B"),
    ]
    ids, basis = memory_context.relate_media(context, [], described)
    assert ids == ["A"], ids
    assert basis == memory_context.BASIS_SCENE, basis
    assert memory_context.shows_action({**context, "media_basis": basis})

    # 가족이 이 기억과 함께 올린 기록이 있으면 그것이 근거다
    ids, basis = memory_context.relate_media(
        context, [_photo([], "", "C")], described
    )
    assert ids == ["C"], ids
    assert basis == memory_context.BASIS_ATTACHED, basis
    print("  사진 연결 근거 OK")


def test_an_action_absent_from_the_photo_is_not_stated_as_fact():
    """사진에 없는 행동을 사진의 내용처럼 적지 않는다"""
    context = memory_context.normalize(MODEL_OUTPUT, ANSWER, SPEAKER)

    # 사진 근거가 없을 때
    note = memory_context.source_note(context)
    assert "확인" not in note or "아닙니다" in note, note
    assert "기억" in note, note

    line = memory_context.narration_line(context)
    assert line.startswith("엄마는"), line
    assert line.endswith("기억합니다."), line

    # 프롬프트에 넘기는 줄도 "누가 무엇을 기억한다"까지다. 사진에서 확인됐는지는
    # 넘기지 않는다 — 사진에 무엇이 있는지는 사진 설명이 따로 들어가 있다.
    prompt = memory_context.prompt_line(context)
    assert "기억한다" in prompt, prompt
    assert "확인" not in prompt, prompt

    # 확인 여부는 화면 문구에서만 갈린다 (사람이 읽는 자리)
    confirmed = {**context, "media_basis": memory_context.BASIS_SCENE}
    assert "사진 설명에서 확인됨" in memory_context.source_note(confirmed)
    # 확인된 경우에도 주어는 기억한 사람이다
    assert memory_context.narration_line(confirmed).startswith("엄마는")
    print("  단정하지 않음 OK")


def test_prompt_lines_carry_no_display_marks():
    """프롬프트 줄에 화면으로 새어 나갈 표시를 붙이지 않는다

    처음에는 줄 끝에 "[사진에서 확인되지 않음]"을 적었다. 모델이 그것을 그대로
    옮겨 적어서 "함께 기억한 이야기" 본문에 그 말이 나왔다 — 프롬프트에만 쓰려던
    표시가 화면에 나가면 근거가 아니라 기계 부품이 보이는 것이다.
    """
    context = memory_context.normalize(MODEL_OUTPUT, ANSWER, SPEAKER)
    line = memory_context.prompt_line(context)

    assert line, "프롬프트 줄이 비었다"
    assert "[" not in line and "]" not in line, line
    assert "확인" not in line, line
    # 그대로 베껴도 안전한 문장이어야 한다 (주어가 기억한 사람이다)
    assert "기억한다" in line, line
    assert "부산 바다" in line and "물장구치던" in line, line

    # 사진에서 확인된 맥락도 같은 모양이다 — 확인 여부는 프롬프트로 넘기지 않는다
    confirmed = {**context, "media_basis": memory_context.BASIS_SCENE}
    assert "확인" not in memory_context.prompt_line(confirmed)
    print("  프롬프트 줄 OK:", line)


def test_prompt_marks_are_stripped_from_generated_text():
    """모델이 표시를 베껴 오면 나가는 자리에서 떼어낸다"""
    leaked = (
        "엄마는 부산 바다에서 김하늘이 물장구치던 순간을 기억합니다. "
        "[사진에서 확인되지 않음] 아빠는 그날 파도가 높았다고 기억합니다.\n"
        "[기억 맥락] 가족은 그 여행을 오래 이야기했습니다 (사진에서 확인되지 않음).\n"
        "[다르게 기억함] 누구도 정답으로 정하지 않았습니다."
    )
    cleaned = memory_context.strip_prompt_marks(leaked)

    for mark in ("[", "]", "사진에서 확인되지 않음", "기억 맥락", "다르게 기억함"):
        assert mark not in cleaned, cleaned
    # 문장은 그대로 남는다 (걷어내는 것까지가 이 함수의 몫이다)
    assert "물장구치던 순간을 기억합니다." in cleaned, cleaned
    assert "파도가 높았다고 기억합니다." in cleaned, cleaned
    assert "  " not in cleaned, cleaned
    # 표시가 없는 글은 손대지 않는다
    plain = "엄마는 부산 바다를 기억합니다."
    assert memory_context.strip_prompt_marks(plain) == plain
    print("  표시 제거 OK")


def test_story_drops_marks_the_model_copied():
    """함께 기억한 이야기에 프롬프트 표시가 남지 않는다 (저장되는 값까지)"""
    _add_memory_with_context()

    kept = {
        key: graph_manager.get_node(EVENT).get(key)
        for key in ("together_story", "together_story_at", "together_story_basis")
    }
    enabled, complete = llm_client.is_enabled, llm_client.complete

    async def fake_complete(*args, **kwargs):
        return (
            "가족은 그 여행을 이렇게 기억합니다. [사진에서 확인되지 않음] "
            "엄마는 하늘이가 물장구치던 순간을 가장 좋아했습니다."
        )

    llm_client.is_enabled = lambda *a, **k: True
    llm_client.complete = fake_complete
    try:
        result = asyncio.run(memories.compose_together_story(EVENT, SPEAKER))
    finally:
        llm_client.is_enabled, llm_client.complete = enabled, complete

    assert result, "이야기를 만들지 못했다"
    try:
        assert "[사진에서 확인되지 않음]" not in result["story"], result["story"]
        stored = graph_manager.get_node(EVENT).get("together_story") or ""
        assert "[" not in stored, stored
        assert "물장구치던 순간을 가장 좋아했습니다." in stored, stored
        print("  이야기 표시 제거 OK")
    finally:
        graph_manager.update_node(EVENT, kept)


def test_scene_only_context_reads_as_a_sentence():
    """장소만 남은 맥락도 조사가 어긋나지 않는다"""
    context = memory_context.normalize(
        {"subjects": [], "scene": "부산 바다", "action": None}, ANSWER, SPEAKER
    )
    assert context and context["scene"] == "부산 바다", context
    line = memory_context.narration_line(context)
    assert line == "엄마는 부산 바다를 기억합니다.", line
    print("  장소만 있는 맥락 OK:", line)


def test_context_disappears_with_the_memory():
    """기억을 지우면 맥락도 함께 사라진다 (노드 하나에 들어 있다)"""
    memory = _add_memory_with_context()
    result = memories.delete_memory(EVENT, memory["id"])

    assert result, "지우지 못했다"
    assert graph_manager.get_node(memory["id"]) is None, "기억이 남아 있다"
    contexts = memory_context.contexts_of(EVENT)
    assert all(c.get("memory_id") != memory["id"] for c in contexts), contexts
    print("  기억과 함께 사라짐 OK")


def test_story_names_everyone_who_was_there():
    """이야기가 부르지 않은 참여자는 한 줄로 채워진다

    프롬프트에 "참여자를 한 명도 빼지 마라"를 적어도 모델은 기억 문장에 나온
    사람만 부른다. 사진에서 직접 지목한 할머니가 이야기에 없으면, 지목한 사람
    눈에는 지목이 저장되지 않은 것으로 보인다.
    """
    persons = [graph_manager.get_node(pid) for pid in (SPEAKER, SUBJECT, "P05")]
    story = "김민수는 캠코더로 하늘이를 찍었습니다."

    filled = memory_context.ensure_persons_named(story, persons)

    assert filled.startswith(story), filled
    # "하늘이"로 불린 김하늘은 다시 적지 않는다 (성을 뗀 이름까지 맞춰 본다)
    assert filled.count("하늘") == 1, filled
    assert "할머니" in filled, filled
    assert "엄마" in filled, filled
    print("  빠진 참여자 채우기 OK:", filled)


def test_story_is_left_alone_when_everyone_is_named():
    """모두 불린 이야기에는 아무것도 덧붙이지 않는다"""
    persons = [graph_manager.get_node(pid) for pid in (SPEAKER, SUBJECT)]
    story = "엄마 박서연은 하늘이가 물장구치던 순간을 기억합니다."

    assert memory_context.ensure_persons_named(story, persons) == story
    print("  덧붙이지 않음 OK")


def test_person_mentions_become_name_with_relation():
    """모델이 쓴 "아빠 김민수"는 "김민수(아빠)"로 맞춰진다

    이야기에 사람이 이름만으로 나오면 가족이 서로를 부르는 말이 사라지고,
    호칭만으로 나오면 누구인지 이름이 남지 않는다. 표기를 한 모양으로 모은다.
    """
    persons = [graph_manager.get_node(pid) for pid in (SPEAKER, SUBJECT)]

    fixed = memory_context.label_person_mentions(
        "엄마 박서연은 딸 김하늘이가 노는 모습을 지켜봤다.", persons
    )
    assert "박서연(엄마)" in fixed, fixed
    assert "김하늘(딸)" in fixed, fixed
    # 조사가 두 번 붙지 않는다 ("김하늘(딸)이가"가 아니다)
    assert ")이가" not in fixed, fixed
    # 괄호로 끝난 이름 뒤의 조사도 맞춰진다 ("(엄마)은"이 아니라 "(엄마)는")
    assert "박서연(엄마)는" in fixed, fixed

    # 조사가 아닌 "이"는 건드리지 않는다
    copula = "엄마 박서연이라는 사람이 있었다."
    assert memory_context.label_person_mentions(copula, persons) == (
        "박서연(엄마)이라는 사람이 있었다."
    )

    # 이름이 앞에 오는 말은 건드리지 않는다 — "김하늘 딸"은 "김하늘의 딸"일 수 있다
    kept = "김하늘 딸에 대한 이야기다."
    assert memory_context.label_person_mentions(kept, persons) == kept
    print("  인물 표기 맞추기 OK:", fixed)


TESTS = [
    test_answer_yields_speaker_subject_scene_action,
    test_details_that_are_not_in_the_answer_are_dropped,
    test_unknown_person_is_reported_not_created,
    test_original_text_and_event_are_untouched,
    test_context_reaches_memory_detail,
    test_film_narration_carries_the_context,
    test_film_puts_the_remembered_photo_first_with_its_caption,
    test_tv_slides_carry_a_short_caption_and_its_source,
    test_photos_are_linked_only_when_there_is_a_reason,
    test_an_action_absent_from_the_photo_is_not_stated_as_fact,
    test_prompt_lines_carry_no_display_marks,
    test_prompt_marks_are_stripped_from_generated_text,
    test_story_drops_marks_the_model_copied,
    test_scene_only_context_reads_as_a_sentence,
    test_context_disappears_with_the_memory,
    test_story_names_everyone_who_was_there,
    test_story_is_left_alone_when_everyone_is_named,
    test_person_mentions_become_name_with_relation,
]


def main():
    _require_seeded_graph()
    print("기억 맥락 회귀 테스트")
    failed = 0
    for test in TESTS:
        try:
            test()
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {test.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {test.__name__}: {type(e).__name__}: {e}")
        finally:
            # 테스트마다 만든 기억을 바로 거둔다. 남기면 다음 테스트가 남의
            # 맥락까지 세고, 어느 것이 이번 것인지 알 수 없다.
            _cleanup()
    if failed:
        print(f"\n{failed}개 실패")
        sys.exit(1)
    print(f"\n{len(TESTS)}개 통과")


if __name__ == "__main__":
    main()
