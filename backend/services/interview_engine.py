"""AI Memory Interview Engine - 기억의 빈 곳을 질문하며 새로운 기록 수집

기획안의 마지막 단계(STEP 06 "이어가기")가 여기서 닫힌다. 답변을 문장으로만
쌓으면 그래프는 자라지 않는다. 그래서 답변에서 인물·장소·시점을 뽑아
사건에 잇는다 (기획안 02장 Memory Interview: "답변에서 사건·인물·시점 추출").

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
    - auto: 아직 덜 채워진 사건을 하나 골라 묻는다

    speaker_id  지금 화면 앞에서 답할 사람. 인터뷰 대상은 이 사람이다.

                이 인자가 없던 동안 question_picker가 고른 인물(그 사건에 기억을
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
        # 물어볼 사건을 하나 고른다 (목록을 만들지 않는다 — question_picker)
        target = pick_target(speaker_id=asked_by)
        target_node = target.get("event")
        if not speaker:
            # 누가 답할지 모르는 경우에만 picker가 지목한 인물에게 묻는다
            contributor_id = target.get("person_id")

    # 무엇을 물었는지 남긴다. 시작만 하고 그만둔 경우에도 남겨야 다음에 같은
    # 사건이 다시 나오지 않는다 — 답을 기다리면 그래프가 자라지 않아 auto가
    # 같은 점수를 다시 계산하고, 화면은 부산 여행만 되풀이해 물었다.
    remember_asked(asked_by, (target_node or {}).get("id"))

    subject = speaker or (graph_manager.get_node(contributor_id) if contributor_id else None)
    contributor_name = subject.get("name") if subject else None

    # 타겟 정보 구성
    context = _build_interview_context(target_node, subject)

    # 첫 질문 생성
    first_question = await _generate_question(context, [], [], contributor_name)

    # 세션 저장
    _sessions[session_id] = {
        "target_node": target_node,
        "context": context,
        "contributor_id": contributor_id,
        "contributor_name": contributor_name,
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

    # 답변 저장
    session["answers"].append(answer)

    # 답변에서 정보 추출 → Memory 노드 생성 + 사건에 잇기
    updated_nodes = await _process_answer_to_graph(
        session, answer, speaker_id=speaker_id, audio_media_id=audio_media_id
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
        )
        session["questions"].append(next_question)
        session["question_count"] += 1

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
        mark = " ← 지금 답하는 사람" if subject and person.get("id") == subject.get("id") else ""
        detail = f" · {', '.join(bits)}" if bits else ""
        lines.append(f"- {person.get('name', '')}{detail}{mark}")

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
        lines.append("[주제] 정해진 사건 없이 가족의 기억을 전반적으로 묻는다.")
        return "\n".join(lines)

    node_type = target_node.get("node_type", "")

    if node_type == "event":
        lines.append(f"[주제] {target_node.get('title', '')}")
        lines.append(f"날짜: {target_node.get('date_start', '미상')}")
        lines.append(f"설명: {target_node.get('description', '없음')}")

        # 참여자 정보
        connected = graph_manager.get_connected_nodes(target_node["id"])
        persons = [n for n in connected if n.get("node_type") == "person"]
        if persons:
            lines.append(f"참여자: {', '.join(p.get('name', '') for p in persons)}")

        # 이미 기록된 기억. 누가 남긴 것인지 함께 준다 — 화자를 빼면 모델이
        # 기억의 주인을 뒤바꿔 말한다 (아빠에게 "아버지가 찍으셨다고 하는데"라고
        # 되물은 일이 있었다).
        memories = [n for n in connected if n.get("node_type") == "memory"]
        if memories:
            lines.append("이미 기록된 기억 (같은 것을 다시 묻지 않는다):")
            for m in memories[:3]:
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
) -> list[dict]:
    """질문 생성 프롬프트 (LLM 호출과 분리해 둔다 — 규칙을 시험할 수 있게)"""
    rules = [
        "위 대화에 이미 나온 질문을 다시 하지 마세요. 말만 바꿔 같은 것을 묻는 것도 안 됩니다.",
        "[가족 구성원]에 없는 사람이나 호칭을 만들지 마세요. 확실하지 않으면 이름을 쓰세요.",
        "아직 비어 있는 것(날짜, 장소, 함께 있던 사람, 그때의 장면이나 감정)을 채우는 질문이면 좋습니다.",
    ]
    if subject_name:
        rules.insert(0, f"{subject_name}님에게 직접, 존댓말로 묻습니다.")
    if answers and _NO_MEMORY.search(answers[-1]):
        # 기억나지 않는다는 답이다. 더 캐물으면 답할 수 없는 질문을 반복하게 된다.
        rules.insert(0, '직전 답변은 "기억나지 않는다"는 뜻입니다. 그 질문을 되풀이하지 말고 다른 주제로 넘어가세요.')

    user_content = f"""[인터뷰 대상 정보]
{context}

