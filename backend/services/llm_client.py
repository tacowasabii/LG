"""EXAONE 호출 클라이언트 - LG AI Research code-cli 게이트웨이

LangChain의 ChatOpenAI로 통신한다. 게이트웨이는 OpenAI 호환이지만 인증이
Authorization: Bearer가 아니라 x-api-key다 (Bearer만 보내면 401). 확인 결과
Bearer는 무시되므로 default_headers로 x-api-key를 넣으면 통과한다.
top_k / min_p / repetition_penalty / chat_template_kwargs는 비표준이라
extra_body로 넘긴다.

키가 없거나 호출이 실패하면 None을 반환하고, 각 호출부가 자체 시뮬레이션
응답으로 폴백한다. 이 계약을 깨면 발표 중 네트워크 사고가 그대로 화면에 나온다.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI

from backend.config import (
    EXAONE_API_KEY,
    EXAONE_API_URL,
    EXAONE_ENABLE_THINKING,
    EXAONE_MIN_P,
    EXAONE_MODEL,
    EXAONE_PRESENCE_PENALTY,
    EXAONE_REPETITION_PENALTY,
    EXAONE_TEMPERATURE,
    EXAONE_THINKING_BUDGET,
    EXAONE_TIMEOUT,
    EXAONE_TOP_K,
    EXAONE_TOP_P,
)

# code-cli 게이트웨이는 추론을 message.reasoning으로 분리해서 주므로 content는 이미 깨끗하다.
# 다만 <thought> 블록을 content에 섞어 보내는 EXAONE 배포본도 있어 방어적으로 걷어낸다.
_THINK_BLOCK = re.compile(r"<(thought|think)>.*?</\1>", re.DOTALL)
# max_tokens에 걸려 닫는 태그 없이 끊긴 경우
_THINK_UNCLOSED = re.compile(r"<(thought|think)>.*\Z", re.DOTALL)

# 모델이 JSON을 ```json 펜스로 감싸 보내는 경우가 있다
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def is_enabled() -> bool:
    """API 키가 설정되어 실제 호출이 가능한 상태인지"""
    return bool(EXAONE_API_KEY)


def _base_url() -> str:
    """ChatOpenAI는 /chat/completions를 스스로 붙이므로 떼어낸 값을 준다"""
    suffix = "/chat/completions"
    if EXAONE_API_URL.endswith(suffix):
        return EXAONE_API_URL[: -len(suffix)]
    return EXAONE_API_URL


@lru_cache(maxsize=8)
def get_chat_model(
    model: Optional[str] = None,
    max_tokens: int = 1024,
    thinking: Optional[bool] = None,
    temperature: Optional[float] = None,
) -> ChatOpenAI:
    """설정이 적용된 ChatOpenAI 인스턴스 (조합별로 캐시)

    thinking=True면 추론도 출력 토큰을 쓰므로 예산에 여유분을 더한다.
    """
    use_thinking = EXAONE_ENABLE_THINKING if thinking is None else thinking
    budget = max_tokens + (EXAONE_THINKING_BUDGET if use_thinking else 0)

    return ChatOpenAI(
        model=model or EXAONE_MODEL,
        base_url=_base_url(),
        # 게이트웨이는 Bearer를 무시하지만 SDK가 값을 요구한다
        api_key="unused-gateway-uses-x-api-key",
        default_headers={"x-api-key": EXAONE_API_KEY},
        temperature=EXAONE_TEMPERATURE if temperature is None else temperature,
        top_p=EXAONE_TOP_P,
        presence_penalty=EXAONE_PRESENCE_PENALTY,
        max_tokens=budget,
        timeout=EXAONE_TIMEOUT,
        max_retries=2,  # 게이트웨이가 연속 호출에 간헐적으로 응답을 끊는다
        extra_body={
            "top_k": EXAONE_TOP_K,
            "min_p": EXAONE_MIN_P,
            "repetition_penalty": EXAONE_REPETITION_PENALTY,
            "chat_template_kwargs": {"enable_thinking": use_thinking},
        },
    )


def strip_thinking(text: str) -> str:
    """추론 블록을 제거하고 사용자에게 보여줄 본문만 남긴다"""
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_UNCLOSED.sub("", cleaned)
    return cleaned.strip()


async def complete(
    messages: list[dict],
    max_tokens: int,
    model: Optional[str] = None,
    thinking: Optional[bool] = None,
    temperature: Optional[float] = None,
) -> Optional[str]:
    """EXAONE에 messages를 보내고 본문을 받는다

    Args:
        messages: OpenAI 호환 chat messages
        max_tokens: 답변 본문에 필요한 토큰 예산
        model: 기본 모델 대신 쓸 모델 (예: 의도 분석용 instant)
        thinking: 추론 모드 재정의
        temperature: 온도 재정의 (구조화 추출은 낮게)

    Returns:
        답변 본문. 키가 없거나 호출 실패/본문 없음이면 None.
    """
    if not EXAONE_API_KEY:
        return None

    llm = get_chat_model(
        model=model, max_tokens=max_tokens, thinking=thinking, temperature=temperature
    )

    try:
        result = await llm.ainvoke(messages)
    except Exception as e:  # 게이트웨이 오류·타임아웃·인증 실패 전부
        print(f"[EXAONE] 호출 실패 ({type(e).__name__}: {str(e)[:200]}) → 시뮬레이션 폴백")
        return None

    answer = strip_thinking(result.content if isinstance(result.content, str) else "")

    if not answer:
        finish = (result.response_metadata or {}).get("finish_reason")
        print(
            f"[EXAONE] 본문이 비어 있음 (finish_reason={finish}). "
            f"EXAONE_THINKING_BUDGET({EXAONE_THINKING_BUDGET}) 부족 의심 → 시뮬레이션 폴백"
        )
        return None

    return answer


async def complete_json(
    messages: list[dict],
    max_tokens: int,
    model: Optional[str] = None,
) -> Optional[dict]:
    """구조화 추출용. JSON 객체를 받아 dict로 돌려준다

    의도 분석처럼 결과를 코드가 소비하는 경우에 쓴다. 추론을 끄고 온도를 낮춰
    형식 이탈을 줄이고, 파싱에 실패하면 None을 돌려 호출부가 폴백하게 한다.
    """
    raw = await complete(
        messages, max_tokens=max_tokens, model=model, thinking=False, temperature=0.0
    )
    if raw is None:
        return None

    text = raw.strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    else:
        # 앞뒤 설명 문장이 붙어 오는 경우 첫 { 부터 마지막 } 까지만 취한다
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]

    try:
        parsed = json.loads(text)
    except (ValueError, TypeError) as e:
        print(f"[EXAONE] JSON 파싱 실패 ({e}) → 규칙 기반 폴백. 원문: {raw[:160]}")
        return None

    if not isinstance(parsed, dict):
        print(f"[EXAONE] JSON이 객체가 아님 ({type(parsed).__name__}) → 규칙 기반 폴백")
        return None

    return parsed
