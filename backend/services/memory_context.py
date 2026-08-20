"""기억에서 뽑아낸 작은 맥락 (기억 이어가기 → Memory Film · TV)

가족이 이미 만들어진 추억에 기억을 더하면, 그 문장은 상세 화면에서 댓글 한 줄로
쌓이고 끝났다. "부산 바다에서 하늘이가 물장구치던 게 제일 재미있었어"를 남겨도
Memory Film의 자막은 그대로 "1998년 8월 · 해운대"였고, 내레이션은 그 문장을
통째로 읽었다. 가족이 준 것은 장면인데 화면은 텍스트로만 받았다.

여기서 하는 일은 그 문장에서 다섯 가지를 꺼내는 것뿐이다.

    누가 말했나(speaker) · 누구에 대한 말인가(subjects) · 어디(scene) ·
    무엇을 하던 순간(action) · 이 사람이 무엇을 가장 강하게 기억하나(highlight)

무엇을 하지 않는지가 이 파일의 절반이다.

  - 원문을 고치지 않는다. 맥락은 MemoryNode.context에 따로 붙는 파생값이다
  - 사건의 제목·날짜·장소·정체성을 건드리지 않는다. interview_engine.link_extracted
    와 다른 점이다 — 그쪽은 비어 있는 칸을 채우지만 여기는 이미 게시된 추억에
    얹는다. 이미 있는 사실을 뒤에 온 기억이 바꾸면, 만든 사람이 저장한 추억이
    자기도 모르게 달라진다
  - 사진을 새로 잇지 않는다. CAPTURED_DURING·EVIDENCED_BY 엣지를 만들지 않는다.
    어느 사진을 추억에 붙일지는 사람이 고르는 자리가 따로 있다
    (POST /api/memories/{id}/media)
  - 그래프에 없는 사람을 만들지 않는다. 맞춰지지 않은 호칭은 unmatched로 남겨
    화면이 "아직 가족 공간에 없어 잇지 않았습니다"라고 밝힌다
  - 원문에 없는 장면·행동을 만들지 않는다 (_grounded)
  - 사진에서 확인되지 않은 행동을 사진의 내용으로 적지 않는다 (shows_action)

별도 ContextNode나 사건 버전 관리를 두지 않았다. 맥락은 기억에 딸린 값이라
기억을 지우면 함께 사라져야 한다 — 노드로 떼어 놓으면 거둔 말의 맥락이 그래프에
남고, Film 자막에서 계속 읽힌다 (memories.delete_memory가 지우는 것은 노드
하나다).
"""

from __future__ import annotations

from typing import Optional

from backend.config import EXAONE_PLANNER_MODEL
from backend.models.graph_models import MediaType, NodeType
from backend.services import llm_client, visibility
from backend.services.graph_manager import graph_manager

# 원문에 그대로 적혀 있었는가. 미루어 짚은 것은 inferred다 — 화면이 구분해 적는다.
CONFIDENCE_EXPLICIT = "explicit"
CONFIDENCE_INFERRED = "inferred"

# 맥락이 어느 사진을 가리키는지, 그 근거가 무엇인가.
#   attached : 가족이 이 기억과 함께 올린 기록 (가장 강하다 — 사람이 골랐다)
#   scene    : 사진 설명에 이 장면·행동이 실제로 적혀 있다 (사진에서 확인된다)
#   person   : 이 사진에 대상 인물이 태그되어 있다 (그 사람이 나온 사진일 뿐,
#              행동이 확인된 것은 아니다)
BASIS_ATTACHED = "attached"
BASIS_SCENE = "scene"
BASIS_PERSON = "person"

# 자막 한 줄에 들어갈 수 있는 길이. 넘으면 버린다 — 모델이 문장 하나를 통째로
# scene에 넣어 오는 경우가 있고, 그것은 장면 이름이 아니라 요약이다.
MAX_PHRASE = 24

