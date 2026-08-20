"""LLM 호출 클라이언트 — EXAONE 게이트웨이 + Bedrock

LangChain의 ChatOpenAI로 통신한다. 게이트웨이는 OpenAI 호환이지만 인증이
Authorization: Bearer가 아니라 x-api-key다 (Bearer만 보내면 401). 확인 결과
Bearer는 무시되므로 default_headers로 x-api-key를 넣으면 통과한다.
top_k / min_p / repetition_penalty / chat_template_kwargs는 비표준이라
extra_body로 넘긴다.

키가 없거나 호출이 실패하면 None을 반환하고, 각 호출부가 자체 시뮬레이션
응답으로 폴백한다. 이 계약을 깨면 발표 중 네트워크 사고가 그대로 화면에 나온다.

용도에 따라 제공자가 갈린다 (backend/config.py).

    answer · question · narrate   EXAONE (기본값, LLM_ANSWER_PROVIDER로 변경)
        한국어 서술과 호칭·세대별 어투가 걸린 곳. 기획안이 EXAONE 강점으로
        내세운 자리이고, 채점(Trust Harness)도 이 경로를 돈다.

        다만 EXAONE 게이트웨이는 사내망 사설 주소(10.x)다 — 공용 클라우드에
        배포하면 연결이 열리지 않고 타임아웃까지 매달린다. 배포에서는
        LLM_ANSWER_PROVIDER=bedrock으로 돌린다.

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
from contextlib import aclosing
from functools import lru_cache
from typing import AsyncIterator, Optional

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
    FRIENDLI_API_URL,
    FRIENDLI_ENABLE_THINKING,
    FRIENDLI_MODEL,
    FRIENDLI_PRESENCE_PENALTY,
    FRIENDLI_TEMPERATURE,
    FRIENDLI_TIMEOUT,
    FRIENDLI_TOKEN,
    FRIENDLI_TOP_P,
    LLM_EXTRACT_PROVIDER,
    LLM_ANSWER_PROVIDER,
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
    "answer": LLM_ANSWER_PROVIDER,
    "plan": LLM_PLAN_PROVIDER,
    "extract": LLM_EXTRACT_PROVIDER,
}


def friendli_enabled() -> bool:
    """FriendliAI를 부를 토큰이 있는지"""
    return bool(FRIENDLI_TOKEN)


def bedrock_enabled() -> bool:
    """Bedrock을 부를 자격증명이 있는지 (.env의 키 또는 프로필)"""
    return bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY) or bool(AWS_PROFILE)


_MODEL_BY_PROVIDER = {
    "exaone": EXAONE_MODEL,
    "bedrock": BEDROCK_MODEL_ID,
    "friendli": FRIENDLI_MODEL,
}

# 어느 용도를 어디로 보내는지 한 번씩만 알린다 (호출마다 찍으면 로그가 시끄럽다)
_announced: set = set()


def provider_for(purpose: Optional[str]) -> str:
    """이 용도를 어디로 보낼지. 설정이 bedrock이라도 자격증명이 없으면 EXAONE."""
    provider = _PROVIDER_BY_PURPOSE.get(purpose or "answer", "exaone")
    if provider == "bedrock" and not bedrock_enabled():
        provider = "exaone"
    if provider == "friendli" and not friendli_enabled():
        provider = "exaone"

    key = (purpose or "answer", provider)
    if key not in _announced:
        _announced.add(key)
        model = _MODEL_BY_PROVIDER.get(provider, EXAONE_MODEL)
        print(f"[LLM] {key[0]} -> {provider} ({model})", flush=True)

    return provider


def model_for(purpose: Optional[str] = None) -> str:
    """이 용도가 실제로 부르는 모델 이름

    화면에 "무엇이 답했는지" 밝히는 데 쓴다. 제공자와 따로 관리하면 Bedrock이
    답한 것을 EXAONE 이름으로 적게 된다.
    """
    return _MODEL_BY_PROVIDER.get(provider_for(purpose), EXAONE_MODEL)


def is_enabled(purpose: Optional[str] = None) -> bool:
    """이 용도를 실제로 호출할 수 있는 상태인지

    purpose를 주면 그 용도의 제공자를 본다. Bedrock으로 보내는 용도는 EXAONE
    키가 없어도 동작한다 (반대도 마찬가지).
    """
    if provider_for(purpose) in ("bedrock", "friendli"):
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


# --- FriendliAI ---------------------------------------------------------------


def _friendli_base_url() -> str:
    """ChatOpenAI가 /chat/completions를 스스로 붙이므로 떼어낸 값을 준다"""
    suffix = "/chat/completions"
    if FRIENDLI_API_URL.endswith(suffix):
        return FRIENDLI_API_URL[: -len(suffix)]
    return FRIENDLI_API_URL


@lru_cache(maxsize=8)
def get_friendli_model(max_tokens: int = 1024, temperature: Optional[float] = None) -> ChatOpenAI:
    """FriendliAI용 ChatOpenAI (OpenAI 호환, 인증은 Bearer)

    사내망 게이트웨이와 달리 표준 Authorization 헤더를 쓴다. 추론을 켜면
    응답에 사고 과정이 함께 오므로 strip_thinking()으로 걷어낸다.
    """
    return ChatOpenAI(
        model=FRIENDLI_MODEL,
        base_url=_friendli_base_url(),
        api_key=FRIENDLI_TOKEN,
        temperature=FRIENDLI_TEMPERATURE if temperature is None else temperature,
        top_p=FRIENDLI_TOP_P,
        presence_penalty=FRIENDLI_PRESENCE_PENALTY,
        max_tokens=max_tokens + (EXAONE_THINKING_BUDGET if FRIENDLI_ENABLE_THINKING else 0),
        timeout=FRIENDLI_TIMEOUT,
        max_retries=2,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": FRIENDLI_ENABLE_THINKING,
                # 사고 과정을 응답에 남긴다. strip_thinking()이 화면에 나가기 전에
                # 떼어내고, 남겨 두는 쪽이 빈 본문이 왔을 때 원인을 볼 수 있다.
                "preserve_thinking": FRIENDLI_ENABLE_THINKING,
            }
        },
    )


async def _friendli_invoke(
    messages: list[dict], max_tokens: int, temperature: Optional[float]
) -> Optional[str]:
    """FriendliAI 호출. 실패하면 None (호출부가 폴백한다)"""
    try:
        result = await get_friendli_model(max_tokens, temperature).ainvoke(messages)
    except Exception as e:
        print(f"[Friendli] 호출 실패 ({type(e).__name__}: {str(e)[:200]})", flush=True)
        return None

    answer = strip_thinking(result.content if isinstance(result.content, str) else "")
    if not answer:
        finish = (result.response_metadata or {}).get("finish_reason")
        print(f"[Friendli] 본문이 비어 있음 (finish_reason={finish})", flush=True)
        return None
    return answer


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
                print(f"[Bedrock] 연결이 끊겼습니다 ({type(e).__name__}) → 다시 겁니다", flush=True)
                continue
            print(f"[Bedrock] 연결 실패 ({type(e).__name__}) → 다음 제공자로", flush=True)
            return None
        except Exception as e:  # 자격증명·권한·모델 접근·형식 오류
            print(f"[Bedrock] 호출 실패 ({type(e).__name__}: {str(e)[:200]}) → 다음 제공자로", flush=True)
            return None

    if response is None:
        return None

    blocks = (response.get("output") or {}).get("message", {}).get("content") or []
    text = "".join(block.get("text", "") for block in blocks).strip()
    if not text:
        print(f"[Bedrock] 본문이 비어 있음 (stopReason={response.get('stopReason')})", flush=True)
        return None
    return text


def _bedrock_describe_image(image_bytes: bytes, fmt: str, prompt: str) -> Optional[str]:
    """이미지 한 장을 보내고 설명을 받는다 (동기 — 호출부가 to_thread로 감싼다)

    Converse API는 본문 블록에 이미지를 함께 실을 수 있다. 텍스트만 다루는
    _to_converse를 고치지 않고 여기서 직접 요청을 만든다 — 이미지가 필요한
    호출은 이 하나뿐이고, 텍스트 경로에 분기를 더하면 그쪽이 읽기 어려워진다.
    """
    request = {
        "modelId": BEDROCK_MODEL_ID,
        "messages": [{
            "role": "user",
            "content": [
                {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
                {"text": prompt},
            ],
        }],
        "inferenceConfig": {"maxTokens": 300, "temperature": 0.2},
    }

    from botocore.exceptions import ConnectionClosedError, EndpointConnectionError

    # 텍스트 경로보다 한 번 더 시도한다. 여기서 놓치면 설명이 빈 채로 남고,
    # 그 사진은 초안·검색에서 계속 내용 없는 사진으로 취급된다.
    response = None
    attempts = (1, 2, 3)
    for attempt in attempts:
        try:
            response = _bedrock_client().converse(**request)
            break
        except (ConnectionClosedError, EndpointConnectionError) as e:
            if attempt < attempts[-1]:
                print(
                    f"[Bedrock/vision] 연결이 끊겼습니다 ({type(e).__name__}) "
                    f"→ 다시 겁니다 ({attempt}/{attempts[-1]})",
                    flush=True,
                )
                continue
            print(f"[Bedrock/vision] 연결 실패 ({type(e).__name__}) → 설명을 비워 둡니다", flush=True)
            return None
        except Exception as e:
            print(
                f"[Bedrock/vision] 호출 실패 ({type(e).__name__}: {str(e)[:200]}) "
                "→ 설명을 비워 둡니다",
                flush=True,
            )
            return None

    blocks = (response.get("output") or {}).get("message", {}).get("content") or []
    text = "".join(block.get("text", "") for block in blocks).strip()
    return text or None


async def describe_image(image_bytes: bytes, fmt: str, prompt: str) -> Optional[str]:
    """사진 한 장을 모델에게 보여주고 설명을 받는다

    EXAONE 폴백이 없다. 이 게이트웨이는 이미지를 받지 않으므로, Bedrock 자격증명이
    없으면 설명을 만들지 않는다 — 사진을 보지 않고 쓴 문장을 "AI가 읽은 내용"으로
    남기면 그게 가장 나쁜 거짓이다.

    Returns:
        설명 문장. 자격증명 없음·호출 실패·본문 없음이면 None.
    """
    if not bedrock_enabled():
        return None
    return await asyncio.to_thread(_bedrock_describe_image, image_bytes, fmt, prompt)


def strip_thinking(text: str) -> str:
    """추론 블록을 제거하고 사용자에게 보여줄 본문만 남긴다"""
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_UNCLOSED.sub("", cleaned)
    return cleaned.strip()


_FALLBACK_ORDER = ("friendli", "bedrock", "exaone")


def _provider_available(provider: str) -> bool:
    """이 제공자를 부를 자격증명이 있는지"""
    if provider == "friendli":
        return friendli_enabled()
    if provider == "bedrock":
        return bedrock_enabled()
    return bool(EXAONE_API_KEY)


async def _exaone_invoke(
    messages: list[dict],
    max_tokens: int,
    model: Optional[str],
    thinking: Optional[bool],
    temperature: Optional[float],
) -> Optional[str]:
    """사내망 EXAONE 게이트웨이 호출. 실패하면 None"""
    llm = get_chat_model(
        model=model, max_tokens=max_tokens, thinking=thinking, temperature=temperature
    )
    try:
        result = await llm.ainvoke(messages)
    except Exception as e:  # 게이트웨이 오류·타임아웃·인증 실패 전부
        print(f"[EXAONE] 호출 실패 ({type(e).__name__}: {str(e)[:200]})", flush=True)
        return None

    answer = strip_thinking(result.content if isinstance(result.content, str) else "")
    if not answer:
        finish = (result.response_metadata or {}).get("finish_reason")
        print(
            f"[EXAONE] 본문이 비어 있음 (finish_reason={finish}). "
            f"EXAONE_THINKING_BUDGET({EXAONE_THINKING_BUDGET}) 부족 의심",
            flush=True,
        )
        return None
    return answer


async def _invoke(
    provider: str,
    messages: list[dict],
    max_tokens: int,
    model: Optional[str],
    thinking: Optional[bool],
    temperature: Optional[float],
) -> Optional[str]:
    """제공자 하나를 부른다"""
    if provider == "friendli":
        return await _friendli_invoke(messages, max_tokens, temperature)
    if provider == "bedrock":
        return await asyncio.to_thread(
            _bedrock_invoke, messages, max_tokens, 0.0 if temperature is None else temperature
        )
    return await _exaone_invoke(messages, max_tokens, model, thinking, temperature)


class _ThinkingStripper:
    """스트림에서 추론 블록을 걷어낸다

    한 번에 받는 응답은 strip_thinking()으로 정규식 한 번에 처리하면 된다.
    스트리밍은 그럴 수 없다 — 태그가 청크 경계에 걸쳐 온다("<thi" 다음 청크에 "nk>").
    그래서 지금 내보내도 안전한 부분만 내보내고, 태그의 앞부분일 수 있는 꼬리는
    다음 청크까지 들고 있는다.
    """

    _OPEN = ("<think>", "<thought>")
    _CLOSE = ("</think>", "</thought>")
    # 가장 긴 태그에서 한 글자 뺀 길이. 이만큼은 태그 조각일 수 있어 보류한다.
    _HOLD = max(len(tag) for tag in _OPEN + _CLOSE) - 1

    def __init__(self) -> None:
        self._buf = ""
        self._inside = False

    @staticmethod
    def _find(text: str, tags: tuple) -> tuple:
        best, found = -1, ""
        for tag in tags:
            i = text.find(tag)
            if i != -1 and (best == -1 or i < best):
                best, found = i, tag
        return best, found

    def _tail_len(self, text: str) -> int:
        """뒤쪽 몇 글자가 태그의 앞부분일 수 있는지"""
        for n in range(min(len(text), self._HOLD), 0, -1):
            if any(tag.startswith(text[-n:]) for tag in self._OPEN):
                return n
        return 0

    def feed(self, chunk: str) -> str:
        """청크를 넣고, 화면에 내보낼 수 있는 부분을 돌려준다"""
        self._buf += chunk
        out = []
        while True:
            if self._inside:
                i, tag = self._find(self._buf, self._CLOSE)
                if i == -1:
                    # 아직 닫히지 않았다. 내용은 버리고 태그 조각만 남긴다.
                    self._buf = self._buf[-self._HOLD :]
                    break
                self._buf = self._buf[i + len(tag) :]
                self._inside = False
                continue

            i, tag = self._find(self._buf, self._OPEN)
            if i == -1:
                keep = self._tail_len(self._buf)
                cut = len(self._buf) - keep
                out.append(self._buf[:cut])
                self._buf = self._buf[cut:]
                break
            out.append(self._buf[:i])
            self._buf = self._buf[i + len(tag) :]
            self._inside = True
        return "".join(out)

    def flush(self) -> str:
        """스트림이 끝났을 때 남은 것 (열린 추론 블록 안이면 버린다)"""
        if self._inside:
            return ""
        rest, self._buf = self._buf, ""
        return rest


async def stream(
    messages: list[dict],
    max_tokens: int,
    model: Optional[str] = None,
    thinking: Optional[bool] = None,
    temperature: Optional[float] = None,
    purpose: Optional[str] = None,
) -> AsyncIterator[str]:
    """토큰을 받는 대로 흘려보낸다

    complete()와 같은 제공자 사슬을 쓰지만 폴백 규칙이 하나 다르다. 첫 글자가
    나가기 전에 실패하면 다음 제공자로 넘어가고, 이미 흘려보낸 뒤에 끊기면
    거기서 끝낸다 — 화면에 쓰인 문장을 되돌릴 수는 없다.

    Bedrock은 스트리밍을 붙이지 않았다. 한 번에 받아 한 조각으로 내보낸다
    (답변 제공자는 배포에서 Friendli이고, Bedrock은 계획·추출용이다).
    """
    preferred = provider_for(purpose)

    for provider in [preferred] + [p for p in _FALLBACK_ORDER if p != preferred]:
        if not _provider_available(provider):
            continue

        emitted = False
        stripper = _ThinkingStripper()
        try:
            if provider == "bedrock":
                text = await _invoke(provider, messages, max_tokens, model, thinking, temperature)
                if text:
                    emitted = True
                    yield text
            else:
                llm = (
                    get_friendli_model(max_tokens, temperature)
                    if provider == "friendli"
                    else get_chat_model(
                        model=model,
                        max_tokens=max_tokens,
                        thinking=thinking,
                        temperature=temperature,
                    )
                )
                # aclosing으로 감싸는 이유: 이걸 빼면 HTTP 응답이 GC 시점까지
                # 열려 있어, 스트림이 중간에 끊길 때 "generator didn't stop"
                # 경고가 로그를 덮는다. 클라이언트가 창을 닫는 것은 정상 상황이다.
                async with aclosing(llm.astream(messages)) as parts:
                    async for part in parts:
                        piece = part.content if isinstance(part.content, str) else ""
                        if not piece:
                            continue
                        visible = stripper.feed(piece)
                        if visible:
                            emitted = True
                            yield visible
                tail = stripper.flush()
                if tail:
                    emitted = True
                    yield tail
        except Exception as e:
            print(
                f"[{provider}] 스트리밍 실패 ({type(e).__name__}: {str(e)[:160]})",
                flush=True,
            )
            if emitted:
                return
            continue

        if emitted:
            return
        print(f"[LLM] {provider} 스트리밍 본문 없음 → 다음 제공자", flush=True)


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
        purpose: "answer"(기본) · "plan" · "extract". 용도마다 설정된 제공자로
            보내고, 자격증명이 없으면 EXAONE으로 돌아간다.

    Returns:
        답변 본문. 호출 실패/본문 없음이면 None (호출부가 폴백한다).
    """
    provider = provider_for(purpose)

    preferred = provider_for(purpose)

    # 설정된 제공자를 먼저 부르고, 실패하면 자격증명이 있는 다른 제공자로 넘어간다.
    # 순서를 고정으로 둔 이유: 예전에는 무엇이 실패해도 마지막이 EXAONE이었는데,
    # EXAONE 게이트웨이는 사내망 사설 주소라서 배포에서는 연결이 열리지 않은 채
    # 타임아웃까지 매달린다 — 폴백이 오히려 응답을 더 늦추는 함정이었다.
    # 자격증명이 없는 제공자는 아예 건너뛰므로, 배포에서 EXAONE 키를 두지 않으면
    # 그 경로는 시도조차 하지 않는다.
    for provider in [preferred] + [p for p in _FALLBACK_ORDER if p != preferred]:
        if not _provider_available(provider):
            continue
        text = await _invoke(provider, messages, max_tokens, model, thinking, temperature)
        if text is not None:
            return text
        print(f"[LLM] {provider} 응답 없음 → 다음 제공자", flush=True)

    return None


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
        print(f"[EXAONE] JSON 파싱 실패 ({e}) → 규칙 기반 폴백. 원문: {raw[:160]}", flush=True)
        return None

    if not isinstance(parsed, dict):
        print(f"[EXAONE] JSON이 객체가 아님 ({type(parsed).__name__}) → 규칙 기반 폴백", flush=True)
        return None

    return parsed
