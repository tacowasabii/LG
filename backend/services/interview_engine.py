"""AI Memory Interview Engine - 기억의 빈 곳을 질문하며 새로운 기록 수집

기획안의 마지막 단계(STEP 06 "이어가기")가 여기서 닫힌다. 답변을 문장으로만
쌓으면 그래프는 자라지 않는다. 그래서 답변에서 인물·장소·시점을 뽑아
추억에 잇는다 (기획안 02장 Memory Interview: "답변에서 추억·인물·시점 추출").

다만 AI가 가족사를 새로 쓰지는 않는다. 지키는 선은 셋이다.
  1. 없는 사람을 만들지 않는다. 그래프에 이미 있는 인물·장소에만 잇는다 —
     "큰엄마"가 누구인지는 가족만 안다.
  2. 있는 값을 덮어쓰지 않는다. 비어 있는 자리(날짜 없음·장소 없음)만 채운다.
  3. 이렇게 넣은 것은 추정이다. ai_inferred로 표시해 어디까지가 AI가 채운
     것인지 데이터가 알고 있게 한다. 가족이 고칠 때 사람이 쓴 값으로 바뀐다.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from backend.config import EXAONE_PLANNER_MODEL
from backend.services import kinship, llm_client
from backend.models.graph_models import (
    MemoryNode, Edge, RelationType, SourceType, Confidence, NodeType,
)
from backend.services.graph_manager import graph_manager
from backend.services.question_picker import pick_target, remember_asked


# 인터뷰 세션 저장 (MVP: in-memory)
_sessions: dict[str, dict] = {}

# 사람별로 예전에 물은 질문 (MVP: in-memory)
#
# 세션은 끝나면 사라진다. 그래서 같은 사람이 다시 인터뷰를 시작하면 모델은
# 첫 질문을 백지에서 냈고, 백지에서 낸 첫 질문은 늘 비슷했다 — 같은 사람이
# 세 번 들어와 세 번 "가장 기억에 남는 순간"을 들었다. 추억은 회전하는데
# (question_picker) 질문의 말투와 각도가 회전하지 않았다.
_asked_questions: dict[str, list[str]] = {}

# 몇 개를 기억할지. 세션 하나가 질문 5개이므로 12개면 최근 두세 번의 인터뷰가
# 덮인다. 무한히 쌓으면 프롬프트가 질문 목록으로 채워진다.
_ASKED_KEEP = 12


INTERVIEW_SYSTEM_PROMPT = """너는 가족의 기억을 받아 적는 따뜻한 인터뷰어야.
지금 화면 앞에는 한 사람이 앉아 있다. [인터뷰 대상]에 적힌 그 사람에게 묻는다.

규칙:
1. 한 번에 하나만 묻는다. 두 가지를 이어 붙이지 마.
2. [인터뷰 대상]에게 직접 묻는다. 다른 사람을 그 자리에 세우지 마 —
   답하는 사람이 아빠인데 "서연님, 기억나세요?"라고 물으면 안 된다.
3. [가족 구성원]에 있는 사람만 언급한다. 목록에 없는 사람이나 호칭(형, 누나,
   삼촌, 사촌 같은 말)을 만들어 내지 마. 확실하지 않으면 이름을 쓴다.
