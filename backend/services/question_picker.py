"""무엇을 물어볼지 고른다 (AI 인터뷰의 과녁)

예전에는 `gap_detector`가 이 일을 했다. 그 모듈은 두 가지를 겸했다 —
(1) 인터뷰가 물어볼 대상을 고르는 일, (2) "해결해야 할 Memory Gap" 목록을
사용자에게 보여주는 일.

(2)를 없앴다. 빈칸을 과제 목록으로 보여주면 가족은 기록을 남기러 온 자리에서
할 일을 받아 간다. 채워지지 않은 기억은 결함이 아니다.

(1)은 남는다. 인터뷰는 무언가를 물어야 하고, 아무 추억이나 고르면 이미 잘
채워진 기억을 또 묻는다. 그래서 여기서는 목록을 만들지 않고 **하나**만 고른다.
화면에도 API에도 노출되지 않는다.
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.models.graph_models import NodeType
from backend.services.graph_manager import graph_manager


# 방금 물어본 추억 (답할 사람별로 몇 개만)
#
# 인터뷰를 시작만 하고 답하지 않으면 그래프는 그대로다. 점수도 그대로이므로
# "인터뷰 시작하기"를 다시 눌러도 같은 추억이 나왔다 — 시드된 그래프는 여덟
# 추억 모두 날짜·장소·설명·사진이 채워져 있어 점수가 거의 같고, 같으면 목록의
# 첫 추억이 늘 이겼다. 그것이 1998 부산 가족여행이라 부산 여행만 반복해 물었다.
#
# 그래서 방금 물어본 추억은 다음 선택에서 뒤로 밀어 둔다. 영구히 빼지는 않는다 —
# 한 추억에 여러 사람의 기억이 겹쳐 쌓이는 것이 이 제품이 하려는 일이다.
_recently_asked: dict[str, list[str]] = {}

# 몇 개를 밀어 둘지. 추억 여덟 개 규모에서 셋을 밀어 두면 누를 때마다 다른
# 추억이 나오고, 네 번째 다음에 처음 것으로 돌아온다.
_RECENT_KEEP = 3


def _recent_key(speaker_id: Optional[str]) -> str:
    """답할 사람별로 따로 센다 — 아빠가 물어본 추억이 딸의 차례를 밀어낼 이유가 없다"""
    return speaker_id or "__anon__"


def remember_asked(speaker_id: Optional[str], event_id: Optional[str]) -> None:
    """이 추억을 방금 물어봤다고 적어 둔다

    인터뷰를 **시작하는** 자리에서 부른다. 답변이 들어오기를 기다리지 않는다 —
    시작만 하고 그만둔 경우가 바로 같은 추억이 반복되던 경우다.
    """
    if not event_id:
        return
    key = _recent_key(speaker_id)
    asked = [e for e in _recently_asked.get(key, []) if e != event_id]
    asked.append(event_id)
    _recently_asked[key] = asked[-_RECENT_KEEP:]


def forget_asked() -> None:
    """밀어 둔 추억을 잊는다 (테스트가 선택 순서를 정할 때 쓴다)"""
    _recently_asked.clear()


def pick_target(speaker_id: Optional[str] = None) -> dict:
    """지금 물어보기 가장 좋은 추억 하나

    speaker_id  지금 화면 앞에서 답할 사람. 인터뷰는 이 사람의 기억을 받아 적는
                자리이므로, 물어볼 추억도 이 사람이 함께 있었던 것에서 고른다.

                이 인자가 없던 동안 여기서 고른 인물(기억을 남기지 않은 참여자)이
                그대로 "인터뷰 대상"이 됐다. 아빠로 로그인한 사람에게 화면이
                "서연님, 그때 기억나세요?"라고 물었다 — 답하는 사람과 질문받는
                사람이 어긋났고, 그러면 답변의 주인이 누구인지도 흐려진다.

    Returns:
        {"event": dict|None, "person_id": str|None, "person_name": str|None,
         "missing": ["날짜", ...]}

        추억이 하나도 없으면 event가 None이다 (인터뷰는 그때 일반 질문을 한다).
    """
    speaker = graph_manager.get_node(speaker_id) if speaker_id else None
    if speaker and speaker.get("node_type") != NodeType.PERSON:
        speaker = None

    recent = frozenset(_recently_asked.get(_recent_key(speaker_id), []))

    if speaker:
        # 그 사람이 함께 있었던 추억 먼저. 없던 자리를 물으면 남는 것은 기억이
        # 아니라 추측이다.
        return (
            _best_event(speaker, only_present=True, recent=recent)
            or _best_event(speaker, only_present=False, recent=recent)
            or _empty_target()
        )

    return _best_event(None, only_present=False, recent=recent) or _empty_target()


def _empty_target() -> dict:
    return {"event": None, "person_id": None, "person_name": None, "missing": []}


def _best_event(
    speaker: Optional[dict],
    only_present: bool,
    recent: Iterable[str] = (),
) -> Optional[dict]:
    """빈 곳이 가장 많은 추억 하나 (없으면 None)

    점수가 같을 때 무엇을 앞에 둘지가 여기서 갈린다. 예전에는 점수만 비교해서
    같으면 목록의 첫 추억이 이겼고, 그래서 auto는 늘 같은 추억을 냈다.
    """
    recent = set(recent)
    best: Optional[dict] = None
    best_rank: Optional[tuple] = None

    for event in graph_manager.get_events():
        connected = graph_manager.get_connected_nodes(event["id"])
        persons = [n for n in connected if n.get("node_type") == NodeType.PERSON]
        memories = [n for n in connected if n.get("node_type") == NodeType.MEMORY]
        media = [n for n in connected if n.get("node_type") == NodeType.MEDIA]

        if only_present and speaker and speaker["id"] not in {p["id"] for p in persons}:
            continue

        missing = []
        score = 0

        if not event.get("date_start"):
            missing.append("날짜")
            score += 3
        if not event.get("location_id"):
            missing.append("장소")
            score += 3
        if not (event.get("description") or "").strip():
            missing.append("어떤 일이었는지")
            score += 2
        if not media:
            missing.append("사진")
            score += 1

        # 아직 기억을 남기지 않은 사람에게 물으면 새로운 관점이 하나 늘어난다
        # (추억을 완성하려는 것이 아니다).
        told = {m.get("contributor_id") for m in memories if m.get("contributor_id")}

        if speaker:
            # 답할 사람이 정해져 있다. 인터뷰 대상은 그 사람이고, 그 사람이 아직
            # 말하지 않은 추억일 때 물어볼 값이 커진다.
            if speaker["id"] not in told:
                score += 4
            person_id = speaker["id"]
            person_name = speaker.get("name")
        else:
            silent = [p for p in persons if p["id"] not in told]
            if silent and len(persons) >= 2:
                score += 4
            person_id = silent[0]["id"] if silent else None
            person_name = silent[0].get("name") if silent else None

        rank = (
            # 방금 물어본 추억은 뒤로 — 이것이 없어서 같은 추억이 반복됐다
            event["id"] not in recent,
            score,
            # 점수까지 같으면 기억이 덜 쌓인 쪽. 목록 순서로 정하지 않는다
            -len(memories),
        )

        if best_rank is None or rank > best_rank:
            best_rank = rank
            best = {
                "event": event,
                "person_id": person_id,
                "person_name": person_name,
                "missing": missing,
            }

    return best
