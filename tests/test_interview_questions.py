"""AI 인터뷰가 누구에게 무엇을 묻는지 회귀 테스트

    python tests/test_interview_questions.py

화면에서 실제로 이런 일이 있었다 (아빠 김민수로 로그인한 채로):

  AI : "서연님, 1998년 8월 부산 여행이 정말 특별했던 것 같네요."
  AI : "형이나 엄마와 함께했던 특별한 순간 말이에요."
  나 : "모르겠어요"  →  AI가 같은 질문을 다시 냈다

세 가지가 어긋나 있었다.
  1. 질문받는 사람이 답하는 사람과 달랐다 (question_picker가 다른 참여자를 골랐다)
  2. 가족에 없는 사람을 지어냈다 (형 — 이 가족의 자식은 남매 둘뿐이다)
  3. 무엇을 물었는지 모델에게 주지 않아 같은 질문을 되풀이했다

LLM은 부르지 않는다. 대상 고르기(규칙), 프롬프트 만들기(규칙), 호칭 검사(규칙)만
시험한다 — 그 셋이 위 세 가지가 갈리는 자리다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import interview_engine, kinship  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402
from backend.services.question_picker import (  # noqa: E402
    forget_asked,
    pick_target,
    remember_asked,
)

FATHER = "P01"  # 김민수 (아빠, 1970)
MOTHER = "P02"  # 박서연 (엄마, 1973)
DAUGHTER = "P03"  # 김하늘 (딸, 1996)
SON = "P04"  # 김지우 (아들, 2000)


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


# --- 누구에게 묻는가 ---------------------------------------------------------


def test_target_is_the_person_who_answers():
    """답할 사람을 넘기면 인터뷰 대상이 그 사람이다"""
    _require_seeded_graph()

    for speaker in (FATHER, MOTHER, DAUGHTER):
        target = pick_target(speaker_id=speaker)
        assert target["person_id"] == speaker, (speaker, target["person_id"])
        name = graph_manager.get_node(speaker)["name"]
        assert target["person_name"] == name, target["person_name"]
    print("  인터뷰 대상 = 답하는 사람 OK")


def test_target_event_includes_the_speaker():
    """물어보는 사건은 그 사람이 함께 있었던 사건이다

    없던 자리를 물으면 남는 것은 기억이 아니라 추측이다.
    """
    _require_seeded_graph()

    for speaker in (FATHER, MOTHER, DAUGHTER, SON):
        target = pick_target(speaker_id=speaker)
        event = target["event"]
        assert event, f"{speaker}에게 물어볼 사건을 못 골랐다"
        participants = {
            n["id"]
            for n in graph_manager.get_connected_nodes(event["id"])
            if n.get("node_type") == "person"
        }
        assert speaker in participants, (speaker, event["id"], participants)
    print("  참여한 사건에서만 고름 OK")


def test_repeated_starts_ask_about_different_events():
    """연달아 시작하면 다른 사건을 묻는다

    화면에서 이런 일이 있었다: "인터뷰 시작하기"를 누를 때마다 1998 부산
    가족여행이 다시 나왔다. 시드된 그래프는 여덟 사건 모두 날짜·장소·설명·사진이
    채워져 있어 점수가 같고, 같으면 목록의 첫 사건이 늘 이겼다. 시작만 하고
    그만두면 그래프도 그대로여서 다음 계산이 같은 답을 냈다.
    """
    _require_seeded_graph()

    forget_asked()
    try:
        picked = []
        for _ in range(3):
            event = pick_target(speaker_id=DAUGHTER)["event"]
            assert event, "물어볼 사건을 못 골랐다"
            picked.append(event["id"])
            # 답하지 않고 다시 시작한 경우다 — 그래프는 그대로다
            remember_asked(DAUGHTER, event["id"])

        assert len(set(picked)) == 3, picked
    finally:
        forget_asked()
    print("  연속 시작 시 사건 회전 OK:", " → ".join(picked))


def test_unknown_speaker_falls_back_to_gap():
    """없는 사람 id가 와도 인터뷰는 시작된다 (예전 동작으로 돌아간다)"""
    _require_seeded_graph()

    target = pick_target(speaker_id="P99")
    assert target["event"], "폴백에서 사건을 못 골랐다"
    print("  없는 화자 폴백 OK:", target["person_name"])


def test_context_names_only_the_answering_person():
    """컨텍스트가 다른 사람을 인터뷰 대상으로 세우지 않는다"""
    _require_seeded_graph()

    father = graph_manager.get_node(FATHER)
    event = pick_target(speaker_id=FATHER)["event"]
    context = interview_engine._build_interview_context(event, father)

    assert "[인터뷰 대상] 김민수" in context, context
    assert "[인터뷰 대상] 박서연" not in context
    # 명단은 그대로 들어간다. 참여자로서의 박서연은 있어야 한다.
    assert "[가족 구성원]" in context and "박서연" in context
    assert "← 지금 답하는 사람" in context
    print("  컨텍스트 대상 OK")


# --- 없는 사람을 만들지 않는가 -----------------------------------------------


def test_family_roster_lists_members_and_relations():
    """명단과 서로의 관계가 프롬프트에 들어간다"""
    _require_seeded_graph()

    roster = interview_engine._family_roster(graph_manager.get_node(FATHER))
    for name in ("김민수", "박서연", "김하늘", "김지우", "이정자"):
        assert name in roster, name
    assert "남매" in roster, roster  # 김하늘 — 김지우
    print("  가족 명단 OK")


def test_absent_kin_terms_are_caught():
    """이 가족에 없는 호칭을 잡아낸다 (형·삼촌 — 실제로 나온 말이다)"""
    _require_seeded_graph()

    assert kinship.unknown_terms("형이나 엄마와 함께했던 순간이 있으세요?") == ["형"]
    assert kinship.unknown_terms("삼촌도 그 자리에 계셨나요?") == ["삼촌"]
    assert "오빠" in kinship.unknown_terms("오빠랑 뭘 하고 놀았어요?")
    print("  없는 호칭 검출 OK")


def test_real_kin_terms_pass():
    """있는 사람은 통과시킨다 — 막으면 맞는 질문까지 버린다"""
    _require_seeded_graph()

    for text in (
        "엄마와 함께 간 곳이 어디였나요?",
        "아버지가 캠코더로 무엇을 찍으셨나요?",
        "딸과 아들이 물놀이를 했나요?",
        "누나와 무엇을 하고 놀았는지 기억나세요?",  # 김하늘(1996)이 김지우의 누나다
        "남동생과 함께 찍은 사진이 있나요?",
        "할머니는 그때 어디 계셨나요?",
        "아내와 단둘이 보낸 시간도 있었나요?",  # 부부 관계가 그래프에 있다
    ):
        assert kinship.unknown_terms(text) == [], (text, kinship.unknown_terms(text))
    print("  있는 호칭 통과 OK")


def test_kin_check_does_not_match_inside_words():
    """낱말 안에 든 글자를 호칭으로 읽지 않는다 (인형의 형은 형이 아니다)"""
    _require_seeded_graph()

    for text in (
        "인형을 안고 찍은 사진이 있나요?",
        "그날의 상황이 어땠는지 기억나세요?",
        "형태가 어떤 건물이었나요?",
    ):
        assert kinship.unknown_terms(text) == [], (text, kinship.unknown_terms(text))
    print("  낱말 안 오검출 없음 OK")


# --- 같은 질문을 다시 묻지 않는가 --------------------------------------------


def test_prompt_carries_previous_questions():
    """이전 질문이 프롬프트에 들어간다 (이것이 없어서 같은 질문이 반복됐다)"""
    questions = ["부산에서 가장 기억에 남는 장소가 있으세요?", "해수욕장에서 무엇을 하셨나요?"]
    answers = ["내가 뛰어노는 순간들", "해수욕장과 호텔 수영장"]

    messages = interview_engine._question_messages("[주제] 1998 부산", questions, answers, "김민수")
    prompt = messages[-1]["content"]

    for question in questions:
        assert question in prompt, question
    for answer in answers:
        assert answer in prompt, answer
    assert "이미 나온 질문을 다시 하지 마세요" in prompt
    assert "김민수님에게 직접" in prompt
    print("  이전 질문 전달 OK")


def test_unknown_answer_switches_topic():
    """모른다는 답에는 주제를 바꾸라고 지시한다"""
    for answer in ("모르겠어요", "잘 기억이 안 나요", "그건 기억이 없어요", "글쎄요"):
        messages = interview_engine._question_messages("[주제] 1998 부산", ["Q"], [answer], "김민수")
        prompt = messages[-1]["content"]
        assert "다른 주제로 넘어가세요" in prompt, answer
    print("  모른다는 답 → 주제 전환 OK")


def test_answered_question_does_not_switch_topic():
    """실제로 답한 경우에는 주제를 바꾸라고 하지 않는다"""
    messages = interview_engine._question_messages(
        "[주제] 1998 부산", ["Q"], ["해수욕장과 호텔 수영장"], "김민수"
    )
    assert "다른 주제로 넘어가세요" not in messages[-1]["content"]
    print("  답한 경우 주제 유지 OK")


def test_same_question_is_rejected():
    """같은 질문을 다시 낸 경우 그대로 내보내지 않는다"""
    asked = ["그때 부산에서 가장 기억에 남는 장소가 있으신가요?"]

    same = "그때 부산에서 가장 기억에 남는 장소가 있으신가요?"
    spaced = "그때 부산에서 가장 기억에 남는 장소가 있으신가요?\n"
    assert interview_engine._problem_with(same, asked), "같은 질문을 통과시켰다"
    assert interview_engine._problem_with(spaced, asked), "공백만 다른 질문을 통과시켰다"

    # 말을 바꾼 후속 질문은 막지 않는다 — 막으면 대화가 못 이어진다
    followup = "그 해수욕장에서 누구와 함께 계셨나요?"
    assert interview_engine._problem_with(followup, asked) is None
    print("  같은 질문 거절 OK")


def test_fallback_question_skips_asked_ones():
    """모델을 못 쓸 때도 이미 한 질문을 다시 내지 않는다"""
    pool_first = interview_engine._simulate_question("ctx", [])
    other = interview_engine._simulate_question("ctx", [], [pool_first])
    assert other != pool_first, other
    print("  폴백 질문 중복 회피 OK")


TESTS = [
    test_target_is_the_person_who_answers,
    test_target_event_includes_the_speaker,
    test_repeated_starts_ask_about_different_events,
    test_unknown_speaker_falls_back_to_gap,
    test_context_names_only_the_answering_person,
    test_family_roster_lists_members_and_relations,
    test_absent_kin_terms_are_caught,
    test_real_kin_terms_pass,
    test_kin_check_does_not_match_inside_words,
    test_prompt_carries_previous_questions,
    test_unknown_answer_switches_topic,
    test_answered_question_does_not_switch_topic,
    test_same_question_is_rejected,
    test_fallback_question_skips_asked_ones,
]


if __name__ == "__main__":
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {test.__name__}: {type(e).__name__} {e}")

    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} 통과")
    sys.exit(1 if failures else 0)