4. 존댓말을 끝까지 유지한다. 중간에 반말로 바꾸지 마.
5. [지금까지의 대화]에 이미 나온 질문을 다시 하지 않는다.
6. 질문은 구체적이고 답하기 쉬워야 한다. 따뜻하게, 두 문장 안에.
7. 한국어로 묻는다.
"""

# "모르겠다"는 답. 같은 것을 또 물으면 대화가 제자리를 돈다 (실제로 그랬다 —
# 모른다고 답한 질문을 모델이 다음 차례에 그대로 다시 냈다).
_NO_MEMORY = re.compile(
    r"모르겠|모름|잘\s*몰라|기억\s*(이|은)?\s*(안|없)|기억나지\s*않|생각\s*(이)?\s*안|글쎄"
)


async def start_interview(
    target_type: str = "auto",
    target_id: Optional[str] = None,
    speaker_id: Optional[str] = None,
) -> dict:
    """인터뷰 세션 시작

    target_type: "event" | "media" | "auto"
    - auto: 아직 덜 채워진 추억을 하나 골라 묻는다

    speaker_id  지금 화면 앞에서 답할 사람. 인터뷰 대상은 이 사람이다.

                이 인자가 없던 동안 question_picker가 고른 인물(그 추억에 기억을
                남기지 않은 참여자)이 인터뷰 대상이 됐다. 아빠로 로그인한 화면이
                "서연님, 그때 기억나세요?"라고 물었고, 그 뒤로 모델은 답변을
                서연의 기억으로 읽었다 ("서연이가 뛰어노는 순간들을…").
                기억은 답한 사람의 것이므로 질문도 그 사람을 향해야 한다.
    """
    session_id = str(uuid.uuid4())

    speaker = graph_manager.get_node(speaker_id) if speaker_id else None
    if speaker and speaker.get("node_type") != NodeType.PERSON:
        speaker = None

    # 타겟 결정
    target_node = None
    # 수집한 기억을 누구의 것으로 기록할지. 답할 사람을 알면 그 사람이다.
    contributor_id = speaker["id"] if speaker else None

    if target_id:
        target_node = graph_manager.get_node(target_id)

    # question_picker에 넘긴 사람. 아래에서 contributor_id가 바뀔 수 있으므로
    # 따로 붙잡아 둔다 — 무엇을 물었는지 적어 둘 때 같은 이름으로 세야 한다.
    asked_by = contributor_id

    if not target_node and target_type == "auto":
        # 물어볼 추억을 하나 고른다 (목록을 만들지 않는다 — question_picker)
        target = pick_target(speaker_id=asked_by)
        target_node = target.get("event")
        if not speaker:
            # 누가 답할지 모르는 경우에만 picker가 지목한 인물에게 묻는다
            contributor_id = target.get("person_id")

    # 무엇을 물었는지 남긴다. 시작만 하고 그만둔 경우에도 남겨야 다음에 같은
    # 추억이 다시 나오지 않는다 — 답을 기다리면 그래프가 자라지 않아 auto가
    # 같은 점수를 다시 계산하고, 화면은 부산 여행만 되풀이해 물었다.
    remember_asked(asked_by, (target_node or {}).get("id"))

    subject = speaker or (graph_manager.get_node(contributor_id) if contributor_id else None)
    contributor_name = subject.get("name") if subject else None

    # 타겟 정보 구성
    context = _build_interview_context(target_node, subject)

    # 추억 당시 이 사람의 나이. 같은 추억이어도 두 살과 스물여덟 살에게 물을
    # 것이 다르다 — 컨텍스트와 규칙 양쪽에 넣고, 폴백 질문도 이것으로 고른다.
    age = _age_at(subject, target_node)
    age_rule = _age_rule(subject, target_node)

    # 예전 세션에서 이 사람에게 물은 것 (세션은 끝나면 사라진다)
    prior = _prior_questions(contributor_id)

    # 첫 질문 생성
    first_question = await _generate_question(
        context, [], [], contributor_name, age_rule=age_rule, prior=prior, age=age
    )
    _remember_question(contributor_id, first_question)

    # 세션 저장
    _sessions[session_id] = {
        "target_node": target_node,
        "context": context,
        "contributor_id": contributor_id,
        "contributor_name": contributor_name,
        "age": age,
        "age_rule": age_rule,
        "prior": prior,
        "questions": [first_question],
        "answers": [],
        "updated_nodes": [],
        "question_count": 1,
        "max_questions": 5,
    }

    return {
        "session_id": session_id,
        "question": first_question,
        "context": {
            "target_type": target_node.get("node_type") if target_node else None,
            "target_id": target_node.get("id") if target_node else None,
            "target_title": target_node.get("title", target_node.get("name", "")) if target_node else None,
            "contributor_name": contributor_name,
        },
    }


async def process_answer(
    session_id: str,
    answer: str,
    speaker_id: Optional[str] = None,
    audio_media_id: Optional[str] = None,
) -> dict:
    """사용자 답변 처리 → Graph 업데이트 + 다음 질문 생성

    speaker_id     화면에서 고른 "지금 답하는 사람"
    audio_media_id 말로 답한 경우 먼저 업로드된 음성
    """
    session = _sessions.get(session_id)
    if not session:
        return {
            "session_id": session_id,
            "next_question": None,
            "is_complete": True,
            "updated_nodes": [],
            "message": "세션을 찾을 수 없습니다.",
        }

    # 답하는 사람이 바뀌었으면 세션을 그 사람에게 다시 맞춘다. 답변을 그래프에
    # 넣기 전에 한다 — 아래 _process_answer_to_graph도 같은 사람을 봐야 한다.
    _retarget_session(session, speaker_id)

    # 이 답변이 답한 질문. answers에 담기 전에 짚어 둔다 (아래 _asked_question)
    asked = _asked_question(session)

    # 답변 저장
    session["answers"].append(answer)

    # 답변에서 정보 추출 → Memory 노드 생성 + 추억에 잇기
    updated_nodes = await _process_answer_to_graph(
        session,
        answer,
        speaker_id=speaker_id,
        audio_media_id=audio_media_id,
        question=asked,
    )
    session["updated_nodes"].extend(updated_nodes)
    # 방금 답변에서 무엇을 알아냈는지. 화면이 그대로 보여 준다 — 그래프가
    # 조용히 자라면 사용자는 자기 말이 어디로 갔는지 알 수 없다.
    extracted = (session.get("extracted") or [{}])[-1]

    # 종료 조건 확인
    is_complete = session["question_count"] >= session["max_questions"]

    next_question = None
    if not is_complete:
        # 다음 질문 생성. 지금까지 물은 것을 함께 넘긴다 — 이것을 주지 않아서
        # 모델이 같은 질문을 다시 냈다.
        next_question = await _generate_question(
            session["context"],
            session["questions"],
            session["answers"],
            session.get("contributor_name"),
            age_rule=session.get("age_rule"),
            prior=session.get("prior") or [],
            age=session.get("age"),
        )
        session["questions"].append(next_question)
        session["question_count"] += 1
        _remember_question(session.get("contributor_id"), next_question)

    return {
        "session_id": session_id,
        "next_question": next_question,
        "is_complete": is_complete,
        "updated_nodes": updated_nodes,
        "extracted": {
            "persons": extracted.get("persons") or [],
            "place": extracted.get("place"),
            "date": extracted.get("date"),
            "filled": extracted.get("filled") or [],
            "unmatched": extracted.get("unmatched") or [],
        },
        "message": "감사합니다! 소중한 기억이 기록되었어요." if is_complete else "",
    }


def _retarget_session(session: dict, speaker_id: Optional[str]) -> bool:
    """답하는 사람이 바뀌면 질문도 그 사람을 향하게 한다 (바꿨으면 True)

    화면의 "지금 답하는 사람"은 대화 중에도 바뀐다 (InterviewPage의
    useCurrentUser). 세션은 시작할 때의 사람을 붙잡고 있었고, 답변 귀속만
    speaker_id를 따랐다 (_process_answer_to_graph). 그래서 기억은 새 사람에게
    붙는데 질문은 계속 예전 사람을 불렀다 — 김민수로 바꿨는데도 화면이
    "박서연님께서는"으로 물었다.

    기억은 답한 사람의 것이고, 질문도 답하는 사람을 향해야 한다. 둘이
    갈라지면 어느 쪽이 맞는지 데이터가 말할 수 없다.
    """
    if not speaker_id or speaker_id == session.get("contributor_id"):
        return False
    speaker = graph_manager.get_node(speaker_id)
    if not speaker or speaker.get("node_type") != NodeType.PERSON:
        return False

    target_node = session.get("target_node")
    session["contributor_id"] = speaker["id"]
    session["contributor_name"] = speaker.get("name")
    # 컨텍스트를 다시 짠다. 명단의 시점 호칭·그때 나이·기억의 주인이 모두
    # 답하는 사람을 기준으로 적혀 있다.
    session["context"] = _build_interview_context(target_node, speaker)
    session["age"] = _age_at(speaker, target_node)
    session["age_rule"] = _age_rule(speaker, target_node)
    session["prior"] = _prior_questions(speaker["id"])
    return True


def get_session_status(session_id: str) -> Optional[dict]:
    """인터뷰 세션 상태 조회"""
    session = _sessions.get(session_id)
    if not session:
        return None
    return {
        "session_id": session_id,
        "question_count": session["question_count"],
        "max_questions": session["max_questions"],
        "is_complete": session["question_count"] >= session["max_questions"],
        "updated_nodes": session["updated_nodes"],
    }


def _prior_questions(person_id: Optional[str]) -> list[str]:
    """이 사람에게 예전 세션에서 물은 질문"""
    return list(_asked_questions.get(person_id or "", ()))


def _remember_question(person_id: Optional[str], question: Optional[str]) -> None:
    """이 사람에게 이 질문을 물었다고 적어 둔다"""
    if not person_id or not question:
        return
    asked = [q for q in _asked_questions.get(person_id, []) if q != question]
    asked.append(question)
    _asked_questions[person_id] = asked[-_ASKED_KEEP:]


def forget_questions() -> None:
    """물어본 질문을 잊는다 (테스트가 첫 질문 상태를 만들 때 쓴다)"""
    _asked_questions.clear()


def _age_at(subject: Optional[dict], target: Optional[dict]) -> Optional[int]:
    """그 추억·사진의 해에 이 사람이 몇 살이었나 (알 수 없으면 None)

    연 나이로 센다. 생일 경과까지 보면 한 살이 오갈 수 있지만, 여기서 쓰는 것은
    "아이였나 어른이었나"이므로 한 살 차이는 답이 바뀌지 않는다.

    추억은 date_start, 미디어는 exif_date에 날짜가 있다. 추억만 보면 사진을
    타겟으로 시작한 인터뷰(target_type="media")는 나이를 모른 채 묻는다.
    """
    if not subject or not target:
        return None
    birth_year = subject.get("birth_year")
    year = (target.get("date_start") or target.get("exif_date") or "")[:4]
    if not birth_year or not year.isdigit():
        return None
    return int(year) - int(birth_year)


# 그때 몇 살이었나에 따라 물어도 되는 것이 다르다. (상한 나이, 그때 무엇이었나,
# 무엇을 물어야 하는지).
#
# 이것이 없는 동안 프롬프트는 나이를 몰랐다. 시드 그래프에서 1998년 부산 여행에
# 참여자로 걸린 김하늘은 그때 두 살이다 — 모델은 두 살에게 "그때 어떤 기분이
# 드셨어요?"를 물었다. 답할 수 없는 질문이고, 답하면 남는 것은 기억이 아니다.
_AGE_BANDS: tuple[tuple[int, str, str], ...] = (
    (-1, "아직 태어나기 전이다",
     "그때를 기억하냐고 묻지 않는다. 가족에게 전해 들은 이야기나, "
     "이 사진·영상을 지금 보면서 드는 생각을 묻는다."),
    (3, "너무 어려 직접 기억이 남지 않는 나이다",
     "그때가 기억나냐고 묻지 않는다. 가족에게 들은 이야기나, "
     "사진을 보면서 드는 생각을 묻는다."),
    (12, "아이였다",
     "보이고 들리고 만져진 것, 누구와 무엇을 하고 놀았는지를 묻는다. "
     "어른의 사정이나 집안의 결정 이유는 묻지 않는다."),
    (18, "청소년이었다",
     "그 무렵의 마음과 가족과의 관계를 물어도 좋다. "
     "집안의 형편이나 어른들의 결정은 묻지 않는다."),
)

_ADULT_BAND = (
    "어른이었다",
    "그날을 어떻게 준비했고 무엇을 마음에 두었는지, 다른 가족의 사정까지 물어도 좋다.",
)


def _age_band(age: Optional[int]) -> Optional[tuple[str, str]]:
    """그 나이에 물어도 되는 것 (나이를 모르면 None)"""
    if age is None:
        return None
    for limit, what, guide in _AGE_BANDS:
        if age <= limit:
            return what, guide
    return _ADULT_BAND


def _age_rule(subject: Optional[dict], event: Optional[dict]) -> Optional[str]:
    """나이에서 나오는 규칙 한 줄 (프롬프트 규칙 목록에 넣는다)

    컨텍스트에도 같은 내용이 들어가지만, 규칙 목록에 한 번 더 둔다 — 컨텍스트
    안쪽에만 두면 다섯 번째 질문쯤에서 잊혔다.
    """
    band = _age_band(_age_at(subject, event))
    if not band:
        return None
    name = (subject or {}).get("name") or ""
    who = f"{name}님은" if name else "이 사람은"
    return f"{who} 그때 {band[0]}. {band[1]}"


def _family_roster(subject: Optional[dict] = None) -> str:
    """가족 명단과 서로의 관계

    모델에게 이것을 주지 않으면 없는 사람을 지어낸다. 남매뿐인 가족에게
    "형이나 엄마와 함께했던 순간"을 물은 일이 있었다 — 형은 없다.
    """
    persons = graph_manager.get_persons()
    if not persons:
        return ""

    lines = ["[가족 구성원] — 이 목록에 있는 사람만 언급한다"]
    for person in persons:
        bits = []
        if person.get("relation"):
            bits.append(person["relation"])
        if person.get("birth_year"):
            bits.append(f"{person['birth_year']}년생")
        is_subject = bool(subject and person.get("id") == subject.get("id"))
        mark = " ← 지금 답하는 사람" if is_subject else ""
        detail = f" · {', '.join(bits)}" if bits else ""

        # 답하는 사람이 이 사람을 뭐라고 부르는지. 명단에는 "김하늘 — 김지우:
        # 남매"처럼 방향 없는 관계만 있었고, 방향을 모델이 메우면서 없는 사람이
        # 나왔다 (김지우에게 김하늘은 누나인데 "형"이라고 물었다).
        term = None if is_subject else kinship.address_term(subject, person)
        called = f' (부를 때: "{term}")' if term else ""

        lines.append(f"- {person.get('name', '')}{detail}{mark}{called}")

    # 서로를 어떻게 부르는지는 관계 엣지에 있다. 이것이 없으면 모델이 호칭을
    # 짐작하고, 짐작한 호칭이 없는 사람을 만든다.
    seen = set()
    relations = []
    for a, b, label in kinship.person_relation_edges():
        if not label:
            continue
        key = tuple(sorted((a.get("id", ""), b.get("id", "")))) + (label,)
        if key in seen:
            continue
        seen.add(key)
        relations.append(f"- {a.get('name', '')} — {b.get('name', '')}: {label}")

    if relations:
        lines.append("[사람 사이의 관계]")
        lines.extend(relations)

    return "\n".join(lines)


def _build_interview_context(target_node: Optional[dict], subject: Optional[dict] = None) -> str:
    """인터뷰 컨텍스트 구성

    subject는 지금 답하는 사람의 인물 노드다. 명단과 함께 맨 앞에 둔다 —
    누구에게 묻는 자리인지가 흐려지면 모델은 다른 사람을 그 자리에 세운다.
    """
    lines = []

    roster = _family_roster(subject)
    if roster:
        lines.append(roster)

    if subject:
        relation = subject.get("relation") or ""
        who = subject.get("name", "") + (f" · {relation}" if relation else "")
        lines.append(
            f"[인터뷰 대상] {who} — 지금 화면 앞에서 답하는 사람이다. "
            "이 사람에게 직접 존댓말로 묻고, 다른 사람을 그 자리에 세우지 않는다."
        )

    if not target_node:
        lines.append("[주제] 정해진 추억 없이 가족의 기억을 전반적으로 묻는다.")
        return "\n".join(lines)

    # 그때 이 사람이 몇 살이었나. 같은 추억이어도 두 살과 스물여덟 살에게 물을
    # 것은 다르다 — 이것이 없어서 두 살에게 그날의 심정을 물었다.
    age = _age_at(subject, target_node)
    band = _age_band(age)
    if band:
        who = (subject or {}).get("name") or "이 사람"
        when = f"그때 {age}살" if age >= 0 else f"{-age}년 뒤에 태어난다"
        lines.append(f"[그때 이 사람] {who}님은 {when} — {band[0]}.")
        lines.append(f"  -> {band[1]}")

    node_type = target_node.get("node_type", "")

    if node_type == "event":
        lines.append(f"[주제] {target_node.get('title', '')}")
        lines.append(f"날짜: {target_node.get('date_start', '미상')}")
        lines.append(f"설명: {target_node.get('description', '없음')}")

        # 참여자. 그때 몇 살이었는지 함께 준다 — 이름만 주면 모델은 지금의
        # 나이로 읽는다 (1998년 사진을 두고 두 살이던 사람에게 어른의 일을 물었다).
        connected = graph_manager.get_connected_nodes(target_node["id"])
        persons = [n for n in connected if n.get("node_type") == "person"]
        if persons:
            who = []
            for person in persons:
                years = _age_at(person, target_node)
                who.append(
                    f"{person.get('name', '')}({years}살)"
                    if years is not None and years >= 0
                    else person.get("name", "")
                )
            lines.append(f"참여자: {', '.join(who)}")

        # 그때 아직 없던 사람. 이것을 적어 두지 않으면 모델이 명단에 있는 이름을
        # 그 자리에 세운다 — 2000년생 김지우에게 1998년 여행에서 무엇을 했는지
        # 물을 수 있다. "있는 사람만 언급한다"는 규칙으로는 막히지 않는다,
        # 김지우는 이 가족에 있는 사람이다.
        # 답하는 사람은 뺀다. 그 사람이 그때 없었다는 것은 [그때 이 사람]이
        # 이미 말하고 있고, 여기 또 넣으면 "이 자리에 세우지 않는다"가 인터뷰
        # 대상을 가리켜 앞뒤가 어긋난다.
        unborn = [
            person.get("name", "")
            for person in graph_manager.get_persons()
            if person.get("id") != (subject or {}).get("id")
            and (_age_at(person, target_node) or 0) < 0
        ]
        if unborn:
            lines.append(
                f"그때 아직 태어나지 않은 사람: {', '.join(unborn)} — 이 자리에 세우지 않는다"
            )

        # 이미 기록된 기억. 누가 남긴 것인지 함께 준다 — 화자를 빼면 모델이
        # 기억의 주인을 뒤바꿔 말한다 (아빠에게 "아버지가 찍으셨다고 하는데"라고
        # 되물은 일이 있었다).
        # 본인이 남긴 것과 다른 가족이 남긴 것을 갈라서 준다. 섞어서 주던 동안
        # 지시가 하나뿐이었다 ("같은 것을 다시 묻지 않는다") — 그래서 아빠가 이미
        # 말한 장면도, 엄마만 말한 장면도 똑같이 피해야 할 것이 됐다. 그런데 남이
        # 말한 장면을 이 사람 시점에서 다시 묻는 것은 겹치는 것이 아니라 관점이
        # 하나 늘어나는 일이다 — question_picker가 노리는 것이 그것이다.
        memories = [n for n in connected if n.get("node_type") == "memory"]
        subject_id = (subject or {}).get("id")
        subject_name = (subject or {}).get("name") or ""
        mine = [m for m in memories if subject_id and m.get("contributor_id") == subject_id]
        mine_ids = {m.get("id") for m in mine}
        theirs = [m for m in memories if m.get("id") not in mine_ids]

        if mine:
            lines.append(
                f"{subject_name}님이 이 추억에 이미 남긴 기억 (같은 것을 다시 묻지 않는다):"
                if subject_name
                else "이미 기록된 기억 (같은 것을 다시 묻지 않는다):"
            )
            for m in mine[:3]:
                lines.append(f"  - {(m.get('content') or '')[:100]}")

        if theirs:
            tail = (
                f"참고만 한다. 같은 장면이라도 {subject_name}님이 본 것을 새로 물어도 좋다"
                if subject_name
                else "참고만 한다"
            )
            lines.append(f"다른 가족이 남긴 기억 ({tail}):")
            for m in theirs[:3]:
                contributor = graph_manager.get_node(m.get("contributor_id") or "")
                content = (m.get("content") or "")[:100]
                who = contributor.get("name") if contributor else None
                lines.append(f"  - {who}: {content}" if who else f"  - {content}")

    elif node_type == "media":
        lines.append(f"미디어: {target_node.get('original_filename', '')}")
        lines.append(f"날짜: {target_node.get('exif_date', '미상')}")
        lines.append(f"타입: {target_node.get('media_type', '')}")

    return "\n".join(lines)


def _dialogue(questions: list[str], answers: list[str]) -> str:
    """지금까지 주고받은 것 (질문과 답을 짝지어서)

    답변만 넘기던 동안 모델은 자기가 무엇을 물었는지 몰랐다. 그래서 "모르겠어요"를
    받으면 같은 질문을 다시 냈다 — 대화가 제자리를 돌았다.
    """
    if not answers:
        return "(첫 질문입니다)"

    lines = []
    for i, answer in enumerate(answers):
        if i < len(questions) and questions[i]:
            lines.append(f"Q{i + 1}. {questions[i]}")
        lines.append(f"A{i + 1}. {answer}")
    return "\n".join(lines)


def _question_messages(
    context: str,
    questions: list[str],
    answers: list[str],
    subject_name: Optional[str] = None,
    age_rule: Optional[str] = None,
    prior: list[str] | tuple = (),
) -> list[dict]:
    """질문 생성 프롬프트 (LLM 호출과 분리해 둔다 — 규칙을 시험할 수 있게)

    age_rule  추억 당시 이 사람의 나이에서 나오는 규칙 (_age_rule)
    prior     예전 세션에서 이 사람에게 물은 질문. questions와 섞지 않는다 —
              questions는 answers와 번호를 맞춰야 해서(_dialogue) 여기에
              예전 질문이 끼면 질문과 답이 어긋난다.
    """
    rules = [
        "위 대화에 이미 나온 질문을 다시 하지 마세요. 말만 바꿔 같은 것을 묻는 것도 안 됩니다.",
        "[가족 구성원]에 없는 사람이나 호칭을 만들지 마세요. 확실하지 않으면 이름을 쓰세요.",
        "아직 비어 있는 것(날짜, 장소, 함께 있던 사람, 그때의 장면이나 감정)을 채우는 질문이면 좋습니다.",
    ]
    if age_rule:
        # 나이 규칙을 앞쪽에 둔다. 컨텍스트 안쪽에도 같은 내용이 있지만 거기
        # 하나만 두면 뒤쪽 질문에서 잊혔다.
        rules.insert(0, age_rule)
    if subject_name:
        rules.insert(0, f"{subject_name}님에게 직접, 존댓말로 묻습니다.")
    if answers and _NO_MEMORY.search(answers[-1]):
        # 기억나지 않는다는 답이다. 더 캐물으면 답할 수 없는 질문을 반복하게 된다.
        rules.insert(0, '직전 답변은 "기억나지 않는다"는 뜻입니다. 그 질문을 되풀이하지 말고 다른 주제로 넘어가세요.')

    # 예전 인터뷰에서 이 사람에게 물은 것. 세션마다 백지에서 시작하던 동안
    # 같은 사람이 여러 번 들어와도 첫 질문이 늘 비슷했다.
    history = ""
    if prior:
        nl = chr(10)
        asked = nl.join(f"- {q}" for q in prior)
        history = f"[예전 인터뷰에서 이미 물은 것] — 다시 묻지 않는다{nl}{asked}{nl}{nl}"

    user_content = f"""[인터뷰 대상 정보]
{context}