# 값이 없다는 뜻으로 모델이 보내는 말들. 그대로 저장하면 자막에 "모름"이 뜬다.
_EMPTY_WORDS = frozenset({"null", "none", "없음", "모름", "미상", "unknown", "n/a", "-"})

EXTRACT_SYSTEM = (
    "가족이 남긴 기억 문장 하나에서 장면 정보만 뽑는다. JSON 객체만 출력한다.\n"
    "\n"
    '{"subjects": ["문장에 나온 사람의 호칭이나 이름"],\n'
    ' "scene": "장소나 배경", "action": "무엇을 하던 순간인가",\n'
    ' "highlight": "이 사람이 무엇을 가장 강하게 기억하는가",\n'
    ' "confidence": "explicit" 또는 "inferred"}\n'
    "\n"
    "규칙:\n"
    "1. 문장에 없는 사람·장소·행동을 만들지 마라. 모르면 null, 없으면 빈 배열.\n"
    "2. subjects는 문장에 적힌 말을 그대로 쓴다 (\"하늘이\", \"엄마\", \"할머니\").\n"
    "3. action은 \"물장구치던\", \"케이크를 자르던\"처럼 순간을 가리키는 꾸밈말로 쓴다.\n"
    "4. 문장에 그대로 적혀 있으면 confidence는 explicit, 미루어 짚었으면 inferred.\n"
    "5. 각 값은 20자 이내. 설명 없이 JSON만 출력한다."
)


# --- 원문에서 나온 말인가 -----------------------------------------------------


def _word_grounded(word: str, source: str) -> bool:
    """낱말 하나가 원문에서 나왔는가 (두 글자가 이어서 나오면 나온 것으로 본다)

    한국어는 어미가 바뀐다 — 원문이 "물장구치던"인데 모델은 "물장구를 침"을 준다.
    문자열이 그대로 같기를 요구하면 맞는 값도 버리게 되므로 두 글자 조각으로 본다.
    """
    if word in source:
        return True
    if len(word) < 2:
        return False
    return any(word[i : i + 2] in source for i in range(len(word) - 1))


def _grounded(value: Optional[str], source: str) -> bool:
    """이 표현이 원문에서 나온 말인가

    낱말마다 따로 본다. 한 조각만 걸려도 통과시키면 "제주도 바다"가 "부산 바다"에
    붙어 있는 원문에서 살아남는다 — 반은 원문이고 반은 지어낸 말이 자막에 오른다.
    그래서 두 글자 이상인 낱말은 모두 원문에 근거가 있어야 한다.

    한 글자짜리는 세지 않는다. 조사와 짧은 꼬리("침", "것")라서 지어낼 여지가
    없고, 이것까지 요구하면 "물장구를 침"처럼 맞는 값이 버려진다.
    """
    text = " ".join((value or "").split())
    if not text or not source:
        return False
    if text in source:
        return True

    words = [word for word in text.split() if len(word) >= 2]
    if not words:
        return text.replace(" ", "") in source
    return all(_word_grounded(word, source) for word in words)


def _phrase(value, source: str) -> Optional[str]:
    """장면·행동 한 조각 (원문에 근거가 없으면 버린다)"""
    text = " ".join(str(value or "").split())
    if not text or text.lower() in _EMPTY_WORDS:
        return None
    if len(text) > MAX_PHRASE:
        return None
    return text if _grounded(text, source) else None


def _short(value) -> Optional[str]:
    """이 사람이 무엇을 가장 강하게 기억하는가 (해석이라 근거 검사를 하지 않는다)

    scene·action과 달리 highlight는 원문에 그대로 적혀 있는 말이 아니다
    ("제일 재미있었어" → "가장 재미있게 기억하는 순간"). 대신 화면과 내레이션에서
    언제나 말한 사람에게 귀속시켜 적는다 — 사진의 내용으로는 쓰지 않는다.
    """
    text = " ".join(str(value or "").split())
    if not text or text.lower() in _EMPTY_WORDS:
        return None
    return text[:40]


