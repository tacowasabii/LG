"""이어지는 질문과 짧은 답변의 뜻 보존 회귀 테스트

    python tests/test_chat_followup.py

두 가지를 지킨다.

1. 인터뷰 답변은 그 답을 부른 질문과 짝으로 남아야 한다. "모르겠어요"만
   그래프에 남으면 무엇을 모른다는 것인지 사라진다. 실제로 98년 기억을 물었을
   때 "모르겠어요" 기억이 근거로 잡혔고, 화면에는 그 답의 음성까지 떴는데
   무엇에 대한 답인지 어디에도 없었다.

2. 앞 답변에 매달린 질문("뭘 모르겠다는 거야?")은 그 자체로는 검색되지 않는다.
   빈손으로 돌아온 검색 결과를 그대로 모델에 주면, "반드시 [검색 결과]를
   근거로" 라는 규칙과 방금 자기가 한 말 사이에서 답이 엉킨다.

LLM 키가 없어도 통과해야 한다 (chat_graph.run을 대역으로 갈아끼운다).
"""

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import chat_engine, chat_graph  # noqa: E402
from backend.services.chat_engine import (  # noqa: E402
    _format_search_results,
    _is_followup,
    _prepare,
)
from backend.services.interview_engine import _asked_question  # noqa: E402


# --- 1. 짧은 답변은 질문과 짝으로 남는다 -------------------------------------


def test_answer_is_paired_with_the_question_it_answered():
    """N번째 답변에 N번째 질문이 짝지어진다

    지금까지 받은 답이 n개면 이번 답은 n+1번째이고 짝은 questions[n]이다.
    한 칸 어긋나면 기억의 뜻이 바뀐다.
    """
    session = {
        "questions": ["해수욕장에서 뭘 하고 노셨어요?", "그때 누구와 함께 갔어요?"],
        "answers": [],
    }
    assert _asked_question(session) == "해수욕장에서 뭘 하고 노셨어요?"

    session["answers"].append("모르겠어요")
    assert _asked_question(session) == "그때 누구와 함께 갔어요?"


def test_missing_question_is_left_empty_not_guessed():
    """짝을 찾을 수 없으면 비워 둔다 (엉뚱한 질문을 붙이지 않는다)"""
    assert _asked_question({"questions": [], "answers": []}) is None
    assert _asked_question({}) is None
    # 질문보다 답이 많은 어긋난 세션
    assert _asked_question({"questions": ["A"], "answers": ["a"]}) is None


def test_memory_context_carries_its_question():
    """기억 컨텍스트에 그 기억이 답한 질문이 실린다

    이것이 없으면 모델은 "모르겠어요"를 근거로 받고도 무엇을 모른다고 했는지
    말할 수 없다.
    """
    context = _format_search_results([
        {
            "id": "M100",
            "node_type": "memory",
            "content": "모르겠어요",
            "question": "광안리 해수욕장에서 뭘 하고 노셨어요?",
        }
    ])
    assert "모르겠어요" in context, context
    assert "광안리 해수욕장에서 뭘 하고 노셨어요?" in context, (
        f"기억이 답한 질문이 컨텍스트에 없음:\n{context}"
    )


def test_memory_without_question_stays_unchanged():
    """질문이 없는 기억(직접 쓴 기억·시드)은 전과 같은 줄로 남는다"""
    context = _format_search_results([
        {"id": "M001", "node_type": "memory", "content": "그때 캠코더로 찍었지."}
    ])
    assert "[기억] 그때 캠코더로 찍었지." in context, context
    assert "질문" not in context, context


# --- 2. 이어지는 질문은 앞 turn의 근거를 물려받는다 --------------------------


# (설명, 계획 상태, 이어지는 질문인가)
FOLLOWUP_CASES = [
    (
        "가리키는 대상이 없는 질문",
        {"planned_by_llm": True, "plan": {"persons": [], "places": [], "events": [], "year": None}},
        True,
    ),
    (
        "장소를 지목한 질문 (없는 장소여도 스스로 대상이 있다)",
        {"planned_by_llm": True, "plan": {"persons": [], "places": ["런던"], "events": [], "year": None}},
        False,
    ),
    (
        "연도를 지목한 질문",
        {"planned_by_llm": True, "plan": {"persons": [], "places": [], "events": [], "year": "2019"}},
        False,
    ),
    (
        "계획을 모델이 세우지 못한 경우 - 판정하지 않는다",
        {"planned_by_llm": False, "plan": {"persons": [], "places": [], "events": [], "year": None}},
        False,
    ),
]


def test_followup_detection():
    """스스로 가리키는 대상이 없는 질문만 이어지는 질문으로 본다"""
    failures = []
    for note, state, expected in FOLLOWUP_CASES:
        got = _is_followup(state)
        if got != expected:
            failures.append(f"  {note}: {got} (기대 {expected})")
    assert not failures, "이어지는 질문 판정 불일치:\n" + "\n".join(failures)