{history}[지금까지의 대화]
{_dialogue(questions, answers)}

다음 질문 하나만 쓰세요.
""" + "\n".join(f"- {rule}" for rule in rules)

    return [
        {"role": "system", "content": INTERVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _normalize_question(text: str) -> str:
    """비교용으로 공백·문장부호를 떼어낸 형태"""
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", text or "")


def _repeats(question: str, questions: list[str]) -> bool:
    """이미 물은 질문을 그대로 다시 낸 것인가

    말을 바꿔 묻는 것까지 잡지는 않는다. 글자 겹침으로 재면 정상적인 후속
    질문("그 수영장은 어디였나요?")이 걸린다 — 여기서 막는 것은 같은 문장이
    다시 나오는 경우다.
    """
    current = _normalize_question(question)
    if not current:
        return False
    for asked in questions:
        past = _normalize_question(asked)
        if past and (current == past or current in past or past in current):
            return True
    return False


# 모델이 프롬프트를 그대로 베껴 오는 자리들. 화면에 이런 것이 나갔다:
#
#   "Q3. 교문 앞에서 사진을 찍고 나면, 가장 먼저 도착한 곳은 어디였나요?"
#   "김민수님에게 직접, 존댓말로 묻습니다."
#
# 앞의 것은 [지금까지의 대화]의 "Q1./A1." 번호를, 뒤의 것은 규칙 목록을
# 베낀 것이다. 프롬프트에 "베끼지 마라"를 더 적어도 막히지 않는다 — 모델이
# 문서를 이어 쓰는 쪽으로 읽으면 형식까지 따라온다. 그래서 나가는 자리에서
# 걸러낸다.
_LABEL = re.compile(r"^\s*(?:[QA]\s*\d*|질문|물음|답|답변)\s*[.:)\]]\s*", re.I)

# 규칙 목록·컨텍스트 제목처럼 질문이 아닌 줄
_SCAFFOLD = re.compile(
    # 목록·제목·머리말로 시작하는 줄
    r"^\s*(?:[-*•]\s|\[|#|다음 질문|규칙\s*[:0-9])"
    # 규칙 문구 그대로. "에게 직접"만으로 재면 정상 질문이 걸린다 —
    # "하늘이에게 직접 말해 주셨나요?"는 버려서는 안 된다.
    r"|^\S{1,12}님에게 직접"
    r"|존댓말로 묻|다시 하지 마세요|만들지 마세요"
)


def _clean_question(text: Optional[str]) -> str:
    """모델이 준 것에서 화면에 나갈 한 문장만 남긴다 (없으면 빈 문자열)

    줄 단위로 본다. 규칙 목록·대괄호 제목은 버리고, 남은 첫 줄에서 "Q3." 같은
    번호표를 뗀다. 질문을 고쳐 쓰지는 않는다 — 여기서 하는 일은 프롬프트에서
    새어 나온 것을 떼는 것까지다.
    """
    if not text:
        return ""

    for line in (text or "").splitlines():
        line = line.strip().strip("`").strip()
        if not line or _SCAFFOLD.search(line):
            continue
        # 번호표가 겹쳐 오기도 한다 ("Q3. Q3. 교문 앞에서…") — 남지 않을
        # 때까지 뗀다.
        while True:
            stripped = _LABEL.sub("", line).strip()
            if stripped == line:
                break
            line = stripped
        if line:
            return line
    return ""


def _calls_someone_else(question: str, subject_name: Optional[str]) -> Optional[str]:
    """다른 가족을 불러 세운 질문인가 (아니면 None)

    화면에서 이런 일이 있었다: 김민수로 인터뷰하는 중에 질문이 "박서연님께서는"
    으로 시작했다. 답하는 사람이 김민수인데 대답을 박서연에게 청한 것이다.

    문장 맨 앞만 본다. 다른 사람을 **가리키는** 것은 정상이다 ("박서연님은
    그때 어디 계셨나요?"는 김민수에게 묻는 질문이다). 잘못된 것은 다른 사람을
    **부르는** 것이고, 부르는 자리는 문장 맨 앞이다.
    """
    if not question:
        return None
    head = question.strip()
    for person in graph_manager.get_persons():
        name = (person.get("name") or "").strip()
        if not name or name == (subject_name or ""):
            continue
        if re.match(rf"^{re.escape(name)}(님|씨)?\s*[,，]|^{re.escape(name)}(님|씨)?께서", head):
            return (
                f"{name}님을 부르면 안 됩니다. 지금 답하는 사람은 "
                f"{subject_name or '[인터뷰 대상]에 적힌 사람'}입니다."
            )
    return None


def _problem_with(
    question: str,
    questions: list[str],
    subject_name: Optional[str] = None,
) -> Optional[str]:
    """이 질문을 그대로 내보낼 수 없는 이유 (없으면 None)

    모델에게 그대로 돌려줄 문장으로 쓴다. "다시 써"라고만 하면 같은 것이 온다.
    """
    if not (question or "").strip():
        return "질문이 비었습니다. 질문 한 문장만 쓰세요."
    strays = kinship.unknown_terms(question)
    if strays:
        return (
            f"'{', '.join(strays)}'는 이 가족에 없습니다. [가족 구성원]에 있는 사람만 쓰세요."
        )
    wrong_person = _calls_someone_else(question, subject_name)
    if wrong_person:
        return wrong_person
    if _repeats(question, questions):
        return "그 질문은 이미 했습니다. 아직 묻지 않은 것을 물으세요."
    return None


async def _generate_question(
    context: str,
    questions: list[str],
    answers: list[str],
    subject_name: Optional[str] = None,
    age_rule: Optional[str] = None,
    prior: list[str] | tuple = (),
    age: Optional[int] = None,
) -> str:
    """EXAONE으로 인터뷰 질문 생성

    낸 질문을 한 번 검사한다. 없는 사람을 부르거나 이미 한 질문이면 한 번 더
    청하고, 그래도 같으면 그 문장은 쓰지 않는다 — 화면에 나가면 답하는 사람이
    없는 사람을 떠올리려 애쓰거나 같은 것을 두 번 답하게 된다.
    """
    messages = _question_messages(
        context, questions, answers, subject_name, age_rule=age_rule, prior=prior
    )
    # 이번 세션에서 물은 것과 예전 세션에서 물은 것을 함께 놓고 검사한다.
    asked = list(questions) + list(prior)
    fallback = dict(subject_name=subject_name, age=age)

    raw = await llm_client.complete(messages, max_tokens=256)
    question = _clean_question(raw)

    problem = _problem_with(question, asked, subject_name)
    if not problem:
        return question

    # 무엇이 잘못됐는지 적어 돌려준다. 되돌려 주는 것은 청소 전 원본이다 —
    # 모델이 자기가 쓴 것을 봐야 다른 것을 쓴다.
    retry = messages + [
        {"role": "assistant", "content": raw or ""},
        {"role": "user", "content": f"{problem} 질문 한 문장만, 다른 말 없이 쓰세요."},
    ]
    question = _clean_question(await llm_client.complete(retry, max_tokens=256))
    if _problem_with(question, asked, subject_name):
        return _simulate_question(context, answers, asked, **fallback)
    return question


# 모델을 못 쓸 때 쓰는 질문. 나이대별로 갈라 둔다 — 하나뿐이던 동안 두 살이던
# 사람에게도 "그때의 기분은 어땠나요?"가 나갔고, 그것이 이 폴백의 첫 질문이었다.
_HEARSAY_POOL = (
    "이날 이야기를 가족에게 들어 본 적 있으세요? 어떤 이야기였나요?",
    "이 사진을 지금 보면 가장 먼저 눈에 들어오는 것이 무엇인가요?",
    "이 무렵 이야기 중에 가족들이 자주 하는 이야기가 있나요?",
    "사진 속 사람들의 모습에서 지금과 달라 보이는 것이 있나요?",
    "이 사진을 남겨 준 사람에게 지금 묻고 싶은 것이 있나요?",
)

_CHILD_POOL = (
    "그날 누구와 무엇을 하고 놀았는지 기억나세요?",
    "그때 보이거나 들렸던 것 중에 아직 생각나는 것이 있나요?",
    "그날 먹은 것 중에 기억나는 게 있나요?",
    "그때 제일 재미있었던 일은 무엇이었나요?",
    "그날 어디를 돌아다녔는지 기억나세요?",
)

_ADULT_POOL = (
    "이 사진이 찍힌 날, 어떤 일이 있었는지 기억나세요?",
    "그때 함께 있었던 가족이 누구였나요? 특별히 기억나는 순간이 있나요?",
    "이 장소에서의 추억 중 가장 먼저 떠오르는 것은 무엇인가요?",
    "그날의 날씨나 분위기가 기억나시나요?",
    "이 사진을 보면 어떤 감정이 떠오르나요? 그때의 기분은 어땠나요?",
)


def _fallback_pool(age: Optional[int]) -> tuple[str, ...]:
    """그 나이에 답할 수 있는 폴백 질문 목록"""
    if age is None:
        return _ADULT_POOL
    if age <= 3:
        return _HEARSAY_POOL
    if age <= 12:
        return _CHILD_POOL
    return _ADULT_POOL


def _simulate_question(
    context: str,
    previous_answers: list[str],
    asked: list[str] | tuple = (),
    subject_name: Optional[str] = None,
    age: Optional[int] = None,
) -> str:
    """EXAONE 없을 때 시뮬레이션 질문 (이미 한 것은 건너뛴다)

    모델이 없어도 누구에게 묻는지는 안다. 나이대로 묶음을 고르고 이름을 붙인다 —
    이 경로가 전원에게 같은 문장을 내던 동안, 키가 없는 환경에서는 사용자별
    차별화가 아예 없었다.
    """
    question_pool = list(_fallback_pool(age))

    def _address(text: str) -> str:
        return f"{subject_name}님, {text}" if subject_name else text

    idx = len(previous_answers) % len(question_pool)
    for offset in range(len(question_pool)):
        candidate = _address(question_pool[(idx + offset) % len(question_pool)])
        if not _repeats(candidate, list(asked)):
            return candidate
    return _address(question_pool[idx])


def _asked_question(session: dict) -> Optional[str]:
    """이번에 받은 답변이 답한 질문 (answers에 담기 전에 부른다)

    지금까지 받은 답이 n개면 이번 답은 n+1번째이고, 그 짝은 questions[n]이다.
    세션이 어긋나 짝이 없으면 짐작하지 않고 비워 둔다 — 엉뚱한 질문을 짝지으면
    기억의 뜻이 바뀐다.
    """
    questions = session.get("questions") or []
    index = len(session.get("answers") or [])
    if 0 <= index < len(questions):
        return questions[index]
    return None


async def _process_answer_to_graph(
    session: dict,
    answer: str,
    speaker_id: Optional[str] = None,
    audio_media_id: Optional[str] = None,
    question: Optional[str] = None,
) -> list[str]:
    """답변을 구조화하여 Graph에 저장

    같은 추억에 대한 가족별 기억을 따로 보존하려면 "누가 말했는지"가 남아야 한다.
    contributor_id와 REMEMBERS 엣지가 없으면 Gap 탐지도 "아직 기억을 남기지
    않은 참여자"를 찾을 수 없다.

    speaker_id는 화면에서 고른 "지금 답하는 사람"이다. Gap이 지목한 인물보다
    우선한다 — 실제로 말한 사람이 누구인지는 화면 앞에 있는 가족만 안다.

    question은 이 답을 부른 질문이다. 짧은 답은 질문 없이는 뜻이 없다.
    """
    updated_nodes = []

    # 화면이 알려준 화자를 먼저 쓰고, 없으면 Gap이 지목한 인물에게 귀속한다
    contributor_id = session.get("contributor_id")
    if speaker_id and graph_manager.get_node(speaker_id):
        contributor_id = speaker_id

    # Memory 노드 생성. 답과 함께 그 답을 부른 질문도 남긴다 — 짧은 답은
    # 질문 없이는 뜻이 없다. "모르겠어요"만 그래프에 남으면 나중에 채팅이
    # 그것을 근거로 잡아도 무엇을 모른다는 것인지 말할 수 없다.
    memory = MemoryNode(
        content=answer,
        question=question,
        source_type=SourceType.INTERVIEW,
        contributor_id=contributor_id,
        confidence=Confidence.CONFIRMED,
    )
    graph_manager.add_memory(memory)
    updated_nodes.append(memory.id)

    # 타겟 이벤트가 있으면 연결
    target = session.get("target_node")
    if target and target.get("node_type") == "event":
        edge = Edge(
            source=memory.id,
            target=target["id"],
            relation=RelationType.ABOUT,
        )
        graph_manager.add_edge(edge)

    # 화자 → 기억 (REMEMBERS)
    if contributor_id and graph_manager.get_node(contributor_id):
        graph_manager.add_edge(Edge(
            source=contributor_id,
            target=memory.id,
            relation=RelationType.REMEMBERS,
        ))

    # 말로 답한 경우 원본 음성을 기억의 근거로 잇는다 (기획안 "출처 보존").
    # 전사문만 남기면 목소리로 되짚을 수 없다.
    if audio_media_id:
        audio = graph_manager.get_node(audio_media_id)
        if audio and audio.get("node_type") == NodeType.MEDIA:
            graph_manager.add_edge(Edge(
                source=memory.id,
                target=audio_media_id,
                relation=RelationType.EVIDENCED_BY,
            ))
            updated_nodes.append(audio_media_id)

    # 답변에서 인물·장소·시점을 뽑아 추억에 잇는다 (그래프가 자라는 자리)
    extracted = await extract_and_link(answer, target, contributor_id, memory.id)
    updated_nodes.extend(extracted["updated_nodes"])
    session.setdefault("extracted", []).append(extracted)

    return updated_nodes


# --- 답변에서 구조 뽑기 -------------------------------------------------------

EXTRACT_SYSTEM = """너는 가족 인터뷰 답변에서 사실 후보만 뽑는 추출기야.
답변에 실제로 나온 표현만 JSON으로 출력해. 설명이나 인사는 하지 마.

출력 형식:
{
  "persons": ["답변에 나온 사람의 이름 또는 호칭"],
  "places": ["지명 또는 장소 이름"],
  "date": "YYYY-MM-DD 또는 YYYY-MM 또는 YYYY, 없으면 null"
}

규칙:
1. 답변에 등장한 표현만 넣어. 추측해서 채우지 마.
2. 조사(은/는/이/가/의/에서/와/과)는 떼고 넣어. "엄마가" -> "엄마"
3. 여러 사람을 뭉뚱그린 표현은 넣지 마. "우리 가족", "다들", "모두" -> 넣지 않는다.
4. 말하는 사람 자신을 가리키는 표현(나, 내가, 저는)은 넣지 마.
5. 장소는 고유한 이름만. "거기", "그곳", "집" 같은 지시어는 넣지 마.
6. 날짜는 답변에 연도나 날짜가 실제로 있을 때만. "그때", "옛날"은 null.
7. JSON만 출력해."""

# "1998년 8월", "1998-08-13", "98년" 같은 표현에서 연도를 건져낸다
_YEAR = re.compile(r"(19|20)\d{2}")


def _clean_terms(value) -> list[str]:
    """LLM이 준 값을 문자열 목록으로 정리한다 (형식 이탈 방어)"""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    terms = []
    for item in value:
        text = str(item).strip()
        if text and text not in terms:
            terms.append(text)
    return terms


def _normalize_date(raw) -> Optional[str]:
    """YYYY / YYYY-MM / YYYY-MM-DD 만 통과시킨다

    추억의 date_start는 화면과 정렬이 ISO 문자열로 다루므로, 형식이 어긋나면
    타임라인이 엉킨다. 확신할 수 없으면 넣지 않는다.
    """
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if re.fullmatch(r"\d{4}", text):
        return text + "-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return text + "-01"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    return None


def _resolve_person(term: str) -> Optional[str]:
    """호칭이나 이름을 그래프의 인물에 맞춘다 (없으면 None)

    새 인물을 만들지 않는다. "큰엄마"가 누구인지는 가족만 알고, AI가 정하면
    잘못된 귀속이 그래프에 박힌다 (기획안 08장 Identity Safety).
    """
    persons = graph_manager.get_persons()
    for person in persons:
        if term == person.get("name") or term == person.get("relation"):
            return person["id"]
    for person in persons:
        name = person.get("name") or ""
        relation = person.get("relation") or ""
        if (name and (term in name or name in term)) or (relation and term == relation):
            return person["id"]
    return None


def _resolve_place(term: str) -> Optional[str]:
    """지명을 그래프의 장소에 맞춘다 (없으면 None)"""
    places = graph_manager.get_places()
    for place in places:
        if term == place.get("name"):
            return place["id"]
    for place in places:
        name = place.get("name") or ""
        if name and (term in name or name in term):
            return place["id"]
    return None


def _empty_extraction() -> dict:
    return {
        "persons": [],
        "place": None,
        "date": None,
        "unmatched": [],
        "updated_nodes": [],
        "filled": [],
    }


async def extract_and_link(
    answer: str,
    target: Optional[dict],
    contributor_id: Optional[str],
    memory_id: str,
) -> dict:
    """답변에서 인물·장소·시점을 뽑아 추억에 잇는다"""
    if not llm_client.is_enabled("extract"):
        # 부를 모델이 없으면 추출하지 않는다. 규칙 기반으로 흉내내면 잘못된
        # 연결이 그래프에 남고, 그게 화면에서는 사실처럼 보인다.
        return _empty_extraction()

    raw = await llm_client.complete_json(
        [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": answer},
        ],
        max_tokens=256,
        model=EXAONE_PLANNER_MODEL,
        # 답변에서 인물·장소·날짜만 뽑는 기계적인 일 (config의 LLM_EXTRACT_PROVIDER)
        purpose="extract",
    )
    if not raw:
        return _empty_extraction()

    return link_extracted(raw, target, contributor_id, memory_id)


def link_extracted(
    raw: dict,
    target: Optional[dict],
    contributor_id: Optional[str],
    memory_id: str,
) -> dict:
    """뽑아낸 표현을 그래프에 잇는다 (LLM과 분리해 둔다 — 규칙을 시험할 수 있게)

    Returns:
        {"persons": [{id, name, term}], "place": {...}|None, "date": "..."|None,
         "unmatched": ["그래프에 없는 표현"], "updated_nodes": [...],
         "filled": ["date_start", "location_id"]}
    """
    result = _empty_extraction()

    event = target if (target or {}).get("node_type") == NodeType.EVENT else None
    event_id = event["id"] if event else None
    # 추억은 그동안 바뀌었을 수 있다 (세션이 들고 있는 것은 시작 시점의 값)
    current = graph_manager.get_node(event_id) if event_id else None

    # --- 인물: 있는 사람에게만 잇는다 ---
    for term in _clean_terms(raw.get("persons")):
        person_id = _resolve_person(term)
        if not person_id:
            result["unmatched"].append(term)
            continue
        person = graph_manager.get_node(person_id) or {}
        entry = {"id": person_id, "name": person.get("name", person_id), "term": term}
        if entry not in result["persons"]:
            result["persons"].append(entry)

        # 말한 사람 자신은 이미 REMEMBERS로 이어져 있다
        if event_id and person_id != contributor_id:
            graph_manager.add_edge(Edge(
                source=person_id,
                target=event_id,
                relation=RelationType.PARTICIPATED_IN,
                # 추정임을 엣지에 남긴다. 화면이 AI가 채운 값이라고 밝힐 수 있다.
                properties={
                    "role": "참여자",
                    "confidence": Confidence.AI_INFERRED,
                    "source": SourceType.INTERVIEW,
                    "from_memory": memory_id,
                },
            ))
            if person_id not in result["updated_nodes"]:
                result["updated_nodes"].append(person_id)

    # --- 장소: 비어 있을 때만 채운다 ---
    for term in _clean_terms(raw.get("places")):
        place_id = _resolve_place(term)
        if not place_id:
            result["unmatched"].append(term)
            continue
        place = graph_manager.get_node(place_id) or {}
        result["place"] = {"id": place_id, "name": place.get("name", place_id), "term": term}

        if current and not current.get("location_id"):
            graph_manager.update_node(event_id, {
                "location_id": place_id,
                "confidence": Confidence.AI_INFERRED,
            })
            graph_manager.add_edge(Edge(
                source=event_id,
                target=place_id,
                relation=RelationType.LOCATED_AT,
                properties={
                    "confidence": Confidence.AI_INFERRED,
                    "source": SourceType.INTERVIEW,
                },
            ))
            result["filled"].append("location_id")
            if event_id not in result["updated_nodes"]:
                result["updated_nodes"].append(event_id)
        break  # 추억의 대표 장소는 하나다

    # --- 시점: 비어 있을 때만 채운다 ---
    date = _normalize_date(raw.get("date"))
    if date:
        result["date"] = date
        if current and not current.get("date_start"):
            graph_manager.update_node(event_id, {
                "date_start": date,
                "confidence": Confidence.AI_INFERRED,
            })
            result["filled"].append("date_start")
            if event_id not in result["updated_nodes"]:
                result["updated_nodes"].append(event_id)

    return result
