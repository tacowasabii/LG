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


# --- 같은 사건이어도 사람마다 다르게 묻는가 -----------------------------------


def test_age_at_event_is_counted_per_person():
    """사건 당시 나이를 사람마다 따로 센다"""
    _require_seeded_graph()

    busan = graph_manager.get_node("E01")  # 1998-08-13
    ages = {
        pid: interview_engine._age_at(graph_manager.get_node(pid), busan)
        for pid in (FATHER, MOTHER, DAUGHTER, SON)
    }
    assert ages[FATHER] == 28, ages
    assert ages[MOTHER] == 25, ages
    assert ages[DAUGHTER] == 2, ages
    assert ages[SON] == -2, ages  # 2000년생 — 이 여행 뒤에 태어난다
    print("  사건 당시 나이 OK:", ages)


def test_toddler_and_adult_get_different_instructions():
    """두 살과 스물여덟 살에게 물을 것이 다르다

    1998년 부산 여행은 김하늘(1996년생)이 참여자로 걸려 있어 auto가 그를 고른다.
    그때 두 살이다. 나이를 모르는 프롬프트는 두 살에게 그날의 심정을 물었다 —
    답할 수 없고, 답하면 남는 것은 기억이 아니다.
    """
    _require_seeded_graph()

    busan = graph_manager.get_node("E01")
    toddler = interview_engine._age_rule(graph_manager.get_node(DAUGHTER), busan)
    adult = interview_engine._age_rule(graph_manager.get_node(FATHER), busan)

    assert toddler and adult and toddler != adult
    assert "기억나냐고 묻지 않는다" in toddler, toddler
    assert "들은 이야기" in toddler, toddler
    assert "어른이었다" in adult, adult
    print("  나이별 지시 갈림 OK")


def test_context_states_the_age_at_that_time():
    """컨텍스트가 그때 몇 살이었는지 말한다"""
    _require_seeded_graph()

    busan = graph_manager.get_node("E01")
    father = interview_engine._build_interview_context(busan, graph_manager.get_node(FATHER))
    daughter = interview_engine._build_interview_context(busan, graph_manager.get_node(DAUGHTER))

    assert "그때 28살" in father, father
    assert "그때 2살" in daughter, daughter
    # 참여자 줄도 그때 나이로 적힌다 — 이름만 주면 모델이 지금 나이로 읽는다
    assert "김하늘(2살)" in father, father
    print("  컨텍스트 나이 표기 OK")


def test_unborn_family_member_is_kept_out():
    """그때 태어나지 않은 사람을 그 자리에 세우지 않게 알려 준다

    "있는 사람만 언급한다"로는 막히지 않는다 — 김지우는 이 가족에 있는 사람이다.
    """
    _require_seeded_graph()

    busan = graph_manager.get_node("E01")
    father = interview_engine._build_interview_context(busan, graph_manager.get_node(FATHER))
    assert "그때 아직 태어나지 않은 사람: 김지우" in father, father

    # 대상 본인은 그 목록에 넣지 않는다 (앞의 [그때 이 사람]과 어긋난다)
    son = interview_engine._build_interview_context(busan, graph_manager.get_node(SON))
    assert "태어나지 않은 사람" not in son, son
    assert "2년 뒤에 태어난다" in son, son
    print("  태어나기 전 처리 OK")


def test_address_terms_have_a_direction():
    """호칭에 방향이 있다 (김지우에게 김하늘은 누나다 — 형이 아니다)"""
    _require_seeded_graph()

    father = graph_manager.get_node(FATHER)
    mother = graph_manager.get_node(MOTHER)
    daughter = graph_manager.get_node(DAUGHTER)
    son = graph_manager.get_node(SON)

    assert kinship.address_term(son, daughter) == "누나"
    assert kinship.address_term(daughter, son) == "남동생"
    assert kinship.address_term(daughter, father) == "아빠"
    assert kinship.address_term(son, mother) == "엄마"
    assert kinship.address_term(father, mother) == "아내"
    assert kinship.address_term(mother, father) == "남편"
    # 부모는 자식을 "딸"이라고 부르지 않는다 — 이름으로 부른다
    assert kinship.address_term(father, daughter) is None
    print("  방향 있는 호칭 OK")


