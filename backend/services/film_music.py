"""Memory Film 배경 음악 — 무드 고르기 (기획안 02장 CORE · STORY)

소리는 서버가 만들지 않는다. 무드만 고르고, 화면이 그 무드로 소리를 합성한다
(frontend/src/lib/filmMusic.ts). narrator(브라우저 speechSynthesis)·recorder·
transcriber와 같은 분업이다 — 음원 자산도 음악 생성 API 키도 없는데, 브라우저는
이미 소리를 만들 수 있다.

무엇을 깔지는 서버가 정한다. 카메라 움직임에서 같은 실수를 한 적이 있다
(film_composer.CAMERA_MOTIONS) — 화면이 따로 고르면 "무슨 음악이 왜 깔렸는지"
적어 둔 문구가 사실이 아니게 된다.

LLM에 맡기지 않는다. motion_prompt와 같은 이유다 — 같은 사건이 볼 때마다 다른
음악으로 시작하면 그 음악은 이 사건의 것이 아니다. 낱말 표는 사람이 읽고 고칠 수
있고, 왜 그 무드가 나왔는지 화면에 그대로 적을 수 있다.

사건이 가진 말(제목·설명·장소)만 본다. 가족이 남긴 기억 문장은 보지 않는다.
문장 하나가 더 붙었다고 이야기의 음악이 바뀌면 안 되고, "돌아가신 할머니와 갔던
여행"처럼 사람을 가리키는 말이 사건의 성격으로 읽히면 잔치에 추모 음악이 깔린다.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

# 무드 이름과 화면에 나갈 문구. 화면(filmMusic.ts)이 같은 열쇠로 소리를 만든다 —
# 목록 순서가 아니라 열쇠로 찾으므로, 한쪽에 무드를 더해도 표시와 적용이 어긋나지
# 않는다 (FilmPage의 MOTION_CLASS와 같은 방식이다).
MOOD_LABEL = {
    "warm": "따뜻하게",
    "nostalgic": "회상하듯",
    "bright": "밝게",
    "calm": "차분하게",
    "solemn": "낮고 조용하게",
}

DEFAULT_MOOD = "calm"

# 추모하는 자리. 가장 먼저 보고, 다른 낱말이 함께 걸려도 이쪽이 이긴다.
# 여러 글자짜리만 넣는다 — "묘"·"돌" 같은 한 글자는 묘사·돌잔치에 걸린다.
SOLEMN_WORDS = (
    "제사", "장례", "장례식", "발인", "빈소", "문상", "조문", "성묘", "산소",
    "추모", "추도", "추념", "49재", "사십구재", "기제", "위령", "삼우제",
)

# 아이·학교·놀이의 자리
BRIGHT_WORDS = (
    "입학", "졸업", "운동회", "소풍", "수학여행", "학예회", "재롱", "유치원",
    "어린이", "놀이", "물놀이", "해수욕", "수영", "캠핑", "여행", "나들이",
    "방학", "동물원", "놀이공원", "생일", "돌잔치", "백일",
)

# 모여서 기리는 자리
WARM_WORDS = (
    "결혼", "혼례", "예식", "약혼", "상견례", "청혼",
    "칠순", "환갑", "팔순", "고희", "회갑", "잔치",
    "가족모임", "가족사진", "모임", "명절", "추석", "한가위", "설날", "김장",
)

# 한 세대가 지난 기록. 이 해 수를 넘으면 그 자체가 회상이다.
NOSTALGIC_YEARS = 20


def _subject_josa(word: str) -> str:
    """‘제사’가 / ‘졸업’이 — 받침에 따라 조사를 고른다

    "이(가)"로 적으면 화면에 그대로 나가는 문구가 어색해진다. 이 자리는 왜 이
    음악이 깔렸는지 사람에게 밝히는 곳이라 문장으로 읽혀야 한다.
    """
    if not word:
        return "가"
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return "이" if (code - 0xAC00) % 28 else "가"
    return "가"


def _match(haystack: str, words: tuple[str, ...]) -> Optional[str]:
    """걸린 낱말을 돌려준다 (없으면 None) — 무엇에 걸렸는지 밝힐 수 있게"""
    for word in words:
        if word in haystack:
            return word
    return None


def _years_ago(date_start: Optional[str], today: date) -> Optional[int]:
    if not date_start:
        return None
    try:
        year = int(date_start.split("-")[0])
    except (ValueError, IndexError):
        return None
    return today.year - year


def pick(
    event: dict,
    place_name: Optional[str] = None,
    pace: float = 1.0,
    today: Optional[date] = None,
) -> dict:
    """이 사건에 깔 음악의 무드

    판단에 순서가 있다. 한 사건이 여러 낱말에 걸리기 때문이다 — "할머니 칠순잔치"와
    "성묘"가 같은 기록에 있을 수 있고, 그때 무엇이 이기는지 정해 두지 않으면 같은
    사건이 열 때마다 다르게 들린다.

      1. 추모하는 자리. 무조건 먼저 본다 — 제사에 밝은 음악이 깔리는 것은 고치면
         되는 실수가 아니라 그 자리를 망치는 일이다
      2. 한 세대가 지난 기록. 20년이 넘었으면 그것 자체가 회상이다
      3. 아이·학교·놀이의 자리
      4. 모여서 기리는 자리
      5. 나머지는 이야기를 방해하지 않는 차분한 소리

    pace는 대상 세대의 장면 배수를 그대로 받는다 (film_composer.AUDIENCE_PACE).
    어르신에게 장면을 늦추면서 음악만 제 속도로 가면 화면과 소리가 갈라진다.
    """
    today = today or date.today()
    haystack = " ".join(
        [event.get("title") or "", event.get("description") or "", place_name or ""]
    )

    word = _match(haystack, SOLEMN_WORDS)
    if word:
        mood = "solemn"
        reason = f"기록에 ‘{word}’{_subject_josa(word)} 있습니다."
    else:
        years = _years_ago(event.get("date_start"), today)
        if years is not None and years >= NOSTALGIC_YEARS:
            mood = "nostalgic"
            reason = f"{years}년 전 기록입니다."
        elif (word := _match(haystack, BRIGHT_WORDS)):
            mood = "bright"
            reason = f"기록에 ‘{word}’{_subject_josa(word)} 있습니다."
        elif (word := _match(haystack, WARM_WORDS)):
            mood = "warm"
            reason = f"기록에 ‘{word}’{_subject_josa(word)} 있습니다."
        else:
            mood = DEFAULT_MOOD
            reason = "특별한 자리를 가리키는 말이 없는 기록입니다."

    return {
        "mood": mood,
        "label": MOOD_LABEL[mood],
        "reason": reason,
        # 소수점 둘째 자리까지. 화면이 코드 전환과 음 간격에 곱한다.
        "pace": round(pace, 2),
    }
