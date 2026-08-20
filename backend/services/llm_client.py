"""LLM 호출 클라이언트 — EXAONE 게이트웨이 + Bedrock

LangChain의 ChatOpenAI로 통신한다. 게이트웨이는 OpenAI 호환이지만 인증이
Authorization: Bearer가 아니라 x-api-key다 (Bearer만 보내면 401). 확인 결과
Bearer는 무시되므로 default_headers로 x-api-key를 넣으면 통과한다.
top_k / min_p / repetition_penalty / chat_template_kwargs는 비표준이라
extra_body로 넘긴다.

키가 없거나 호출이 실패하면 None을 반환하고, 각 호출부가 자체 시뮬레이션
응답으로 폴백한다. 이 계약을 깨면 발표 중 네트워크 사고가 그대로 화면에 나온다.

용도에 따라 제공자가 갈린다 (backend/config.py).

    answer · question · narrate   EXAONE
        한국어 서술과 호칭·세대별 어투가 걸린 곳. 기획안이 EXAONE 강점으로
        내세운 자리이고, 채점(Trust Harness)도 이 경로를 돈다.

    plan · extract                Bedrock (기본값)
        질문이나 답변에서 JSON 조각만 뽑는 기계적인 호출. 질의 계획은 채팅
        응답 시간에 그대로 더해지므로 빠른 모델이 유리하다.

Bedrock 자격증명이 없으면 조용히 EXAONE으로 돌아간다 — 설정하지 않은 사람의
화면이 깨지지 않게. 어느 쪽으로 갔는지는 로그에 남는다.
"""

from __future__ import annotations

import asyncio
import json
import re
from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI

from backend.config import (
    AWS_ACCESS_KEY_ID,
    AWS_PROFILE,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
    BEDROCK_MODEL_ID,
    BEDROCK_TIMEOUT,
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
    LLM_EXTRACT_PROVIDER,
    LLM_PLAN_PROVIDER,
)

# code-cli 게이트웨이는 추론을 message.reasoning으로 분리해서 주므로 content는 이미 깨끗하다.
# 다만 <thought> 블록을 content에 섞어 보내는 EXAONE 배포본도 있어 방어적으로 걷어낸다.
_THINK_BLOCK = re.compile(r"<(thought|think)>.*?</\1>", re.DOTALL)
# max_tokens에 걸려 닫는 태그 없이 끊긴 경우
_THINK_UNCLOSED = re.compile(r"<(thought|think)>.*\Z", re.DOTALL)

# 모델이 JSON을 ```json 펜스로 감싸 보내는 경우가 있다
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


# 용도 -> 설정된 제공자
_PROVIDER_BY_PURPOSE = {
    "plan": LLM_PLAN_PROVIDER,
    "extract": LLM_EXTRACT_PROVIDER,
}


def bedrock_enabled() -> bool:
    """Bedrock을 부를 자격증명이 있는지 (.env의 키 또는 프로필)"""
    return bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY) or bool(AWS_PROFILE)


# 어느 용도를 어디로 보내는지 한 번씩만 알린다 (호출마다 찍으면 로그가 시끄럽다)
_announced: set = set()


def provider_for(purpose: Optional[str]) -> str:
    """이 용도를 어디로 보낼지. 설정이 bedrock이라도 자격증명이 없으면 EXAONE."""
    provider = _PROVIDER_BY_PURPOSE.get(purpose or "", "exaone")
    if provider == "bedrock" and not bedrock_enabled():
        provider = "exaone"

    key = (purpose or "answer", provider)
    if key not in _announced:
        _announced.add(key)
        model = BEDROCK_MODEL_ID if provider == "bedrock" else EXAONE_MODEL
        print(f"[LLM] {key[0]} -> {provider} ({model})")

    return provider


def is_enabled(purpose: Optional[str] = None) -> bool:
    """이 용도를 실제로 호출할 수 있는 상태인지

    purpose를 주면 그 용도의 제공자를 본다. Bedrock으로 보내는 용도는 EXAONE
    키가 없어도 동작한다 (반대도 마찬가지).
    """
    if provider_for(purpose) == "bedrock":
        return True  # provider_for가 이미 자격증명을 확인했다
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


# --- Bedrock ------------------------------------------------------------------


