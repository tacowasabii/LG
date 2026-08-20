"""사건 요약 API · 음성 · 화자 귀속 회귀 테스트

    python tests/test_events_and_voice.py

화면이 목데이터로 메우던 것들을 서버가 실제로 내려주는지 본다.
  - 사건 요약에 장소 좌표·참여자·썸네일·확인 상태가 들어오는가
  - 음성 미디어가 화자·사건과 이어지고 목록에 파형까지 실려 오는가
  - 인터뷰 답변이 "화면에서 고른 사람"의 기억으로 저장되는가

그래프를 실제로 변경하므로 만든 노드는 끝에서 지운다. 데모 데이터를 더럽히지 않는다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import (  # noqa: E402
    Confidence,
    Edge,
    MediaNode,
    MediaType,
    NodeType,
    RelationType,
    SourceType,
)
from backend.routers.graph import list_events  # noqa: E402
from backend.routers.media import _parse_waveform, _to_list_item, list_media  # noqa: E402
from backend.services import interview_engine  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

EVENT = "E01"  # 1998 부산 가족여행
SPEAKER = "P02"  # 박서연 (시드에서 이 사건의 기억은 P01만 남겼다)

# 이 테스트가 만든 노드
_created: list[str] = []


def _require_seeded_graph():
    if len(graph_manager.get_events()) < 8 or len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _cleanup():
    for node_id in _created:
        graph_manager.delete_node(node_id)
    _created.clear()


def _make_voice_node() -> MediaNode:
    """녹음 업로드가 만드는 것과 같은 모양의 음성 노드를 그래프에 넣는다

    업로드 라우터는 파일 저장과 UploadFile이 필요해 여기서는 그 뒤 단계만 검증한다.
    """
    node = MediaNode(
        media_type=MediaType.AUDIO,
        file_path="/media-files/test-voice.webm",
        original_filename="test-voice.webm",
        duration_sec=12.4,
        waveform=[0.2, 0.8, 0.5],
        transcript="그때 하늘이가 바다를 처음 봤어요.",
        speaker_id=SPEAKER,
        confidence=Confidence.CONFIRMED,
        source=SourceType.INTERVIEW,
    )
    graph_manager.add_media(node)
    _created.append(node.id)

    graph_manager.add_edge(Edge(source=node.id, target=SPEAKER, relation=RelationType.NARRATED_BY))
    graph_manager.add_edge(
        Edge(source=node.id, target=EVENT, relation=RelationType.CAPTURED_DURING)
    )
    return node


# --- 사건 요약 ---------------------------------------------------------------


def test_event_summary_has_place_and_participants():
    """지도가 점을 찍을 수 있어야 한다 — 이름만으로는 못 찍는다"""
    events = asyncio.run(list_events())
    target = next(e for e in events if e.id == EVENT)

    assert target.place is not None, "장소가 비어 있다"
    assert target.place.lat is not None and target.place.lng is not None, "좌표가 없다"
    assert len(target.participants) >= 3, target.participants
    assert all(p.name for p in target.participants), "참여자 이름이 비어 있다"
    print("  사건 요약 장소·참여자 OK:", target.place.name, len(target.participants), "명")


def test_event_summary_has_thumbs_and_state():
    """타임라인 미리보기와 기억 상태 뱃지가 목데이터 없이 그려져야 한다"""
    events = asyncio.run(list_events())
    target = next(e for e in events if e.id == EVENT)

    assert len(target.media_thumbs) > 0, "썸네일이 없다"
    assert all(path.startswith("/media-files/") for path in target.media_thumbs), target.media_thumbs
    assert target.state in ("alone", "shared", "varied"), target.state
    assert target.memory_count >= 1, target.memory_count
    print("  썸네일", len(target.media_thumbs), "장 · 상태", target.state)


def test_event_summary_counts_voice_separately():
    """음성은 사진 미리보기에 섞이지 않고 voice_count로 센다"""
    node = _make_voice_node()
    try:
        events = asyncio.run(list_events())
        target = next(e for e in events if e.id == EVENT)

        assert target.voice_count >= 1, "음성이 세어지지 않았다"
        assert node.file_path not in target.media_thumbs, "음성이 썸네일에 섞였다"
        print("  음성", target.voice_count, "개 · 썸네일에 섞이지 않음")
    finally:
        _cleanup()


# --- 음성 목록 ---------------------------------------------------------------


def test_voice_list_carries_playback_fields():
    """재생 화면이 한 번의 목록 조회로 그릴 수 있어야 한다"""
    node = _make_voice_node()
    try:
        # person_id를 생략하면 FastAPI의 Query 기본값 객체가 넘어가 참으로 평가된다.
        # 라우터를 직접 부를 때는 None을 명시해야 HTTP 호출과 같은 경로를 탄다.
        items = asyncio.run(list_media(media_type="audio", person_id=None))
        found = next(i for i in items if i.id == node.id)

        assert found.duration_sec == 12.4, found.duration_sec
        assert found.waveform == [0.2, 0.8, 0.5], found.waveform
        assert found.transcript, "전사문이 비었다"
        assert found.speaker_name == "박서연", found.speaker_name
        assert found.event_id == EVENT, found.event_id
        assert found.event_title, "사건 제목이 비었다"
        print("  음성 목록 화자·사건·파형 OK:", found.speaker_name, found.event_title)
    finally:
        _cleanup()


def test_voice_list_filters_by_speaker():
    """인물 상세는 그 사람이 '말한' 음성만 보여준다 (사진에 찍힌 것과 다른 관계)"""
    node = _make_voice_node()
    try:
        mine = asyncio.run(list_media(media_type="audio", person_id=SPEAKER))
        others = asyncio.run(list_media(media_type="audio", person_id="P04"))

        assert any(i.id == node.id for i in mine), "화자로 조회했는데 안 나온다"
        assert not any(i.id == node.id for i in others), "다른 사람 것으로 잡혔다"
        print("  화자 필터 OK")
    finally:
        _cleanup()


def test_waveform_parser_rejects_garbage():
    """파형이 깨져도 업로드는 살아야 한다 (그림이 없을 뿐 음성은 들린다)"""
    assert _parse_waveform("not json") == []
    assert _parse_waveform(json.dumps({"a": 1})) == []
    assert _parse_waveform(json.dumps([2.5, -1, 0.5, "x"])) == [1.0, 0.0, 0.5]
    print("  파형 파서 방어 OK")


def test_photo_list_item_has_no_voice_fields():
    """사진 항목에 음성 칸이 헛되게 채워지지 않는다"""
    photo = graph_manager.get_node("E01_001")
    assert photo, "시드 사진이 없다"

    item = _to_list_item(photo)
    assert item.speaker_name is None and item.event_id is None, "사진에 음성 정보가 붙었다"
    print("  사진 항목 OK")


# --- 화자 귀속 ---------------------------------------------------------------


def test_interview_attributes_answer_to_selected_speaker():
    """화면에서 고른 사람의 기억으로 저장된다 (Gap이 지목한 인물보다 우선)"""
    session = {
        "contributor_id": "P01",  # Gap이 지목한 인물
        "target_node": graph_manager.get_node(EVENT),
        "answers": [],
    }

    updated = asyncio.run(
        interview_engine._process_answer_to_graph(session, "파도가 무서워서 다리를 붙잡았어요.", speaker_id=SPEAKER)
    )
    memory_id = updated[0]
    _created.append(memory_id)

    try:
        memory = graph_manager.get_node(memory_id)
        assert memory["contributor_id"] == SPEAKER, memory["contributor_id"]

        edges = graph_manager.get_all_edges()
        assert any(
            e["source"] == SPEAKER and e["target"] == memory_id
            and e["relation"] == RelationType.REMEMBERS
            for e in edges
        ), "REMEMBERS 엣지가 없다"
        assert any(
            e["source"] == memory_id and e["target"] == EVENT and e["relation"] == RelationType.ABOUT
            for e in edges
        ), "ABOUT 엣지가 없다"
        print("  화자 귀속 OK:", memory["contributor_id"])
    finally:
        _cleanup()


def test_interview_links_voice_as_evidence():
    """말로 답하면 기억이 원본 음성으로 되짚을 수 있다 (기획안 출처 보존)"""
    voice = _make_voice_node()
    session = {
        "contributor_id": None,
        "target_node": graph_manager.get_node(EVENT),
        "answers": [],
    }

    updated = asyncio.run(
        interview_engine._process_answer_to_graph(
            session,
            "그때 하늘이가 바다를 처음 봤어요.",
            speaker_id=SPEAKER,
            audio_media_id=voice.id,
        )
    )
    memory_id = updated[0]
    _created.append(memory_id)

    try:
        assert voice.id in updated, "음성이 업데이트 목록에 없다"
        edges = graph_manager.get_all_edges()
        assert any(
            e["source"] == memory_id
            and e["target"] == voice.id
            and e["relation"] == RelationType.EVIDENCED_BY
            for e in edges
        ), "EVIDENCED_BY 엣지가 없다"
        print("  기억 → 음성 근거 연결 OK")
    finally:
        _cleanup()


def test_voice_list_carries_the_question_it_answered():
    """음성 목록이 그 목소리가 답한 질문을 함께 내려준다

    질문은 음성 노드가 아니라 그 답을 남긴 기억에 있다 (EVIDENCED_BY). 답만
    보여주면 "모르겠어요" 한 마디가 무슨 이야기인지 읽을 수 없다 — 채팅 답변
    아래 붙는 클립에서 특히 그렇다.
    """
    voice = _make_voice_node()
    session = {
        "contributor_id": None,
        "target_node": graph_manager.get_node(EVENT),
        "answers": [],
    }

    updated = asyncio.run(
        interview_engine._process_answer_to_graph(
            session,
            "모르겠어요",
            speaker_id=SPEAKER,
            audio_media_id=voice.id,
            question="광안리 해수욕장에서 뭘 하고 노셨어요?",
        )
    )
    _created.append(updated[0])

    try:
        item = _to_list_item(graph_manager.get_node(voice.id))
        assert item.question == "광안리 해수욕장에서 뭘 하고 노셨어요?", (
            f"질문이 실려 오지 않음: {item.question!r}"
        )
        print("  음성 목록에 질문 실림 OK")
    finally:
        _cleanup()


def test_photo_list_item_has_no_question():
    """사진에는 질문이 붙지 않는다 (음성만 답이다)"""
    photo = graph_manager.get_node("MED001") or next(
        (m for m in graph_manager.get_media_nodes() if m.get("media_type") == "photo"), None
    )
    assert photo, "시드에 사진이 없다"
    assert _to_list_item(photo).question is None


def test_unknown_speaker_falls_back_to_question_target():
    """없는 사람 id가 와도 기억을 잃지 않는다

    인터뷰가 물어볼 대상을 고를 때 함께 지목한 인물(question_picker)에게 귀속한다.
    """
    session = {
        "contributor_id": "P01",
        "target_node": graph_manager.get_node(EVENT),
        "answers": [],
    }

    updated = asyncio.run(
        interview_engine._process_answer_to_graph(session, "기억이 잘 안 나요.", speaker_id="P99")
    )
    memory_id = updated[0]
    _created.append(memory_id)

    try:
        memory = graph_manager.get_node(memory_id)
        assert memory["contributor_id"] == "P01", memory["contributor_id"]
        print("  없는 화자 폴백 OK")
    finally:
        _cleanup()


# --- 실제 HTTP 경로 -----------------------------------------------------------


def test_http_endpoints_serialize():
    """응답 모델이 실제 HTTP에서도 통째로 나가는지 본다

    라우터 함수를 직접 부르면 FastAPI의 의존성 기본값과 응답 모델 직렬화를
    건너뛴다. 화면이 실제로 받는 모양은 여기서만 확인된다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    node = _make_voice_node()
    try:
        with TestClient(app) as client:
            events = client.get("/api/graph/events")
            assert events.status_code == 200, events.text
            target = next(e for e in events.json() if e["id"] == EVENT)
            assert target["place"]["lat"], target["place"]
            assert target["participants"], target
            assert target["state"], target
            assert target["voice_count"] >= 1, target

            audios = client.get("/api/media", params={"media_type": "audio"})
            assert audios.status_code == 200, audios.text
            found = next(i for i in audios.json() if i["id"] == node.id)
            assert found["speaker_name"] == "박서연", found
            assert found["waveform"] == [0.2, 0.8, 0.5], found
            assert found["file_path"].startswith("/media-files/"), found
        print("  HTTP 응답 OK: /api/graph/events · /api/media?media_type=audio")
    finally:
        _cleanup()


TESTS = [
    test_event_summary_has_place_and_participants,
    test_event_summary_has_thumbs_and_state,
    test_event_summary_counts_voice_separately,
    test_voice_list_carries_playback_fields,
    test_voice_list_filters_by_speaker,
    test_waveform_parser_rejects_garbage,
    test_photo_list_item_has_no_voice_fields,
    test_photo_list_item_has_no_question,
    test_interview_attributes_answer_to_selected_speaker,
    test_interview_links_voice_as_evidence,
    test_voice_list_carries_the_question_it_answered,
    test_unknown_speaker_falls_back_to_question_target,
    test_http_endpoints_serialize,
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
        except Exception as e:  # 연결 실패 등도 실패로 본다
            failures += 1
            print(f"ERROR {test.__name__}: {type(e).__name__} {e}")
        finally:
            _cleanup()

    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} 통과")
    sys.exit(1 if failures else 0)