[지금까지의 대화]
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


def _problem_with(question: str, questions: list[str]) -> Optional[str]:
    """이 질문을 그대로 내보낼 수 없는 이유 (없으면 None)

    모델에게 그대로 돌려줄 문장으로 쓴다. "다시 써"라고만 하면 같은 것이 온다.
    """
    strays = kinship.unknown_terms(question)
    if strays:
        return (
            f"'{', '.join(strays)}'는 이 가족에 없습니다. [가족 구성원]에 있는 사람만 쓰세요."
        )
    if _repeats(question, questions):
        return "그 질문은 이미 했습니다. 아직 묻지 않은 것을 물으세요."
    return None


async def _generate_question(
    context: str,
    questions: list[str],
    answers: list[str],
    subject_name: Optional[str] = None,
) -> str:
    """EXAONE으로 인터뷰 질문 생성

    낸 질문을 한 번 검사한다. 없는 사람을 부르거나 이미 한 질문이면 한 번 더
    청하고, 그래도 같으면 그 문장은 쓰지 않는다 — 화면에 나가면 답하는 사람이
    없는 사람을 떠올리려 애쓰거나 같은 것을 두 번 답하게 된다.
    """
    messages = _question_messages(context, questions, answers, subject_name)

    question = await llm_client.complete(messages, max_tokens=256)
    if question is None:
        return _simulate_question(context, answers, questions)

    problem = _problem_with(question, questions)
    if not problem:
        return question

    retry = messages + [
        {"role": "assistant", "content": question},
        {"role": "user", "content": f"{problem} 질문을 다시 하나만 쓰세요."},
    ]
    question = await llm_client.complete(retry, max_tokens=256)
    if question is None or _problem_with(question, questions):
        return _simulate_question(context, answers, questions)
    return question


def _simulate_question(
    context: str,
    previous_answers: list[str],
    asked: list[str] | tuple = (),
) -> str:
    """EXAONE 없을 때 시뮬레이션 질문 (이미 한 것은 건너뛴다)"""
    question_pool = [
        "이 사진이 찍힌 날, 어떤 일이 있었는지 기억나세요?",
        "그때 함께 있었던 가족이 누구였나요? 특별히 기억나는 순간이 있나요?",
        "이 장소에서의 추억 중 가장 먼저 떠오르는 것은 무엇인가요?",
        "그날의 날씨나 분위기가 기억나시나요?",
        "이 사진을 보면 어떤 감정이 떠오르나요? 그때의 기분은 어땠나요?",
    ]

    idx = len(previous_answers) % len(question_pool)
    for offset in range(len(question_pool)):
        candidate = question_pool[(idx + offset) % len(question_pool)]
        if not _repeats(candidate, list(asked)):
            return candidate
    return question_pool[idx]


async def _process_answer_to_graph(
    session: dict,
    answer: str,
    speaker_id: Optional[str] = None,
    audio_media_id: Optional[str] = None,
) -> list[str]:
    """답변을 구조화하여 Graph에 저장

    같은 사건에 대한 가족별 기억을 따로 보존하려면 "누가 말했는지"가 남아야 한다.
    contributor_id와 REMEMBERS 엣지가 없으면 Gap 탐지도 "아직 기억을 남기지
    않은 참여자"를 찾을 수 없다.

    speaker_id는 화면에서 고른 "지금 답하는 사람"이다. Gap이 지목한 인물보다
    우선한다 — 실제로 말한 사람이 누구인지는 화면 앞에 있는 가족만 안다.
    """
    updated_nodes = []

    # 화면이 알려준 화자를 먼저 쓰고, 없으면 Gap이 지목한 인물에게 귀속한다
    contributor_id = session.get("contributor_id")
    if speaker_id and graph_manager.get_node(speaker_id):
        contributor_id = speaker_id

    # Memory 노드 생성
    memory = MemoryNode(
        content=answer,
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

    # 답변에서 인물·장소·시점을 뽑아 사건에 잇는다 (그래프가 자라는 자리)
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

    사건의 date_start는 화면과 정렬이 ISO 문자열로 다루므로, 형식이 어긋나면
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
    """답변에서 인물·장소·시점을 뽑아 사건에 잇는다"""
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
    # 사건은 그동안 바뀌었을 수 있다 (세션이 들고 있는 것은 시작 시점의 값)
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
        break  # 사건의 대표 장소는 하나다

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