def test_roster_carries_the_viewpoint_terms():
    """명단이 그 사람 시점의 호칭을 함께 준다"""
    _require_seeded_graph()

    son = interview_engine._family_roster(graph_manager.get_node(SON))
    assert "누나" in son, son
    assert "아빠" in son, son

    daughter = interview_engine._family_roster(graph_manager.get_node(DAUGHTER))
    assert "남동생" in daughter, daughter
    assert "누나" not in daughter, daughter  # 김하늘에게 누나는 없다
    print("  시점 호칭 명단 OK")


def test_own_memories_and_others_memories_are_separated():
    """본인이 남긴 기억과 다른 가족이 남긴 기억을 갈라서 준다

    섞어서 주면 지시가 하나뿐이다 ("다시 묻지 않는다"). 그러면 남만 말한 장면도
    피해야 할 것이 되는데, 그것을 이 사람 시점에서 묻는 것은 겹치는 것이 아니라
    관점이 하나 늘어나는 일이다.
    """
    _require_seeded_graph()

    busan = graph_manager.get_node("E01")  # 기록된 기억이 둘 다 김민수의 것이다

    father = interview_engine._build_interview_context(busan, graph_manager.get_node(FATHER))
    assert "김민수님이 이 사건에 이미 남긴 기억" in father, father
    assert "다른 가족이 남긴 기억" not in father, father

    mother = interview_engine._build_interview_context(busan, graph_manager.get_node(MOTHER))
    assert "다른 가족이 남긴 기억" in mother, mother
    assert "박서연님이 본 것을 새로 물어도 좋다" in mother, mother
    assert "박서연님이 이 사건에 이미 남긴 기억" not in mother, mother
    print("  기억 분리 OK")


def test_age_rule_reaches_the_prompt_rules():
    """나이 규칙이 규칙 목록에 들어간다 (컨텍스트 안쪽에만 두면 뒤에서 잊혔다)"""
    messages = interview_engine._question_messages(
        "[주제] 1998 부산", [], [], "김하늘", age_rule="김하늘님은 그때 두 살이었다."
    )
    assert "김하늘님은 그때 두 살이었다." in messages[-1]["content"]
    print("  나이 규칙 전달 OK")


def test_prior_questions_reach_the_prompt_without_breaking_pairs():
    """예전 세션의 질문을 주되, 이번 대화의 질문·답 짝은 어긋나지 않는다"""
    messages = interview_engine._question_messages(
        "[주제] 1998 부산",
        ["이번에 물은 것"],
        ["이번에 답한 것"],
        "김민수",
        prior=["예전에 물은 것"],
    )
    prompt = messages[-1]["content"]

    assert "예전 인터뷰에서 이미 물은 것" in prompt, prompt
    assert "예전에 물은 것" in prompt, prompt
    # 짝짓기는 questions/answers만으로 센다 — prior가 끼면 질문과 답이 어긋난다
    assert "Q1. 이번에 물은 것" in prompt, prompt
    assert "A1. 이번에 답한 것" in prompt, prompt
    assert "Q2." not in prompt, prompt
    print("  예전 질문 전달 + 짝 유지 OK")


def test_asked_questions_are_remembered_per_person():
    """물어본 질문을 사람별로 따로 적어 둔다

    아빠에게 물은 것이 딸의 차례를 밀어낼 이유가 없다.
    """
    interview_engine.forget_questions()
    try:
        interview_engine._remember_question(FATHER, "캠코더는 어디서 사셨어요?")
        assert interview_engine._prior_questions(FATHER) == ["캠코더는 어디서 사셨어요?"]
        assert interview_engine._prior_questions(DAUGHTER) == []

        # 같은 질문을 두 번 적어도 하나로 남는다
        interview_engine._remember_question(FATHER, "캠코더는 어디서 사셨어요?")
        assert len(interview_engine._prior_questions(FATHER)) == 1

        # 무한히 쌓지 않는다 — 프롬프트가 질문 목록으로 채워진다
        for i in range(30):
            interview_engine._remember_question(FATHER, f"질문 {i}")
        assert len(interview_engine._prior_questions(FATHER)) == interview_engine._ASKED_KEEP
    finally:
        interview_engine.forget_questions()
    print("  사람별 질문 이력 OK")


