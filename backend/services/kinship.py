"""가족에 없는 호칭을 걸러낸다 (AI 인터뷰가 문장을 내보내기 전의 마지막 문턱)

인터뷰가 실제로 이런 질문을 냈다:

    "물속에서 뭔가 재미있는 일이 있었거나, 아니면 형이나 엄마와 함께했던
     특별한 순간 말이에요."

이 가족에 형은 없다. 자식은 딸(1996년생)과 아들(2000년생) 남매뿐이고, 아무도
형이라고 부를 사람이 없다. 모델이 남자 형제를 지어냈고 그것이 질문으로 나갔다.
없는 사람을 부르는 질문은 답할 수 없을 뿐 아니라, 답하면 그 사람이 기억으로
그래프에 들어온다.

프롬프트에 "만들지 마라"고 적는 것만으로는 막히지 않는다 (적어 두었다). 그래서
생성된 문장을 그래프의 가족 구성원에서 나온 호칭 집합과 대조한다. 규칙은 둘이다.

  1. **아는 말만 검사한다.** 어휘 목록(KIN_TERMS)에 없는 말은 통과시킨다.
     모르는 말까지 막으면 정상적인 질문이 버려진다.
  2. **확실할 때만 허용한다.** 할머니가 있어도 "외할머니"는 허용하지 않는다.
     친가·외가는 이 데이터가 모르는 사실이다. 형·누나의 위아래도 생년으로
     정해질 때만 허용한다.

호칭을 고쳐 주지는 않는다. 여기서 하는 일은 "이 말은 이 가족에 없다"고
알리는 것까지고, 무엇을 할지는 부르는 쪽이 정한다 (interview_engine).
"""

from __future__ import annotations

import re
from typing import Optional

from backend.models.graph_models import NodeType, RelationType
from backend.services.graph_manager import graph_manager


# 검사할 어휘. 여기 없는 말은 검사하지 않는다 (규칙 1).
KIN_TERMS: tuple[str, ...] = (
    "아버지", "아빠", "어머니", "엄마",
    "할아버지", "할머니", "외할아버지", "외할머니",
    "아들", "딸", "손자", "손녀",
    "남편", "아내", "부인", "와이프", "신랑", "남자친구", "여자친구",
    "형", "형님", "누나", "누님", "오빠", "언니",
    "형제", "자매", "남매", "동생", "남동생", "여동생",
    "삼촌", "외삼촌", "이모", "고모", "큰아빠", "작은아빠", "큰엄마", "작은엄마",
    "사촌", "조카", "매형", "형수", "처남", "시누이",
    "장인", "장모", "시아버지", "시어머니", "며느리", "사위",
)

# 같은 사람을 가리키는 말. 관계가 "아빠"로 적혀 있으면 "아버지"도 그 사람이다.
_SAME_PERSON = {
    "아빠": {"아빠", "아버지"},
    "아버지": {"아빠", "아버지"},
    "엄마": {"엄마", "어머니"},
    "어머니": {"엄마", "어머니"},
    "남편": {"남편", "신랑"},
    "아내": {"아내", "부인", "와이프"},
}

# 관계 이름에서 읽는 성별. 인물 노드에 성별 필드는 없다 — 있는 것으로 판단한다.
_MALE = {"아빠", "아버지", "아들", "할아버지", "형", "오빠", "남편", "손자", "삼촌"}
_FEMALE = {"엄마", "어머니", "딸", "할머니", "누나", "언니", "아내", "손녀", "이모"}

# 형제자매 관계를 뜻하는 엣지 이름 (properties.relation_type)
_SIBLING_LABELS = {"남매", "형제", "자매"}

# 배우자 관계를 뜻하는 엣지 이름
_SPOUSE_LABELS = {"부부"}
_SPOUSE_TERMS = {"남편", "신랑", "아내", "부인", "와이프"}

# 조사·호칭 접미. 한국어는 낱말 사이에 띄어쓰기가 없을 수 있어서, 뒤에 붙는 말을
# 여기서 허용해 주지 않으면 "형이랑"을 찾지 못한다.
_SUFFIX = (
    "님|씨|이랑|하고|에게|한테|께서|께|이나|이야|이었|였|처럼|보다|까지|부터|만|도|의"
    "|이|가|은|는|을|를|와|과|랑|나"
)


def _gender(person: dict) -> Optional[str]:
    relation = (person or {}).get("relation") or ""
    if relation in _MALE:
        return "male"
    if relation in _FEMALE:
        return "female"
    return None