def _terms(value) -> list[str]:
    """모델이 준 값을 문자열 목록으로 (형식 이탈 방어)"""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    terms: list[str] = []
    for item in value:
        text = " ".join(str(item or "").split())
        if text and text.lower() not in _EMPTY_WORDS and text not in terms:
            terms.append(text)
    return terms


# 이름 뒤에 붙어 오는 조사·호칭. 사람이 말할 때 이름만 뚝 떼어 쓰지 않는다 —
# "하늘이가", "하늘이", "하늘도". 떼지 않으면 "김하늘"과 맞춰지지 않아, 가족
# 공간에 있는 사람인데 "아직 없는 사람"으로 밀려난다.
_NAME_TAIL = "이가은는을를도와과랑아야씨님"


def _variants(term: str):
    """맞춰 볼 모양들 (긴 것부터 한 글자씩 조사를 떼며)

    두 글자까지만 떼어 본다. "영이"에서 "영"까지 가면 "김영수"에 걸려 엉뚱한
    사람이 된다 — 짧아질수록 남의 이름에 얹히기 쉽다.
    """
    current = term
    seen: list[str] = []
    while True:
        if current not in seen:
            seen.append(current)
            yield current
        if len(current) > 2 and current[-1] in _NAME_TAIL:
            current = current[:-1]
        else:
            return


def resolve_person(term: str) -> Optional[str]:
    """호칭이나 이름을 그래프에 있는 인물에 맞춘다 (없으면 None)

    새 인물을 만들지 않는다. "큰엄마"가 누구인지는 가족만 알고, AI가 정하면
    잘못된 귀속이 그래프에 박힌다 (기획안 08장 Identity Safety).
    """
    term = (term or "").strip()
    if not term:
        return None

    persons = graph_manager.get_persons()
    for candidate in _variants(term):
        for person in persons:
            if candidate == person.get("name") or candidate == person.get("relation"):
                return person["id"]
        for person in persons:
            name = person.get("name") or ""
            if name and (candidate in name or name in candidate):
                return person["id"]
    return None


def _subject_particle(name: str) -> str:
    """이름 뒤에 붙는 주격 조사 (받침이 있으면 "이", 없으면 "가")

    "김하늘가 물장구치던"으로 읽히지 않게 한다. 문장을 만드는 곳이 세 군데라
    (자막·내레이션·프롬프트) 한 자리에서 정한다.
    """
    if not name:
        return "가"
    last = name[-1]
    if "가" <= last <= "힣":
        return "이" if (ord(last) - 0xAC00) % 28 else "가"
    return "가"


# --- 뽑아내기 ----------------------------------------------------------------


def is_usable(context: Optional[dict]) -> bool:
    """이 맥락으로 자막이나 내레이션을 만들 수 있는가"""
    if not context:
        return False
    return bool(
        context.get("scene")
        or context.get("action")
        or context.get("highlight")
        or context.get("subject_person_ids")
    )