def test_fallback_questions_also_differ_by_person():
    """모델을 못 쓸 때도 사람마다 다른 질문이 나온다

    이 경로가 전원에게 같은 문장을 내던 동안, 키가 없는 환경에서는 차별화가
    아예 없었다. 그 풀의 첫 질문이 "그때의 기분은 어땠나요?"였다 — 두 살에게도.
    """
    toddler = interview_engine._simulate_question("ctx", [], age=2)
    child = interview_engine._simulate_question("ctx", [], age=8)
    adult = interview_engine._simulate_question("ctx", [], age=30)

    assert len({toddler, child, adult}) == 3, (toddler, child, adult)
    assert "기분" not in toddler, toddler
    assert "들어 본 적" in toddler, toddler

    named = interview_engine._simulate_question("ctx", [], subject_name="김민수", age=30)
    assert named.startswith("김민수님, "), named
    print("  폴백 개인화 OK")


def test_media_target_also_knows_the_age():
    """사진을 타겟으로 시작한 인터뷰도 그때 나이를 안다

    날짜가 사건은 date_start, 미디어는 exif_date에 있다. 사건만 보면
    target_type="media"로 시작한 인터뷰는 나이를 모른 채 묻는다.
    """
    _require_seeded_graph()

    photo = {"node_type": "media", "exif_date": "2006-07-23", "original_filename": "jeju.jpg"}
    daughter = graph_manager.get_node(DAUGHTER)  # 1996년생

    assert interview_engine._age_at(daughter, photo) == 10
    context = interview_engine._build_interview_context(photo, daughter)
    assert "그때 10살" in context, context
    assert "아이였다" in context, context
    print("  미디어 타겟 나이 OK")


# --- 프롬프트가 화면으로 새어 나오지 않는가 -----------------------------------


def test_prompt_scaffolding_is_stripped():
    """모델이 프롬프트를 베껴 오면 떼어낸다

    화면에 실제로 이런 것이 나갔다:
      "Q3. 교문 앞에서 사진을 찍고 나면, 가장 먼저 도착한 곳은 어디였나요?"
      "김민수님에게 직접, 존댓말로 묻습니다."

    앞의 것은 [지금까지의 대화]의 "Q1./A1." 번호를, 뒤의 것은 규칙 목록을 베낀
    것이다. 프롬프트에 "베끼지 마라"를 더 적어도 막히지 않는다.
    """
    clean = interview_engine._clean_question

    assert clean("Q3. 교문 앞에서 무엇을 하셨나요?") == "교문 앞에서 무엇을 하셨나요?"
    # 번호표가 겹쳐 오기도 한다
    assert clean("Q3. Q3. 교문 앞에서 무엇을 하셨나요?") == "교문 앞에서 무엇을 하셨나요?"
    assert clean("질문: 그날 날씨가 어땠나요?") == "그날 날씨가 어땠나요?"

    leaked = "- 김민수님에게 직접, 존댓말로 묻습니다.\n- 이미 나온 질문을 다시 하지 마세요.\n그날 날씨가 어땠나요?"
    assert clean(leaked) == "그날 날씨가 어땠나요?"

    assert clean("[인터뷰 대상] 김민수\n그날 날씨가 어땠나요?") == "그날 날씨가 어땠나요?"
    assert clean("```\n그날 날씨가 어땠나요?\n```") == "그날 날씨가 어땠나요?"
    assert clean(None) == ""
    print("  프롬프트 누출 제거 OK")


def test_cleaner_keeps_real_questions_whole():
    """정상 질문은 손대지 않는다 — 넓게 막으면 맞는 질문까지 버린다"""
    clean = interview_engine._clean_question

    for text in (
        "그날 아침 날씨가 어땠나요?",
        # "에게 직접"만으로 재면 이것이 걸린다
        "그때 하늘이에게 직접 말해 주셨나요?",
        "박서연님은 그때 어디 계셨나요?",
        "김민수님, 그날 저녁 외식은 어디서 하셨나요?",
        "그 캠코더로 무엇을 가장 많이 찍으셨는지 기억나세요?",
    ):
        assert clean(text) == text, (text, clean(text))
    print("  정상 질문 보존 OK")


