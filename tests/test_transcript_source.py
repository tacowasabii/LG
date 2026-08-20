"""전사문 출처 회귀 테스트 (기계가 옮긴 글 vs 사람이 쓴 글)

    python tests/test_transcript_source.py

브라우저 음성 인식(lib/transcriber.ts)이 붙으면서 transcript에 두 종류가 섞여
들어온다. 사람이 적은 문장과, 기계가 옮기고 아무도 고치지 않은 문장이다.

둘을 구분하지 않으면 신뢰도 표시가 거짓이 된다 — 잘못 들은 문장이 "가족이 확인한
기억"으로 읽힌다. 그래서 목소리의 출처(source)와 그 글의 출처(transcript_source)를
다른 축으로 둔다. 여기서 재는 것은 그 분리가 실제로 지켜지는지다.

  - 화면이 ai_stt라고 밝히면 그렇게 남는가
  - 안 밝히면 사람이 쓴 것으로 보는가
  - 화면이 엉뚱한 값을 보내면 사람이 쓴 것으로 떨어지는가 (주장을 그대로 믿지 않는다)
  - 목소리 자체의 신뢰도는 글의 출처와 무관하게 유지되는가
  - 화면이 받는 응답(/api/media)에 그 값이 실려 나가는가

업로드가 실제 파일을 만들므로 끝에서 지운다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import MEDIA_DIR  # noqa: E402
from backend.models.graph_models import Confidence, SourceType  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

SPEAKER = "P02"  # 박서연

# 업로드가 만든 노드·파일을 지우기 위해 모아 둔다
_created: list[str] = []


def _require_seeded_graph():
    if len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _upload(client, filename: str, transcript: str, transcript_source=None) -> dict:
    """녹음 업로드를 화면과 같은 모양(multipart)으로 흉내 낸다"""
    data = {
        "duration_sec": "3.4",
        "waveform": "[0.2, 0.8, 0.5]",
        "transcript": transcript,
        "speaker_id": SPEAKER,
    }
    if transcript_source is not None:
        data["transcript_source"] = transcript_source

    response = client.post(
        "/api/media/upload",
        files={"file": (filename, b"fake-audio-bytes", "audio/webm")},
        data=data,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    _created.append(body["id"])
    return body


def _cleanup():
    for media_id in _created:
        node = graph_manager.get_node(media_id)
        if node:
            name = Path(node.get("file_path", "")).name
            if name:
                path = MEDIA_DIR / name
                if path.exists():
                    path.unlink()
            graph_manager.delete_node(media_id)
    _created.clear()


def test_machine_transcript_is_marked_ai_stt():
    """화면이 ai_stt라고 밝히면 그렇게 남는다"""
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "stt-1.webm", "그날 비가 왔어요", SourceType.AI_STT.value)

        node = graph_manager.get_node(body["id"])
        assert node["transcript"] == "그날 비가 왔어요", node
        assert node["transcript_source"] == SourceType.AI_STT, node["transcript_source"]
        print("  기계가 옮긴 글 → ai_stt OK")
    finally:
        _cleanup()


def test_typed_transcript_is_user_input():
    """출처를 안 보내면 사람이 쓴 것으로 본다 (기존 화면 경로)"""
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "typed-1.webm", "해운대에서 찍었어요")

        node = graph_manager.get_node(body["id"])
        assert node["transcript_source"] == SourceType.USER_INPUT, node["transcript_source"]
        print("  사람이 적은 글 → user_input OK")
    finally:
        _cleanup()


def test_unexpected_source_value_falls_back_to_user_input():
    """화면이 주장하는 값을 그대로 믿지 않는다

    ai_stt 말고 다른 것이 오면 사람이 쓴 것으로 떨어진다. 남이 보낸 값으로
    신뢰도를 높이는 길을 열어 두지 않는다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            confirmed = _upload(client, "bogus-1.webm", "확정된 문장", "confirmed")
            garbage = _upload(client, "bogus-2.webm", "이상한 값", "무엇이든")

        for body in (confirmed, garbage):
            node = graph_manager.get_node(body["id"])
            assert node["transcript_source"] == SourceType.USER_INPUT, node["transcript_source"]
        print("  엉뚱한 출처 → user_input OK")
    finally:
        _cleanup()


def test_voice_confidence_is_independent_of_transcript_source():
    """글이 기계 것이어도 목소리의 신뢰도는 그대로다

    두 축이 섞이면 "AI가 옮긴 글이라 이 녹음은 못 믿는다"가 되어 버린다.
    말한 사람이 분명한 녹음은 확정된 기록이다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "stt-2.webm", "광안리였어요", SourceType.AI_STT.value)

        node = graph_manager.get_node(body["id"])
        assert node["source"] == SourceType.INTERVIEW, node["source"]
        assert node["confidence"] == Confidence.CONFIRMED, node["confidence"]
        assert node["speaker_id"] == SPEAKER, node
        print("  목소리 신뢰도와 글 출처가 분리됨 OK")
    finally:
        _cleanup()


def test_media_list_exposes_transcript_source():
    """화면이 받는 응답에 실려 나간다 (안 나가면 밝힐 수 없다)"""
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "stt-3.webm", "그때 사진 찍었죠", SourceType.AI_STT.value)

            audios = client.get("/api/media", params={"media_type": "audio"})
            assert audios.status_code == 200, audios.text
            found = next(i for i in audios.json() if i["id"] == body["id"])

        assert found["transcript_source"] == SourceType.AI_STT.value, found
        print("  /api/media 응답에 transcript_source 실림 OK")
    finally:
        _cleanup()


def test_webm_recording_is_stored_as_audio():
    """브라우저 녹음(.webm)이 음성으로 저장된다

    .webm은 영상 확장자와 같다. 확장자만 보면 목소리가 영상 노드가 되어
    음성 목록에서 통째로 빠지고 파형도 쓰이지 않는다. 브라우저가 보내는
    audio/webm을 믿어야 갈린다.
    """
    from backend.services.media_analyzer import detect_media_type

    from backend.models.graph_models import MediaType

    assert detect_media_type("voice-1.webm", "audio/webm") == MediaType.AUDIO
    assert detect_media_type("clip.webm", "video/webm") == MediaType.VIDEO
    # 형식을 못 받았거나 이상하면 확장자로 떨어진다
    assert detect_media_type("clip.webm", None) == MediaType.VIDEO
    assert detect_media_type("photo.jpg", "application/octet-stream") == MediaType.PHOTO
    assert detect_media_type("memo.m4a", "") == MediaType.AUDIO
    print("  .webm 음성/영상 구분 OK")


def test_uploaded_recording_lands_in_voice_list():
    """올린 녹음이 실제로 음성 목록에 나온다 (분류가 끝까지 이어지는지)"""
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "voice-list.webm", "그때 다 모였어요", SourceType.AI_STT.value)
            assert body["media_type"] == "audio", body

            audios = client.get("/api/media", params={"media_type": "audio"})
            ids = [i["id"] for i in audios.json()]

        assert body["id"] in ids, ids
        print("  올린 녹음이 음성 목록에 도달 OK")
    finally:
        _cleanup()


def _main():
    _require_seeded_graph()
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}\n{e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__} {e}")
        finally:
            _cleanup()

    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