@lru_cache(maxsize=1)
def _bedrock_client():
    """bedrock-runtime 클라이언트 (한 번만 만든다)

    boto3를 여기서 import한다. 자격증명이 없는 로컬에서 이 패키지가 없어도 앱이
    뜨게 하려는 것이다 (Postgres 저장소와 같은 방식).
    """
    import boto3
    from botocore.config import Config

    kwargs = {"region_name": AWS_REGION}
    if AWS_PROFILE:
        kwargs["profile_name"] = AWS_PROFILE
    elif AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
        if AWS_SESSION_TOKEN:
            kwargs["aws_session_token"] = AWS_SESSION_TOKEN

    session = boto3.session.Session(**kwargs)
    return session.client(
        "bedrock-runtime",
        config=Config(
            read_timeout=BEDROCK_TIMEOUT,
            connect_timeout=10,
            # 이 망에서는 새 연결의 첫 요청이 자주 끊긴다 (ConnectionClosedError).
            # 두 번째부터는 1~3초로 안정적이라 재시도로 덮는다.
            retries={"max_attempts": 4, "mode": "standard"},
        ),
    )


def _to_converse(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """OpenAI 형식 messages를 Bedrock Converse 형식으로

    Converse는 system을 별도 인자로 받고, 본문을 [{"text": ...}] 블록으로 싼다.
    같은 역할이 연달아 오면 합친다 (Converse는 교대를 요구한다).
    """
    system: list[dict] = []
    turns: list[dict] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""
        if not content:
            continue
        if role == "system":
            system.append({"text": content})
            continue
        role = "assistant" if role == "assistant" else "user"
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].append({"text": content})
        else:
            turns.append({"role": role, "content": [{"text": content}]})

    return system, turns


def _bedrock_invoke(messages: list[dict], max_tokens: int, temperature: float) -> Optional[str]:
    """동기 호출 (호출부는 asyncio.to_thread로 감싼다)"""
    system, turns = _to_converse(messages)
    if not turns:
        return None

    request = {
        "modelId": BEDROCK_MODEL_ID,
        "messages": turns,
        "system": system or [{"text": "요청받은 형식으로만 답한다."}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }

    # 연결이 끊기는 것(첫 요청에서 잦다)과 권한·모델 오류를 구분한다. 앞은 다시
    # 걸면 되고, 뒤는 다시 걸어도 같은 결과라 바로 EXAONE으로 넘긴다.
    from botocore.exceptions import ConnectionClosedError, EndpointConnectionError

    response = None
    for attempt in (1, 2):
        try:
            response = _bedrock_client().converse(**request)
            break
        except (ConnectionClosedError, EndpointConnectionError) as e:
            if attempt == 1:
                print(f"[Bedrock] 연결이 끊겼습니다 ({type(e).__name__}) → 다시 겁니다")
                continue
            print(f"[Bedrock] 연결 실패 ({type(e).__name__}) → EXAONE으로 재시도")
            return None
        except Exception as e:  # 자격증명·권한·모델 접근·형식 오류
            print(f"[Bedrock] 호출 실패 ({type(e).__name__}: {str(e)[:200]}) → EXAONE으로 재시도")
            return None

    if response is None:
        return None

    blocks = (response.get("output") or {}).get("message", {}).get("content") or []
    text = "".join(block.get("text", "") for block in blocks).strip()
    if not text:
        print(f"[Bedrock] 본문이 비어 있음 (stopReason={response.get('stopReason')})")
        return None
    return text


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
    purpose: Optional[str] = None,
) -> Optional[str]:
    """messages를 보내고 본문을 받는다

    Args:
        messages: OpenAI 호환 chat messages
        max_tokens: 답변 본문에 필요한 토큰 예산
        model: 기본 모델 대신 쓸 모델 (예: 의도 분석용 instant). EXAONE 경로에만
            쓰인다 — Bedrock은 BEDROCK_MODEL_ID를 쓴다.
        thinking: 추론 모드 재정의 (EXAONE 전용)
        temperature: 온도 재정의 (구조화 추출은 낮게)
        purpose: "plan" · "extract"면 설정된 제공자로 보낸다. 없으면 EXAONE.

    Returns:
        답변 본문. 호출 실패/본문 없음이면 None (호출부가 폴백한다).
    """
    if provider_for(purpose) == "bedrock":
        text = await asyncio.to_thread(
            _bedrock_invoke, messages, max_tokens, 0.0 if temperature is None else temperature
        )
        if text is not None:
            return text
        # Bedrock이 실패하면 EXAONE으로 한 번 더 시도한다 (조용히 죽지 않게)

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
    purpose: Optional[str] = None,
) -> Optional[dict]:
    """구조화 추출용. JSON 객체를 받아 dict로 돌려준다

    의도 분석처럼 결과를 코드가 소비하는 경우에 쓴다. 추론을 끄고 온도를 낮춰
    형식 이탈을 줄이고, 파싱에 실패하면 None을 돌려 호출부가 폴백하게 한다.
    """
    raw = await complete(
        messages,
        max_tokens=max_tokens,
        model=model,
        thinking=False,
        temperature=0.0,
        purpose=purpose,
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