def test_calling_another_family_member_is_rejected():
    """다른 가족을 불러 세운 질문은 내보내지 않는다

    화면에서 이런 일이 있었다: 김민수로 인터뷰하는 중에 질문이 "박서연님께서는"
    으로 시작했다. 답하는 사람은 김민수인데 대답을 박서연에게 청한 것이다.
    """
    _require_seeded_graph()

    for bad in (
        "박서연님께서는 그날 무엇을 하셨나요?",
        "박서연님, 그날 기억나세요?",
        "김하늘님께서는 그때 무엇을 하고 놀았나요?",
    ):
        assert interview_engine._calls_someone_else(bad, "김민수"), bad
        assert interview_engine._problem_with(bad, [], "김민수"), bad

    # 다른 사람을 **가리키는** 것은 정상이다 — 김민수에게 묻는 질문이다
    for ok in (
        "박서연님은 그때 어디 계셨나요?",
        "그날 아내분과 어떤 이야기를 나누셨나요?",
        "김민수님, 그날 저녁 외식은 어디서 하셨나요?",
    ):
        assert interview_engine._calls_someone_else(ok, "김민수") is None, ok
    print("  다른 사람 호출 거절 OK")


def test_empty_question_is_rejected():
    """빈 문장은 내보내지 않는다 (규칙만 베껴 오면 남는 것이 없다)"""
    assert interview_engine._problem_with("", [], "김민수")
    assert interview_engine._problem_with("   ", [], "김민수")
    print("  빈 질문 거절 OK")


def test_switching_speaker_moves_the_question_too():
    """대화 중에 답하는 사람이 바뀌면 질문도 그 사람을 향한다

    화면의 "지금 답하는 사람"은 대화 중에도 바뀐다. 세션은 시작할 때의 사람을
    붙잡고 있었고 답변 귀속만 speaker_id를 따랐다 — 그래서 기억은 김민수에게
    붙는데 질문은 계속 "박서연님께서는"으로 나갔다.
    """
    _require_seeded_graph()

    busan = graph_manager.get_node("E01")
    mother = graph_manager.get_node(MOTHER)
    session = {
        "target_node": busan,
        "context": interview_engine._build_interview_context(busan, mother),
        "contributor_id": MOTHER,
        "contributor_name": mother["name"],
        "age": interview_engine._age_at(mother, busan),
        "age_rule": interview_engine._age_rule(mother, busan),
        "prior": [],
    }

    # 같은 사람이면 아무것도 바꾸지 않는다
    assert interview_engine._retarget_session(session, MOTHER) is False
    assert session["contributor_name"] == "박서연"

    # 없는 사람 id로는 세션을 흔들지 않는다
    assert interview_engine._retarget_session(session, "P99") is False
    assert session["contributor_name"] == "박서연"

    # 딸로 바뀌면 이름·컨텍스트·나이가 함께 따라간다 (박서연 25살 → 김하늘 2살)
    assert interview_engine._retarget_session(session, DAUGHTER) is True
    assert session["contributor_id"] == DAUGHTER
    assert session["contributor_name"] == "김하늘"
    assert session["age"] == 2, session["age"]
    assert "[인터뷰 대상] 김하늘" in session["context"], session["context"]
    assert "[인터뷰 대상] 박서연" not in session["context"]
    assert "기억나냐고 묻지 않는다" in session["age_rule"], session["age_rule"]
    print("  화자 전환 시 질문도 따라감 OK")


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
    test_age_at_event_is_counted_per_person,
    test_toddler_and_adult_get_different_instructions,
    test_context_states_the_age_at_that_time,
    test_unborn_family_member_is_kept_out,
    test_address_terms_have_a_direction,
    test_roster_carries_the_viewpoint_terms,
    test_own_memories_and_others_memories_are_separated,
    test_age_rule_reaches_the_prompt_rules,
    test_prior_questions_reach_the_prompt_without_breaking_pairs,
    test_asked_questions_are_remembered_per_person,
    test_fallback_questions_also_differ_by_person,
    test_media_target_also_knows_the_age,
    test_prompt_scaffolding_is_stripped,
    test_cleaner_keeps_real_questions_whole,
    test_calling_another_family_member_is_rejected,
    test_empty_question_is_rejected,
    test_switching_speaker_moves_the_question_too,
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
