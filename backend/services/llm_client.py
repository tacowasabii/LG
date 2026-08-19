"""EXAONE 호출 클라이언트 - LG AI Research code-cli 게이트웨이

chat_engine / interview_engine / tv_curator가 공유한다.
키가 없거나 호출이 실패하면 None을 반환하고, 각 호출부가 자체 시뮬레이션 응답으로 폴백한다.
"""

from __future__ import annotations

import re

import httpx

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


def is_enabled() -> bool:
    """API 키가 설정되어 실제 호출이 가능한 상태인지"""
    return bool(EXAONE_API_KEY)


def strip_thinking(text: str) -> str:
    """추론 블록을 제거하고 사용자에게 보여줄 본문만 남긴다"""
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_UNCLOSED.sub("", cleaned)
    return cleaned.strip()


async def complete(messages: list[dict], max_tokens: int) -> str | None:
    """EXAONE에 messages를 보내고 본문을 받는다

    Args:
        messages: OpenAI 호환 chat messages
        max_tokens: 답변 본문에 필요한 토큰 예산.
            추론 모드에서는 EXAONE_THINKING_BUDGET만큼 자동으로 더해진다.

    Returns:
        답변 본문. 키가 없거나 호출 실패/본문 없음이면 None.
    """
    if not EXAONE_API_KEY:
        return None

    payload = {
        "model": EXAONE_MODEL,
        "messages": messages,
        "temperature": EXAONE_TEMPERATURE,
        "top_p": EXAONE_TOP_P,
        "top_k": EXAONE_TOP_K,
        "min_p": EXAONE_MIN_P,
        "presence_penalty": EXAONE_PRESENCE_PENALTY,
        "repetition_penalty": EXAONE_REPETITION_PENALTY,
        "chat_template_kwargs": {"enable_thinking": EXAONE_ENABLE_THINKING},
        "max_tokens": max_tokens,
    }

    if EXAONE_ENABLE_THINKING:
        # 추론도 출력 토큰을 쓴다. 예산을 다 먹으면 본문이 한 글자도 안 나온다.
        payload["max_tokens"] = max_tokens + EXAONE_THINKING_BUDGET

    try:
        async with httpx.AsyncClient(timeout=EXAONE_TIMEOUT) as client:
            response = await client.post(
                EXAONE_API_URL,
                headers={
                    "x-api-key": EXAONE_API_KEY,
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
    except httpx.HTTPStatusError as e:
        print(f"[EXAONE] {e.response.status_code} {e.response.text[:300]} → 시뮬레이션 폴백")
        return None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        print(f"[EXAONE] 호출 실패 ({type(e).__name__}: {e}) → 시뮬레이션 폴백")
        return None

    answer = strip_thinking(choice.get("message", {}).get("content") or "")

    if not answer:
        # 추론만 나오고 본문이 잘린 상황. EXAONE_THINKING_BUDGET을 올리면 해결된다.
        print(
            f"[EXAONE] 본문이 비어 있음 (finish_reason={choice.get('finish_reason')}). "
            f"EXAONE_THINKING_BUDGET({EXAONE_THINKING_BUDGET}) 부족 의심 → 시뮬레이션 폴백"
        )
        return None

    return answer