def normalize(raw: dict, content: str, speaker_id: Optional[str]) -> Optional[dict]:
    """모델이 준 값을 저장할 모양으로 (LLM과 분리해 둔다 — 규칙을 시험할 수 있게)

    말한 사람은 모델에게 묻지 않는다. 누가 남긴 기억인지는 요청이 이미 알고 있고
    (contributor_id), 그것을 모델의 짐작으로 덮으면 남의 기억이 다른 사람 것으로
    적힌다.
    """
    if not isinstance(raw, dict):
        return None

    content = content or ""

    subjects: list[str] = []
    unmatched: list[str] = []
    for term in _terms(raw.get("subjects")):
        # 원문에 없는 사람은 버린다. 모델이 사건 제목이나 다른 기억에서 끌어온
        # 이름일 수 있고, 그러면 이 기억이 하지 않은 말을 하게 된다.
        if not _grounded(term, content):
            continue
        person_id = resolve_person(term)
        if not person_id:
            if term not in unmatched:
                unmatched.append(term)
            continue
        if person_id not in subjects:
            subjects.append(person_id)

    confidence = str(raw.get("confidence") or "").strip().lower()
    if confidence not in (CONFIDENCE_EXPLICIT, CONFIDENCE_INFERRED):
        confidence = CONFIDENCE_INFERRED

    context = {
        "speaker_id": speaker_id,
        "subject_person_ids": subjects,
        "scene": _phrase(raw.get("scene"), content),
        "action": _phrase(raw.get("action"), content),
        "highlight": _short(raw.get("highlight")),
        "confidence": confidence,
        # 그래프에 없어서 잇지 못한 호칭. 화면이 그대로 밝힌다.
        "unmatched": unmatched,
        # 이 맥락이 가리키는 원본과 그 근거 (relate_media가 채운다)
        "media_ids": [],
        "media_basis": None,
        # 나중에 image-to-video를 붙일 자리. 지금 들어가는 값은 원본 픽셀을 옮기는
        # 것뿐이다 (subject-focus = 인물 쪽으로 천천히 들어간다). 생성된 움직임을
        # 넣게 되면 그때는 반드시 "AI 생성 표현"으로 라벨을 나눠 적는다
        # (film_composer.GENERATED_MOTION_LABEL과 같은 방식).
        "visual_treatment": None,
    }

    if not is_usable(context) and not unmatched:
        return None
    return context


async def extract(content: str, speaker_id: Optional[str]) -> Optional[dict]:
    """기억 문장 하나에서 맥락을 뽑는다 (원문은 건드리지 않는다)

    부를 모델이 없으면 뽑지 않는다. 규칙 기반으로 흉내내면 잘못된 장면이 그래프에
    남고, 그게 화면에서는 사실처럼 보인다 (interview_engine.extract_and_link와
    같은 판단이다).
    """
    content = (content or "").strip()
    if not content or not llm_client.is_enabled("extract"):
        return None

    raw = await llm_client.complete_json(
        [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": content},
        ],
        max_tokens=300,
        model=EXAONE_PLANNER_MODEL,
        purpose="extract",
    )
    if not raw:
        return None
    return normalize(raw, content, speaker_id)


# --- 사진과 잇기 (엣지를 만들지 않는다) --------------------------------------


def relate_media(
    context: dict,
    memory_media: list[dict],
    event_media: list[dict],
) -> tuple[list[str], Optional[str]]:
    """이 맥락이 가리키는 사진을 고른다 (그래프에는 아무것도 쓰지 않는다)

    후보는 이미 이 사건에 붙어 있는 기록뿐이다. 사건 밖에서 끌어오지 않는다 —
    EXIF 날짜·좌표로 넓히면 "같은 날 찍힌 남의 사진"이 남의 기억에 붙는다. 사건은
    이미 날짜와 장소로 좁혀진 묶음이라 그 안에서 고르는 것으로 충분하다.

    확정할 근거가 없으면 빈 목록을 돌려준다. 맥락만 저장하고 사진은 잇지 않는 것이
    잘못된 사진을 자막에 세우는 것보다 낫다.

    Returns:
        (media_id 목록, 근거) — 근거는 BASIS_* 중 하나이거나 None
    """
    visual = [
        m
        for m in memory_media
        if m.get("media_type") in (MediaType.PHOTO, MediaType.VIDEO)
    ]
    if visual:
        # 사람이 이 기억과 함께 올린 기록이다. 더 볼 것이 없다.
        return [m["id"] for m in visual], BASIS_ATTACHED

    photos = [m for m in event_media if m.get("media_type") == MediaType.PHOTO]
    if not photos:
        return [], None

    # 사진 설명에 이 장면·행동이 실제로 적혀 있는가. 여기서 걸린 사진만
    # "사진에서 확인된 장면"이라고 말할 수 있다 (shows_action).
    scene_hits = [
        photo["id"]
        for photo in photos
        if _grounded(context.get("scene"), photo.get("scene_description") or "")
        or _grounded(context.get("action"), photo.get("scene_description") or "")
    ]
    if scene_hits:
        return scene_hits, BASIS_SCENE

    # 대상 인물이 태그된 사진. 얼굴 태그는 사람이 지목한 것일 수도, 얼굴 인식이
    # 짚은 것일 수도 있다 (MediaNode.faces_source) — 어느 쪽이든 "그 사람이 나온
    # 사진"까지가 근거이고, 그래서 이 근거로는 행동을 사진의 내용으로 적지 않는다.
    subjects = context.get("subject_person_ids") or []
    if subjects:
        person_hits = [
            photo["id"]
            for photo in photos
            if all(pid in (photo.get("detected_faces") or []) for pid in subjects)
        ]
        # 사건의 사진 전부에 그 사람이 있으면 고른 것이 없는 것과 같다. 그때
        # 전부를 "이 맥락의 사진"으로 적으면, 가리키는 것이 없는데 가리킨 척이 된다.
        if person_hits and len(person_hits) < len(photos):
            return person_hits, BASIS_PERSON

    return [], None


