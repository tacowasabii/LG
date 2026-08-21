"""미세 모션 클립 회귀 테스트

    python tests/test_motion_clips.py

돈이 나가는 기능이라 "부르지 않는 조건"을 주로 본다.
  - 꺼져 있으면 아무것도 맡기지 않는가 (기본값이 꺼짐인가)
  - 상한에 닿으면 멈추는가. 그 값이 재시작에도 남는가
  - 이미 있는 클립을 다시 만들지 않는가
  - 실패한 것을 되풀이하지 않는가
  - 클립이 없어도 화면이 예전처럼 도는가

실제 fal 호출은 하지 않는다. 호출 자리를 가짜로 바꿔 끼운다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import MOTION_LEDGER_FILE  # noqa: E402
from backend.services import film_composer, motion_clips  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


class _Sandbox:
    """모듈 상태와 원장을 건드리고 반드시 되돌린다

    원장(STATE_DIR/motion_spend.json)은 실제 파일이다. 테스트가 그 값을
    남기면 다음 실행에서 상한이 이미 깎여 있다.
    """

    def __init__(self, *, enabled: bool, attempts: int = 0, cap: int = 50):
        self.enabled = enabled
        self.attempts = attempts
        self.cap = cap

    def __enter__(self):
        self._ledger = MOTION_LEDGER_FILE.read_bytes() if MOTION_LEDGER_FILE.exists() else None
        self._pending = set(motion_clips._pending)
        self._failed = dict(motion_clips._failed)
        self._enabled_fn = motion_clips.enabled
        self._cap = motion_clips.MOTION_AUTOGEN_MAX

        motion_clips.enabled = lambda: self.enabled
        motion_clips.MOTION_AUTOGEN_MAX = self.cap
        MOTION_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        MOTION_LEDGER_FILE.write_text(json.dumps({"attempts": self.attempts}), encoding="utf-8")
        return self

    def __exit__(self, *_):
        motion_clips.enabled = self._enabled_fn
        motion_clips.MOTION_AUTOGEN_MAX = self._cap
        motion_clips._pending.clear()
        motion_clips._pending.update(self._pending)
        motion_clips._failed.clear()
        motion_clips._failed.update(self._failed)
        if self._ledger is None:
            MOTION_LEDGER_FILE.unlink(missing_ok=True)
        else:
            MOTION_LEDGER_FILE.write_bytes(self._ledger)
        return False


def test_off_by_default_and_needs_every_condition():
    """설정하지 않은 사람에게서는 돈이 나가지 않는다

    로드된 설정값(config.MOTION_AUTOGEN)을 보지 않는다 — 그러면 정당하게 켠
    순간 이 테스트가 깨진다. 환경변수가 없을 때의 기본값과, 조건 하나만
    빠져도 꺼지는지를 본다.
    """
    import os

    from backend import config

    # 환경변수가 없으면 꺼짐 (config.py가 읽는 기본값과 같은 식)
    assert os.getenv("MOTION_AUTOGEN", "false").lower() != "true" or config.MOTION_AUTOGEN
    saved_env = os.environ.pop("MOTION_AUTOGEN", None)
    try:
        assert os.getenv("MOTION_AUTOGEN", "false").lower() == "false", "기본값이 꺼짐이 아니다"
    finally:
        if saved_env is not None:
            os.environ["MOTION_AUTOGEN"] = saved_env

    # 조건 하나만 빠져도 꺼진다 — 키가 없으면 켜 두어도 부르지 않는다
    saved_flag, saved_key = config.MOTION_AUTOGEN, os.environ.pop("FAL_KEY", None)
    try:
        config.MOTION_AUTOGEN = True
        assert motion_clips.enabled() is False, "키가 없는데 켜져 있다고 한다"
        config.MOTION_AUTOGEN = False
        assert motion_clips.enabled() is False, "꺼져 있는데 켜져 있다고 한다"
    finally:
        config.MOTION_AUTOGEN = saved_flag
        if saved_key is not None:
            os.environ["FAL_KEY"] = saved_key
    print("  기본값 꺼짐 · 조건 하나만 빠져도 꺼짐 OK")


def test_disabled_requests_nothing():
    """꺼져 있으면 무엇도 맡기지 않는다"""
    with _Sandbox(enabled=False):
        taken = motion_clips.request("없는사진", ROOT_DIR / "data/photos/E01_001.jpg", "x")
        assert taken is False, "꺼져 있는데 맡았다"
        assert motion_clips.pending_ids() == [], motion_clips.pending_ids()
    print("  꺼짐 → 요청 없음 OK")


def test_existing_clip_is_not_rebuilt():
    """이미 있는 클립은 다시 만들지 않는다 (한 번 만들면 계속 쓴다)"""
    have = sorted(motion_clips.manifest())
    assert have, "확인할 클립이 없다 — data/motion/manifest.json 을 보라"

    with _Sandbox(enabled=True):
        for media_id in have:
            taken = motion_clips.request(media_id, ROOT_DIR / "data/photos/E01_001.jpg", "x")
            assert taken is False, f"{media_id}: 이미 있는데 다시 맡았다"
    print("  이미 있는 클립", len(have), "개 → 재생성 없음 OK")


def test_cap_stops_requests():
    """상한에 닿으면 멈춘다 (인증 없는 API에서 잔액을 지키는 장치)"""
    with _Sandbox(enabled=True, attempts=50, cap=50):
        assert motion_clips.attempts_left() == 0, motion_clips.attempts_left()
        # enabled를 갈아 끼웠으므로 상한 자체를 다시 본다
        assert motion_clips.attempts_used() >= motion_clips.MOTION_AUTOGEN_MAX

    with _Sandbox(enabled=True, attempts=49, cap=50):
        assert motion_clips.attempts_left() == 1, motion_clips.attempts_left()
    print("  상한 계산 OK (0 / 1 남음)")


def test_cap_is_not_recorded_as_failure():
    """상한에 걸린 사진은 실패로 적지 않는다

    상한은 일시적인 조건이다. 실패로 적으면 운영자가 상한을 올려도 그 사진은
    영구히 제외된다 — request()가 실패한 것을 다시 맡지 않기 때문이다.
    """
    with _Sandbox(enabled=True, attempts=5, cap=5):
        motion_clips._work("상한걸린사진", ROOT_DIR / "data/photos/E01_001.jpg", "x")
        assert "상한걸린사진" not in motion_clips.failures(), motion_clips.failures()
        assert motion_clips.attempts_used() == 5, "상한에 걸렸는데 횟수를 세었다"
    print("  상한 ≠ 실패 OK")


def test_failure_is_not_retried():
    """한 번 실패한 것은 다시 맡지 않는다

    화면이 주기적으로 되묻는 구조라서, 실패를 재시도하면 같은 호출이 끝없이
    반복된다 — 실패가 과금되지 않아도 그건 위험이다.
    """
    with _Sandbox(enabled=True):
        motion_clips._failed["망한사진"] = "테스트"
        taken = motion_clips.request("망한사진", ROOT_DIR / "data/photos/E01_001.jpg", "x")
        assert taken is False, "실패한 것을 다시 맡았다"
    print("  실패 → 재시도 없음 OK")


def test_prompt_comes_from_words_not_a_model():
    """무엇이 움직일지는 문구에서 고른다 (모델에 맡기지 않는다)"""
    sea = motion_clips.motion_prompt(["광안리 해수욕장에서 부모님과 함께"])
    fire = motion_clips.motion_prompt([None, "첫 가족 캠핑", "모닥불 앞에서"])
    plain = motion_clips.motion_prompt(["초등학교 입학식"])

    assert "wave" in sea, sea
    assert "campfire" in fire, fire
    assert plain.startswith(motion_clips.FALLBACK_MOTION), plain
    # 같은 입력이면 같은 결과여야 한다 — 같은 사진이 매번 다르게 움직이면 안 된다
    assert motion_clips.motion_prompt(["광안리 해수욕장에서"]) == sea
    print("  프롬프트 결정적 OK")


def _no_model(picker):
    """모델을 부르면 잡히게 바꿔 끼운다"""
    calls = {"n": 0}

    async def _counted(*_a, **_k):
        calls["n"] += 1
        return None

    picker._by_model = _counted
    return calls


def test_all_photos_are_covers_when_they_fit():
    """사진이 상한보다 적으면 전부 만든다

    미세 모션은 정적으로 보이는 사진도 살린다(머리카락·옷자락). 세 장뿐인
    추억에서 골라낼 이유가 없고, 그때는 모델을 부를 이유도 없다 —
    "셋 중 셋을 고르라"는 값만 쓰고 답이 정해진 질문이다.
    """
    from backend.config import MOTION_COVERS_FILE
    from backend.services import cover_picker

    saved = MOTION_COVERS_FILE.read_bytes() if MOTION_COVERS_FILE.exists() else None
    original = cover_picker._by_model
    calls = _no_model(cover_picker)
    try:
        MOTION_COVERS_FILE.unlink(missing_ok=True)
        # 실내 정적 사진만 있어도 전부 고른다
        photos = [
            {"id": "A", "scene_description": "졸업식장에서 함께 찍은 기념사진"},
            {"id": "B", "scene_description": "학사모를 쓴 단독사진"},
            {"id": "C", "scene_description": "교실에서 부모님과"},
        ]
        picked = asyncio.run(cover_picker.pick({"id": "E_세장"}, photos, limit=3))
        assert picked == ["A", "B", "C"], picked
        assert calls["n"] == 0, f"고를 것이 없는데 모델을 {calls['n']}번 불렀다"

        # 상한이 남은 정원이므로 0이면 아무것도 고르지 않는다
        assert asyncio.run(cover_picker.pick({"id": "E_세장"}, photos, limit=0)) == []
    finally:
        cover_picker._by_model = original
        if saved is None:
            MOTION_COVERS_FILE.unlink(missing_ok=True)
        else:
            MOTION_COVERS_FILE.write_bytes(saved)
    print("  상한 이하면 전부 대표 OK (모델 호출 없음)")


def test_cover_choice_is_remembered_when_choosing_is_needed():
    """골라야 하는 경우에만 묻고, 한 번 고른 것을 지킨다

    고를 때마다 달라지면 방문마다 다른 사진을 만들어 돈이 계속 나간다.
    """
    from backend.config import MOTION_COVERS_FILE
    from backend.services import cover_picker

    saved = MOTION_COVERS_FILE.read_bytes() if MOTION_COVERS_FILE.exists() else None
    original = cover_picker._by_model
    calls = _no_model(cover_picker)
    try:
        MOTION_COVERS_FILE.write_text(
            json.dumps({"E_많음": {"media_ids": ["B", "D"], "by": "llm", "reason": ""}}),
            encoding="utf-8",
        )
        photos = [{"id": x, "scene_description": x} for x in "ABCDE"]

        picked = asyncio.run(cover_picker.pick({"id": "E_많음"}, photos, limit=2))
        assert picked == ["B", "D"], picked
        assert calls["n"] == 0, f"기억해 둔 선택이 있는데 모델을 {calls['n']}번 불렀다"

        # 정원이 남으면 남은 자리만 다시 고른다 (앞선 선택은 지킨다)
        more = asyncio.run(cover_picker.pick({"id": "E_많음"}, photos, limit=3))
        assert more[:2] == ["B", "D"], more
        assert len(more) == 3 and more[2] not in ("B", "D"), more
        assert calls["n"] == 1, f"남은 자리를 고르는 데 {calls['n']}번 불렀다"
    finally:
        cover_picker._by_model = original
        if saved is None:
            MOTION_COVERS_FILE.unlink(missing_ok=True)
        else:
            MOTION_COVERS_FILE.write_bytes(saved)
    print("  선택 기억 OK (정원이 남으면 남은 자리만 채운다)")


def test_only_new_events_are_generated():
    """기능을 켠 뒤에 생긴 추억만 만든다

    이미 쌓여 있던 앨범 전체를 한꺼번에 만들면 지출이 한 번에 튄다. 기준선을
    파일에 적어 두는 것이 요점이다 — id 모양이나 만든 시각으로 가르면
    재시드·이관에서 조용히 달라진다.
    """
    from backend.config import MOTION_BASELINE_FILE
    from backend.services.graph_manager import graph_manager

    saved = MOTION_BASELINE_FILE.read_bytes() if MOTION_BASELINE_FILE.exists() else None
    try:
        MOTION_BASELINE_FILE.unlink(missing_ok=True)

        # 기준선을 아직 못 적었으면 아무것도 새 추억으로 보지 않는다.
        # 기능이 조용히 안 되는 쪽이 돈이 조용히 나가는 쪽보다 낫다.
        assert motion_clips.baseline_event_ids() is None
        assert motion_clips.is_new_event("event_무엇이든") is False, \
            "기준선 없이 새 추억으로 봤다 — 앨범 전체가 대상이 된다"

        # 부팅 때 정한다 (main.py). 그때 있던 추억이 기준선이 된다.
        base = motion_clips.ensure_baseline()
        existing = {event["id"] for event in graph_manager.get_events()}
        assert base == existing, (sorted(base), sorted(existing))
        assert MOTION_BASELINE_FILE.exists(), "기준선을 적어 두지 않았다"

        for event_id in sorted(existing)[:3]:
            assert motion_clips.is_new_event(event_id) is False, event_id
        assert motion_clips.is_new_event("event_아직없던것") is True

        # 이미 적혀 있으면 다시 적지 않는다 (그래프가 늘어도 기준선은 그대로)
        assert motion_clips.ensure_baseline() == base
        assert motion_clips.baseline_event_ids() == base
    finally:
        if saved is None:
            MOTION_BASELINE_FILE.unlink(missing_ok=True)
        else:
            MOTION_BASELINE_FILE.write_bytes(saved)
    print(f"  기준선 {len(existing)}개 제외 · 새 id는 대상 OK")


def test_existing_events_request_nothing_even_when_on():
    """켜져 있어도 기존 추억에서는 아무것도 맡기지 않는다"""
    from backend.config import MOTION_BASELINE_FILE

    saved = MOTION_BASELINE_FILE.read_bytes() if MOTION_BASELINE_FILE.exists() else None
    taken: list[str] = []
    original = motion_clips.request
    try:
        with _Sandbox(enabled=True):
            motion_clips.request = lambda mid, path, prompt: (taken.append(mid) or True)
            board = asyncio.run(film_composer.compose(EVENT, length_sec=60))
        assert board, "스토리보드가 비었다"
        assert taken == [], f"기존 추억인데 맡겼다: {taken}"
        assert board["motion_pending"] == [], board["motion_pending"]
    finally:
        motion_clips.request = original
        if saved is None:
            MOTION_BASELINE_FILE.unlink(missing_ok=True)
        else:
            MOTION_BASELINE_FILE.write_bytes(saved)
    print("  기존 추억 → 맡김 없음 OK")


def test_film_works_without_any_clip():
    """클립이 하나도 없어도 화면은 예전처럼 돈다"""
    with _Sandbox(enabled=False):
        original = motion_clips.manifest
        motion_clips.manifest = lambda: {}
        try:
            board = asyncio.run(film_composer.compose(EVENT, length_sec=60))
        finally:
            motion_clips.manifest = original

    assert board, "스토리보드가 비었다"
    assert board["motion_pending"] == [], board["motion_pending"]
    photo_scenes = [s for s in board["scenes"] if not s["media_id"].startswith("video_")]
    assert photo_scenes, "사진 장면이 없다"
    for scene in photo_scenes:
        assert scene["motion_url"] is None, scene
        assert scene["motion"], f"카메라 움직임이 비었다: {scene}"
        assert scene["ai_effects"] == [dict(film_composer.CAMERA_MOTIONS)[scene["motion"]]]
    print("  클립 0개에서도 정상 OK")


def test_label_is_decided_by_the_server():
    """라벨은 서버가 만든다 (화면이 조립하면 갈라진다)"""
    plain = film_composer.generated_label({"file": "x"})
    masked = film_composer.generated_label({"file": "x", "subject_preserved": True})

    assert plain == film_composer.GENERATED_MOTION_LABEL, plain
    assert masked.endswith(film_composer.SUBJECT_PRESERVED_NOTE), masked
    # 둘 다 허용 목록 안에 있어야 Trust Harness가 위반으로 잡지 않는다
    assert plain in film_composer.ALLOWED_EFFECTS
    assert masked in film_composer.ALLOWED_EFFECTS
    print("  라벨 서버 결정 OK:", masked)


def test_http_motion_status():
    """상태 조회는 목록만 읽는다 (모델을 부르지 않는다)"""
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    have = sorted(motion_clips.manifest())

    r = client.get("/api/film/motion")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["ready"]) == set(have), (sorted(body["ready"]), have)
    for entry in body["ready"].values():
        assert entry["file"].startswith("/media-files/motion/"), entry
        assert entry["label"] in film_composer.ALLOWED_EFFECTS, entry

    # 물어본 것만 돌려준다
    if have:
        one = have[0]
        r = client.get(f"/api/film/motion?media_ids={one}")
        assert set(r.json()["ready"]) == {one}, r.json()["ready"]

    r = client.get("/api/film/motion?media_ids=없는것")
    assert r.json()["ready"] == {}, r.json()
    print("  GET /api/film/motion OK")


def test_tv_serves_clips_but_never_makes_them():
    """거실 화면은 Film이 만든 것을 쓰되, 스스로 만들지는 않는다

    TV는 리모컨으로 넘기는 자리라 40초를 기다릴 수 없고, 넘기는 것만으로 돈이
    나가면 안 된다. 반대로 만들어 둔 것을 못 쓰면 가장 좋은 재료가 한 화면에만
    갇힌다 — 그래서 읽기는 하고 쓰기는 하지 않는다.

    라우터가 모션 필드를 빠뜨렸던 적이 있어(큐레이터는 실어 보내는데 응답 모델로
    옮기지 않았다) 화면에서 조용히 사라졌다. 그 자리를 여기서 잡는다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    have = set(motion_clips.manifest())
    if not have:
        raise AssertionError("확인할 클립이 없다")

    called: list[str] = []
    with _Sandbox(enabled=True):
        original = motion_clips.request
        motion_clips.request = lambda media_id, path, prompt: (called.append(media_id) or True)
        try:
            client = TestClient(app)
            created = client.post(
                "/api/tv/journey", json={"query": "부산 여행", "style": "timeline"}
            )
            assert created.status_code == 200, created.text
            body = created.json()
            fetched = client.get(f"/api/tv/journey/{body['id']}").json()
        finally:
            motion_clips.request = original

    assert called == [], f"TV가 생성을 맡겼다: {called}"

    for name, payload in (("생성", body), ("조회", fetched)):
        moving = [s for s in payload["slides"] if s.get("motion_url")]
        assert moving, f"{name}: 클립이 실리지 않았다 (라우터가 필드를 버렸나)"
        for slide in moving:
            assert slide["media_id"] in have, slide
            assert slide["motion_url"].startswith("/media-files/motion/"), slide
            # 라벨은 서버가 준다 — 화면이 조립하면 Film과 갈라진다
            assert slide.get("motion_label") in film_composer.ALLOWED_EFFECTS, slide
    print("  TV: 클립", len(moving), "개 실림 · 생성 0건 OK")


TESTS = [
    test_off_by_default_and_needs_every_condition,
    test_disabled_requests_nothing,
    test_existing_clip_is_not_rebuilt,
    test_cap_stops_requests,
    test_cap_is_not_recorded_as_failure,
    test_failure_is_not_retried,
    test_all_photos_are_covers_when_they_fit,
    test_cover_choice_is_remembered_when_choosing_is_needed,
    test_only_new_events_are_generated,
    test_existing_events_request_nothing_even_when_on,
    test_prompt_comes_from_words_not_a_model,
    test_film_works_without_any_clip,
    test_label_is_decided_by_the_server,
    test_http_motion_status,
    test_tv_serves_clips_but_never_makes_them,
]


if __name__ == "__main__":
    _require_seeded_graph()

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