def person_relation_edges() -> list[tuple[dict, dict, str]]:
    """사람 사이의 관계 엣지 (a, b, 관계이름)"""
    pairs = []
    for edge in graph_manager.get_all_edges():
        if edge.get("relation") != RelationType.RELATED_TO:
            continue
        a = graph_manager.get_node(edge.get("source", ""))
        b = graph_manager.get_node(edge.get("target", ""))
        if not a or not b:
            continue
        if a.get("node_type") != NodeType.PERSON or b.get("node_type") != NodeType.PERSON:
            continue
        label = (edge.get("properties") or {}).get("relation_type") or ""
        pairs.append((a, b, label))
    return pairs


def sibling_terms(a: dict, b: dict) -> set[str]:
    """형제자매 두 사람 사이에 실제로 쓸 수 있는 호칭

    위아래는 생년에서, 성별은 관계 이름에서 나온다. 부르는 쪽의 성별까지는
    보지 않으므로 형·오빠를 함께 허용한다 — 여기서 막으려는 것은 형이라고
    부를 사람이 아예 없는 경우다.
    """
    years = (a.get("birth_year"), b.get("birth_year"))
    if None in years or years[0] == years[1]:
        # 위아래를 정할 수 없다. 형제자매 호칭을 모두 열어 둔다 —
        # 확실하지 않을 때 막으면 맞는 질문까지 버린다.
        return {"형", "오빠", "누나", "언니", "동생", "남동생", "여동생"}

    older, younger = (a, b) if (years[0] or 0) < (years[1] or 0) else (b, a)
    terms = {"동생"}

    older_gender = _gender(older)
    if older_gender == "male":
        terms |= {"형", "오빠"}
    elif older_gender == "female":
        terms |= {"누나", "언니"}
    else:
        terms |= {"형", "오빠", "누나", "언니"}

    younger_gender = _gender(younger)
    if younger_gender == "male":
        terms.add("남동생")
    elif younger_gender == "female":
        terms.add("여동생")
    else:
        terms |= {"남동생", "여동생"}

    return terms


def known_terms() -> set[str]:
    """이 가족에서 실제로 부를 수 있는 호칭

    비어 있으면(구성원이 아직 없으면) 검사하지 않는다는 뜻이다.
    """
    persons = graph_manager.get_persons()
    if not persons:
        return set()

    terms: set[str] = set()
    for person in persons:
        relation = (person.get("relation") or "").strip()
        if not relation:
            continue
        terms |= _SAME_PERSON.get(relation, {relation})

    for a, b, label in person_relation_edges():
        if label:
            terms.add(label)
        if label in _SIBLING_LABELS:
            terms |= sibling_terms(a, b)
        if label in _SPOUSE_LABELS:
            terms |= _SPOUSE_TERMS

    return terms


def _word_spans(term: str, text: str) -> list[tuple[int, int]]:
    """text에서 term이 낱말로 쓰인 자리

    "인형을 안고"의 형은 형이 아니다. 앞뒤가 한글로 이어지면 낱말이 아니라고
    본다 (뒤에는 조사만 허용한다).
    """
    pattern = rf"(?<![가-힣]){re.escape(term)}(?:{_SUFFIX})?(?![가-힣])"
    return [(m.start(), m.start() + len(term)) for m in re.finditer(pattern, text)]


def mentions(term: str, text: str) -> bool:
    """text가 term을 낱말로 부르고 있는가"""
    return bool(_word_spans(term, text))


def unknown_terms(text: str) -> list[str]:
    """text에서 이 가족에 없는 호칭을 찾는다 (긴 말부터, 중복 없이)

    긴 말을 먼저 본다. "큰아빠"가 없으면 큰아빠만 돌려준다 — 그 안의 "아빠"는
    있는 사람이고, 두 번 세면 무엇이 문제인지 흐려진다.
    """
    if not text:
        return []
    known = known_terms()
    if not known:
        # 구성원을 모르는 상태에서 막으면 인터뷰가 아무 질문도 못 한다
        return []

    found: list[str] = []
    covered: list[tuple[int, int]] = []
    for term in sorted(KIN_TERMS, key=len, reverse=True):
        spans = [
            span for span in _word_spans(term, text)
            if not any(start <= span[0] < end for start, end in covered)
        ]
        if not spans:
            continue
        covered.extend(spans)
        if term not in known:
            found.append(term)

    return found