def shows_action(context: Optional[dict]) -> bool:
    """이 맥락의 장면이 사진에서 확인되는가

    확인되지 않으면 자막과 내레이션은 기억의 출처만 밝힌다. "하늘이가 물장구를
    쳤습니다"가 아니라 "엄마는 하늘이가 물장구치던 순간을 기억합니다"다.
    """
    return bool(context) and context.get("media_basis") == BASIS_SCENE


def resolve_media(context: dict, event_id: str, memory: dict) -> dict:
    """맥락에 사진 근거를 채워 돌려준다 (그래프는 그대로 둔다)

    이름을 memories.attach_media와 다르게 둔 이유가 있다. 그쪽은 사진을 사건에
    실제로 잇고(CAPTURED_DURING) 여기는 아무 엣지도 만들지 않는다 — 같은 이름을
    쓰면 읽는 사람이 여기서도 잇는다고 오해한다.
    """
    memory_media = [
        node
        for node in (graph_manager.get_node(mid) for mid in memory.get("media_ids") or [])
        if node and node.get("node_type") == NodeType.MEDIA
    ]
    event_media = [
        node
        for node in graph_manager.get_connected_nodes(event_id)
        if node.get("node_type") == NodeType.MEDIA
    ]
    media_ids, basis = relate_media(context, memory_media, event_media)
    context["media_ids"] = media_ids
    context["media_basis"] = basis
    if media_ids and (context.get("subject_person_ids") or []):
        # 인물이 있는 사진이면 그 인물 쪽으로 천천히 들어간다. 원본 픽셀을 옮기는
        # 것뿐이라 없던 장면이 생기지 않는다 (film_composer가 focus로 받는다).
        context["visual_treatment"] = "subject-focus"
    return context


# --- 화면과 내레이션이 쓰는 모양 ---------------------------------------------


def _person(person_id: Optional[str]) -> Optional[dict]:
    if not person_id:
        return None
    node = graph_manager.get_node(person_id)
    if not node or node.get("node_type") != NodeType.PERSON:
        return None
    return {
        "id": node["id"],
        "name": node.get("name", node["id"]),
        "relation": node.get("relation", ""),
    }


def _who(context: dict) -> str:
    """말한 사람을 부르는 말. 호칭이 있으면 호칭이다 ("엄마")"""
    speaker = _person(context.get("speaker_id"))
    if not speaker:
        return "가족"
    return speaker.get("relation") or speaker.get("name") or "가족"


def speaker_name(context: Optional[dict]) -> Optional[str]:
    """이 맥락을 남긴 사람의 이름 (화면이 "누구의 기억"인지 적을 때 쓴다)"""
    if not context:
        return None
    speaker = _person(context.get("speaker_id"))
    return speaker.get("name") if speaker else None