class _StubPlan:
    """chat_graph.run 대역. LLM 없이 계획·검색 결과를 정해서 넣는다."""

    def __init__(self):
        self.state = {}

    async def __call__(self, query):
        return dict(self.state)


def _with_stub_plan(fn):
    """chat_graph.run을 대역으로 갈아끼우고 fn(stub)을 돌린다"""
    original = chat_graph.run
    stub = _StubPlan()
    chat_graph.run = stub
    try:
        return fn(stub)
    finally:
        chat_graph.run = original


EVIDENCE = [
    {"id": "E01", "node_type": "event", "title": "1998 부산 가족여행", "date_start": "1998-08-13"},
    {
        "id": "M100",
        "node_type": "memory",
        "content": "모르겠어요",
        "question": "광안리 해수욕장에서 뭘 하고 노셨어요?",
    },
]


def test_followup_inherits_the_previous_turn_evidence():
    """"뭘 모르겠다는 거야?"가 앞 turn의 근거를 그대로 받는다"""

    def run(stub):
        conversation_id = "conv-followup"
        chat_engine._conversations.pop(conversation_id, None)
        chat_engine._last_results.pop(conversation_id, None)

        # 1번째 turn - 98년 기억을 물어 근거를 찾는다
        stub.state = {
            "results": list(EVIDENCE),
            "missing_entities": [],
            "planned_by_llm": True,
            "plan": {"persons": [], "places": [], "events": [], "year": "1998"},
        }
        first = asyncio.run(_prepare("98년 기억 알려줘", conversation_id, None))
        assert {n["id"] for n in first["search_results"]} == {"E01", "M100"}

        # 모델이 답했다고 두고 히스토리를 채운다 (_finish가 하는 일)
        chat_engine._finish(
            "98년 기억 알려줘", "1998 부산 가족여행 기록이 있어요.", True, first
        )

        # 2번째 turn - 되묻는 질문. 검색은 빈손으로 돌아온다
        stub.state = {
            "results": [],
            "missing_entities": [],
            "planned_by_llm": True,
            "plan": {"persons": [], "places": [], "events": [], "year": None},
        }
        second = asyncio.run(_prepare("뭘 모르겠다는 거야?", conversation_id, None))

        ids = {n["id"] for n in second["search_results"]}
        assert ids == {"E01", "M100"}, f"앞 turn의 근거를 물려받지 못함: {sorted(ids)}"

        prompt = second["messages"][-1]["content"]
        assert "광안리 해수욕장에서 뭘 하고 노셨어요?" in prompt, (
            f"되물은 질문의 컨텍스트에 원래 질문이 없음:\n{prompt}"
        )
        assert "이어받는 질문" in prompt, (
            f"물려받은 근거임을 밝히지 않음:\n{prompt}"
        )
        assert "검색 결과가 없습니다" not in prompt, (
            f"근거가 빈손으로 모델에 갔다:\n{prompt}"
        )

        # 앞 turn의 답변이 대화 기록으로 함께 간다 (무엇을 가리키는지 찾을 근거)
        history = "".join(m["content"] for m in second["messages"][:-1])
        assert "1998 부산 가족여행 기록이 있어요." in history, (
            "앞 답변이 대화 기록에 없음"
        )

    _with_stub_plan(run)


def test_named_absent_target_does_not_inherit_evidence():
    """없는 대상을 지목한 질문은 앞 근거로 답하지 않는다

    "런던 여행 얘기해줘"는 스스로 대상을 가리킨다. 검색이 빈손이라고 앞의
    부산 근거를 물려주면 없는 여행을 있는 것처럼 말한다.
    """

    def run(stub):
        conversation_id = "conv-absent"
        chat_engine._conversations.pop(conversation_id, None)
        chat_engine._last_results.pop(conversation_id, None)

        stub.state = {
            "results": list(EVIDENCE),
            "missing_entities": [],
            "planned_by_llm": True,
            "plan": {"persons": [], "places": [], "events": [], "year": "1998"},
        }
        first = asyncio.run(_prepare("98년 기억 알려줘", conversation_id, None))
        chat_engine._finish("98년 기억 알려줘", "기록이 있어요.", True, first)

        stub.state = {
            "results": [],
            "missing_entities": ["런던"],
            "planned_by_llm": True,
            "plan": {"persons": [], "places": ["런던"], "events": [], "year": None},
        }
        second = asyncio.run(_prepare("런던 여행 얘기해줘", conversation_id, None))

        assert second["search_results"] == [], (
            f"없는 대상인데 앞 근거를 물려받았다: "
            f"{[n['id'] for n in second['search_results']]}"
        )

    _with_stub_plan(run)


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}\n{e}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