def _subject_names(context: dict) -> str:
    names = [
        (_person(pid) or {}).get("name", "")
        for pid in context.get("subject_person_ids") or []
    ]
    return ", ".join(n for n in names if n)


def caption(context: dict) -> str:
    """자막 한 줄 (Film 장면 · TV 슬라이드가 같은 문구를 쓴다)

    highlight를 그대로 쓰지 않는다. 그것은 모델이 쓴 해석이고, 자막은 화면에서
    가장 크게 읽히는 자리다. 여기 오르는 것은 사람·장소처럼 확인할 수 있는
    조각과 "누가 기억하는가"뿐이다.
    """
    who = _who(context)
    scene = context.get("scene")
    names = _subject_names(context)

    if scene:
        return f"{who}가 기억하는 {scene}"
    if names:
        return f"{who}가 기억하는 {names}"
    if context.get("action"):
        return f"{who}가 기억하는 순간"
    return f"{who}의 기억이 더해진 장면"


def event_note(context: dict) -> str:
    """이 사진을 가리키는 맥락이 아닐 때 (같은 사건에 남은 기억일 뿐이다)

    TV가 쓴다. 거실 화면은 사건에 걸린 사진을 차례로 넘기므로, 맥락이 가리키지
    않는 사진에도 자막이 올라간다. 그 자막이 이 사진의 설명으로 읽히면 안 된다.
    """
    return f"{_who(context)}의 기억에서 · 이 사진의 장면은 아닙니다"


def source_note(context: dict) -> str:
    """이 자막이 어디서 왔는지 (사진이 그 장면이라고 단정하지 않는다)"""
    who = _who(context)
    basis = context.get("media_basis")
    if basis == BASIS_ATTACHED:
        return f"{who}가 이 기억과 함께 올린 기록"
    if basis == BASIS_SCENE:
        return f"{who}의 기억이 더해진 장면 · 사진 설명에서 확인됨"
    if basis == BASIS_PERSON:
        return f"{who}의 기억이 더해진 장면 · 이 사진에 인물이 있습니다"
    return event_note(context)


def _moment(context: dict) -> str:
    """"부산 바다에서 하늘이가 물장구치던 순간" 같은 조각

    action은 프롬프트에서 "물장구치던"처럼 꾸밈말로 받는다. 그래도 모델이
    "물장구를 침"처럼 명사형을 주는 경우가 있어 두 모양을 갈라 쓴다 — 문장이
    어색해지는 것은 참을 수 있지만, 없는 말을 넣어 고치는 것은 안 된다.
    """
    scene = context.get("scene")
    names = _subject_names(context)
    action = context.get("action")

    parts = []
    if scene:
        parts.append(f"{scene}에서")

    if action and action[-1] in "던는한은":
        if names:
            parts.append(f"{names}{_subject_particle(names)} {action} 순간")
        else:
            parts.append(f"{action} 순간")
    elif action:
        parts.append(f"{names}의 {action}" if names else action)
    elif names:
        parts.append(f"{names}{_subject_particle(names)} 있던 순간")

    return " ".join(parts)


def narration_line(context: dict) -> str:
    """맥락 한 줄을 내레이션 문장으로 (모델 없이 쓰는 경로)

    주어는 언제나 기억한 사람이다. 사진에서 확인되지 않은 행동을 사진의 내용으로
    적지 않기 위한 것이고, 확인된 경우에도 이 형태를 유지한다 — 두 경로에서 문장
    구조가 갈리면 어느 쪽이 확인된 것인지 화면에서 읽을 수 없다.
    """
    moment = _moment(context)
    who = _who(context)
    if not moment:
        highlight = context.get("highlight")
        return f"{who}의 기억: {highlight}" if highlight else ""
    return f"{who}는 {moment}을 기억합니다."


def prompt_line(context: dict) -> str:
    """내레이션·이야기 프롬프트에 넣는 한 줄 (모델이 읽는다)

    사진에서 확인되지 않았다는 사실을 같은 줄에 적는다. 따로 적으면 모델이
    맥락만 읽고 넘어간다.
    """
    speaker = _person(context.get("speaker_id")) or {}
    who = speaker.get("name") or "가족"
    relation = speaker.get("relation")
    label = f"{who}({relation})" if relation else who

    bits = []
    if context.get("scene"):
        bits.append(f"장소={context['scene']}")
    names = _subject_names(context)
    if names:
        bits.append(f"대상={names}")
    if context.get("action"):
        bits.append(f"행동={context['action']}")
    if context.get("highlight"):
        bits.append(f"초점={context['highlight']}")

    tail = "[사진에서 확인됨]" if shows_action(context) else "[사진에서 확인되지 않음]"
    return f"- {label}의 기억: " + " · ".join(bits) + " " + tail


def view(context: Optional[dict], visible_media_ids: Optional[set] = None) -> Optional[dict]:
    """화면이 쓰는 모양 (인물 이름 · 볼 수 있는 사진 · 어디에 반영되는가)

    자막 문구를 화면이 조립하지 않게 서버가 함께 내려준다. 같은 문구가 상세 화면·
    Film·TV 세 곳에 나오는데 각자 만들면 조용히 갈라진다 (미세 모션 라벨에서 이미
    한 번 겪었다).
    """
    if not context:
        return None

    media_ids = [
        media_id
        for media_id in context.get("media_ids") or []
        if visible_media_ids is None or media_id in visible_media_ids
    ]
    # 근거가 보이지 않으면 근거도 비운다. 남겨 두면 볼 수 없는 사진을 두고
    # "사진 설명에서 확인됨"이라고 적게 된다 (from_memories와 같은 규칙).
    shown = context if media_ids else {**context, "media_basis": None}

    usable = is_usable(context)
    return {
        "speaker": _person(context.get("speaker_id")),
        "subjects": [
            person
            for person in (_person(pid) for pid in context.get("subject_person_ids") or [])
            if person
        ],
        "scene": context.get("scene"),
        "action": context.get("action"),
        "highlight": context.get("highlight"),
        "confidence": context.get("confidence") or CONFIDENCE_INFERRED,
        "unmatched": context.get("unmatched") or [],
        "media_ids": media_ids,
        "media_basis": shown.get("media_basis"),
        # 사진에서 확인된 장면인가. 화면은 확인되지 않은 행동을 사진 설명처럼
        # 적지 않는다.
        "shows_action": shows_action(shown),
        "caption": caption(shown) if usable else "",
        "source_note": source_note(shown) if usable else "",
        "visual_treatment": context.get("visual_treatment"),
        # 이 맥락이 Film 내레이션·자막과 TV 자막에 쓰이는가. 두 화면이 같은
        # 판단(is_usable)을 쓰므로 값이 하나다.
        "used_in_film": usable,
        "used_in_tv": usable,
    }


# --- 사건 단위로 모으기 ------------------------------------------------------


def from_memories(
    memories: list[dict],
    visible_media_ids: Optional[set] = None,
) -> list[dict]:
    """기억 목록에서 쓸 수 있는 맥락만 (오래된 것부터)

    memories는 이미 공개 범위를 지난 목록이어야 한다 (visibility.filter_memories).
    맥락이 가리키는 사진도 볼 수 있는 것만 남긴다 — 비공개로 바꾼 사진이 맥락을
    타고 Film 자막에 다시 나오면 설정이 무의미해진다.
    """
    result = []
    for memory in memories:
        context = memory.get("context")
        if not is_usable(context):
            continue
        picked = dict(context)
        if visible_media_ids is not None:
            picked["media_ids"] = [
                media_id
                for media_id in picked.get("media_ids") or []
                if media_id in visible_media_ids
            ]
            if not picked["media_ids"]:
                # 근거가 보이지 않으면 근거도 비운다. 남겨 두면 볼 수 없는 사진을
                # 두고 "사진에서 확인됨"이라고 적게 된다.
                picked["media_basis"] = None
        picked["memory_id"] = memory.get("id")
        result.append(picked)
    return result


def contexts_of(event_id: str, viewer_id: Optional[str] = None) -> list[dict]:
    """사건 하나에 쌓인 맥락 (TV처럼 기억 목록을 따로 들고 있지 않은 쪽이 쓴다)"""
    connected = graph_manager.get_connected_nodes(event_id)
    memories = visibility.filter_memories(
        [n for n in connected if n.get("node_type") == NodeType.MEMORY], viewer_id
    )
    memories.sort(key=lambda m: m.get("created_at") or "")
    visible = {
        m["id"]
        for m in visibility.filter_media(
            [n for n in connected if n.get("node_type") == NodeType.MEDIA], viewer_id
        )
    }
    return from_memories(memories, visible)


def for_media(contexts: list[dict], media_id: str) -> Optional[dict]:
    """이 사진을 가리키는 맥락 (근거가 강한 것 먼저)"""
    order = {BASIS_ATTACHED: 0, BASIS_SCENE: 1, BASIS_PERSON: 2}
    hits = [c for c in contexts if media_id in (c.get("media_ids") or [])]
    if not hits:
        return None
    hits.sort(key=lambda c: order.get(c.get("media_basis"), 3))
    return hits[0]


def primary(contexts: list[dict]) -> Optional[dict]:
    """사건을 대표하는 맥락 하나 (사진을 가리키는 것이 있으면 그쪽)"""
    if not contexts:
        return None
    for context in contexts:
        if context.get("media_ids"):
            return context
    return contexts[0]


def prioritize(photos: list[dict], contexts: list[dict]) -> list[dict]:
    """맥락이 가리키는 사진을 앞으로 (그 안의 순서는 그대로 둔다)

    빼지 않는다. 앞으로만 옮긴다 — 가족이 올린 사진을 맥락이 없다는 이유로
    영상에서 떨어뜨리면, 기억을 더한 것이 다른 사진을 지우는 일이 된다.
    """
    if not contexts:
        return photos

    order = {BASIS_ATTACHED: 0, BASIS_SCENE: 1, BASIS_PERSON: 2}
    rank: dict[str, int] = {}
    for context in contexts:
        weight = order.get(context.get("media_basis"), 3)
        for media_id in context.get("media_ids") or []:
            rank[media_id] = min(rank.get(media_id, 9), weight)

    # 같은 등급 안에서는 원래 순서를 지킨다 (sorted는 안정 정렬이다)
    return sorted(photos, key=lambda photo: rank.get(photo["id"], 8))


def focus_of(context: Optional[dict], photo: dict) -> Optional[dict]:
    """맥락의 인물이 사진에서 어디에 있는가 (0~1 비율)

    사진에 저장된 얼굴 위치를 그대로 쓴다 (MediaNode.face_boxes). 화면은 이
    지점을 기준으로 천천히 들어간다 — 잘라내거나 새로 만드는 것이 아니라
    확대의 중심을 옮기는 것뿐이다.
    """
    if not context:
        return None
    subjects = context.get("subject_person_ids") or []
    if not subjects:
        return None

    points = []
    for entry in photo.get("face_boxes") or []:
        if entry.get("person_id") not in subjects:
            continue
        box = entry.get("box") or {}
        try:
            x = float(box["left"]) + float(box["width"]) / 2
            y = float(box["top"]) + float(box["height"]) / 2
        except (KeyError, TypeError, ValueError):
            continue
        points.append((x, y))

    if not points:
        return None
    return {
        "x": round(sum(p[0] for p in points) / len(points), 4),
        "y": round(sum(p[1] for p in points) / len(points), 4),
    }
