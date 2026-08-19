"""Media Router - 업로드, 목록, 상세, 삭제"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from typing import Optional
import json
import shutil
from pathlib import Path

from backend.config import MEDIA_DIR
from backend.models.schemas import MediaUploadResponse, MediaListItem, MediaDetail, MediaSupplementRequest
from backend.models.graph_models import (
    NodeType, MediaType, RelationType, Edge, Confidence, SourceType,
)
from backend.services.media_analyzer import analyze_media, generate_thumbnail
from backend.services.event_resolver import resolve_event_for_media
from backend.services.graph_manager import graph_manager
from backend.services import visibility

router = APIRouter()


@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    # --- 음성 녹음이 함께 보내는 정보 ---
    # 브라우저가 녹음 직후 길이와 파형을 계산해 보낸다. 서버에 오디오 디코더를
    # 두지 않기 위한 선택이다. 사진 업로드에서는 전부 비어 있다.
    duration_sec: Optional[float] = Form(None),
    waveform: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
    speaker_id: Optional[str] = Form(None),
    event_id: Optional[str] = Form(None),
    # 올린 사람. 공개 범위를 정할 수 있는 사람이고, 비공개로 두면 이 사람만 본다.
    owner_id: Optional[str] = Form(None),
):
    """미디어 파일 업로드 + 자동 분석 + Graph 연결"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="파일명이 없습니다.")

    # 파일 저장
    save_path = MEDIA_DIR / file.filename
    # 중복 방지
    if save_path.exists():
        stem = save_path.stem
        suffix = save_path.suffix
        counter = 1
        while save_path.exists():
            save_path = MEDIA_DIR / f"{stem}_{counter}{suffix}"
            counter += 1

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 미디어 분석
    media_node = analyze_media(str(save_path), file.filename)
    media_node.file_path = f"/media-files/{save_path.name}"

    # 썸네일 생성 (사진인 경우)
    if media_node.media_type == "photo":
        thumb_path = MEDIA_DIR / f"thumb_{save_path.name}"
        thumb_result = generate_thumbnail(str(save_path), str(thumb_path))
        if thumb_result:
            media_node.thumbnail_path = f"/media-files/thumb_{save_path.name}"

    # 음성으로 온 정보 반영 (녹음은 EXIF가 없으므로 화면이 보낸 값이 유일한 근거다)
    is_audio = media_node.media_type == MediaType.AUDIO
    if duration_sec is not None:
        media_node.duration_sec = duration_sec
    if waveform:
        media_node.waveform = _parse_waveform(waveform)
    if transcript:
        media_node.transcript = transcript
    if speaker_id and graph_manager.get_node(speaker_id):
        media_node.speaker_id = speaker_id
    if owner_id and graph_manager.get_node(owner_id):
        media_node.owner_id = owner_id
    elif media_node.speaker_id:
        # 녹음은 말한 사람이 곧 올린 사람이다
        media_node.owner_id = media_node.speaker_id

    if is_audio:
        # 인터뷰 녹음은 말한 사람이 곧 출처다. 사람이 확인한 기록으로 본다.
        media_node.source = SourceType.INTERVIEW
        if media_node.speaker_id:
            media_node.confidence = Confidence.CONFIRMED

    # Graph에 추가
    graph_manager.add_media(media_node)

    # 말하는 사람 연결 (Media -> Person). 사진에 찍힌 것과 구분되는 관계다.
    if media_node.speaker_id:
        graph_manager.add_edge(Edge(
            source=media_node.id,
            target=media_node.speaker_id,
            relation=RelationType.NARRATED_BY,
        ))

    # 어느 사건의 기록인지 화면이 알려준 경우(녹음 등) 그대로 잇는다.
    # 없으면 EXIF로 자동 매칭하고, 그것도 없으면 사용자 입력을 기다린다.
    linked_event_id = None
    if event_id:
        event_node = graph_manager.get_node(event_id)
        if event_node and event_node.get("node_type") == NodeType.EVENT:
            linked_event_id = event_id
            graph_manager.add_edge(Edge(
                source=media_node.id,
                target=linked_event_id,
                relation=RelationType.CAPTURED_DURING,
            ))

    has_exif = bool(media_node.exif_date)
    if not linked_event_id and has_exif:
        linked_event_id = resolve_event_for_media(media_node)

    needs_info = not linked_event_id

    return MediaUploadResponse(
        id=media_node.id,
        media_type=media_node.media_type,
        file_path=media_node.file_path,
        thumbnail_path=media_node.thumbnail_path,
        original_filename=media_node.original_filename,
        exif_date=media_node.exif_date,
        exif_lat=media_node.exif_lat,
        exif_lng=media_node.exif_lng,
        detected_faces=media_node.detected_faces,
        scene_description=media_node.scene_description,
        linked_event_id=linked_event_id,
        needs_info=needs_info,
        message="업로드 완료. 추가 정보를 입력해주세요." if needs_info else "업로드 및 분석 완료",
    )


def _parse_waveform(raw: str) -> list[float]:
    """화면이 보낸 파형 JSON을 0~1 범위 숫자 배열로 정리한다

    남이 보낸 값이므로 형식과 범위를 모두 여기서 막는다. 파형이 깨져도
    업로드 자체는 성공해야 한다 (그림이 없을 뿐 음성은 들을 수 있다).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(parsed, list):
        return []

    peaks: list[float] = []
    for value in parsed[:256]:
        if isinstance(value, (int, float)):
            peaks.append(max(0.0, min(1.0, float(value))))

    return peaks


@router.get("", response_model=list[MediaListItem])
async def list_media(
    media_type: Optional[str] = Query(None, description="photo/video/audio"),
    person_id: Optional[str] = Query(None),
    viewer_id: Optional[str] = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
):
    """미디어 목록 조회

    공개 범위를 실제로 적용한다. 설정만 저장하고 가려 주지 않으면 동의는
    형식이 된다 (기획안 08장).
    """
    media_nodes = visibility.filter_media(graph_manager.get_media_nodes(), viewer_id)

    # 필터링
    if media_type:
        media_nodes = [m for m in media_nodes if m.get("media_type") == media_type]

    if person_id:
        # person에 연결된 미디어만.
        # 사진은 찍힌 사람(DEPICTS), 음성은 말한 사람(NARRATED_BY)으로 이어진다.
        person_relations = {RelationType.DEPICTS, RelationType.NARRATED_BY}
        person_media_ids = set()
        edges = graph_manager.get_all_edges()
        for edge in edges:
            if edge["target"] == person_id and edge["relation"] in person_relations:
                person_media_ids.add(edge["source"])
        media_nodes = [m for m in media_nodes if m["id"] in person_media_ids]

    # 최신순 정렬
    media_nodes.sort(
        key=lambda m: m.get("exif_date") or m.get("created_at") or "",
        reverse=True,
    )

    return [_to_list_item(m) for m in media_nodes]


def _to_list_item(node: dict) -> MediaListItem:
    """미디어 노드를 목록 항목으로. 음성은 화자·사건까지 붙여 내려준다

    음성 재생 화면(홈·인물·채팅·TV)이 "누가 언제 어느 사건에서 말했는지"를
    함께 보여줘야 하므로, 목록 한 번으로 그릴 수 있게 여기서 풀어 준다.
    """
    is_audio = node.get("media_type") == MediaType.AUDIO

    speaker_name = None
    event_id = None
    event_title = None

    if is_audio:
        speaker_id = node.get("speaker_id")
        if speaker_id:
            speaker = graph_manager.get_node(speaker_id)
            speaker_name = speaker.get("name") if speaker else None

        for neighbor in graph_manager.get_connected_nodes(node["id"]):
            if neighbor.get("node_type") == NodeType.EVENT:
                event_id = neighbor["id"]
                event_title = neighbor.get("title")
                break

    return MediaListItem(
        id=node["id"],
        media_type=node.get("media_type", "photo"),
        file_path=node.get("file_path", ""),
        thumbnail_path=node.get("thumbnail_path"),
        original_filename=node.get("original_filename", ""),
        created_at=node.get("created_at", ""),
        exif_date=node.get("exif_date"),
        duration_sec=node.get("duration_sec"),
        waveform=node.get("waveform") or [],
        transcript=node.get("transcript"),
        speaker_id=node.get("speaker_id"),
        speaker_name=speaker_name,
        event_id=event_id,
        event_title=event_title,
        source=node.get("source"),
    )


@router.get("/{media_id}", response_model=MediaDetail)
async def get_media_detail(
    media_id: str,
    viewer_id: Optional[str] = Query(None, description="지금 보는 사람"),
):
    """미디어 상세 조회"""
    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    if not visibility.can_view(node, viewer_id):
        # 있다는 사실 자체가 정보가 되지 않도록 없는 것처럼 답한다
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    # 연결된 이벤트/인물
    connected = graph_manager.get_connected_nodes(media_id)
    linked_events = [n for n in connected if n.get("node_type") == NodeType.EVENT]
    linked_persons = [n for n in connected if n.get("node_type") == NodeType.PERSON]

    return MediaDetail(
        id=node["id"],
        media_type=node.get("media_type", "photo"),
        file_path=node.get("file_path", ""),
        thumbnail_path=node.get("thumbnail_path"),
        original_filename=node.get("original_filename", ""),
        created_at=node.get("created_at", ""),
        exif_date=node.get("exif_date"),
        exif_lat=node.get("exif_lat"),
        exif_lng=node.get("exif_lng"),
        exif_camera=node.get("exif_camera"),
        detected_faces=node.get("detected_faces", []),
        scene_description=node.get("scene_description"),
        confidence=node.get("confidence", "user_unverified"),
        linked_events=[{"id": e["id"], "title": e.get("title", "")} for e in linked_events],
        linked_persons=[{"id": p["id"], "name": p.get("name", "")} for p in linked_persons],
    )


@router.delete("/{media_id}")
async def delete_media(media_id: str):
    """미디어 삭제"""
    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    # 실제 파일 삭제
    file_path = node.get("file_path", "")
    if file_path:
        actual_path = MEDIA_DIR / Path(file_path).name
        if actual_path.exists():
            actual_path.unlink()
        # 썸네일도 삭제
        thumb_path = node.get("thumbnail_path", "")
        if thumb_path:
            actual_thumb = MEDIA_DIR / Path(thumb_path).name
            if actual_thumb.exists():
                actual_thumb.unlink()

    # Graph에서 삭제
    graph_manager.delete_node(media_id)
    return {"message": "삭제 완료", "id": media_id}


@router.post("/supplement")
async def supplement_media_info(request: MediaSupplementRequest):
    """EXIF 없는 미디어에 사용자가 추가 정보 제공 → 이벤트 연결"""
    node = graph_manager.get_node(request.media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    updates = {}

    # 날짜 업데이트
    if request.date:
        updates["exif_date"] = request.date
        updates["confidence"] = Confidence.CONFIRMED

    # 설명 업데이트
    if request.description:
        updates["scene_description"] = request.description

    if updates:
        graph_manager.update_node(request.media_id, updates)

    # 이벤트 연결
    linked_event_id = None
    if request.event_id:
        # 기존 이벤트에 직접 연결
        event = graph_manager.get_node(request.event_id)
        if event and event.get("node_type") == NodeType.EVENT:
            graph_manager.add_edge(Edge(
                source=request.media_id,
                target=request.event_id,
                relation=RelationType.CAPTURED_DURING,
            ))
            linked_event_id = request.event_id
    elif request.date:
        # 날짜 기반으로 Event Resolver 재실행
        updated_node = graph_manager.get_node(request.media_id)
        from backend.services.media_analyzer import analyze_media
        from backend.services.event_resolver import resolve_event_for_media
        from backend.models.graph_models import MediaNode

        # 간이 MediaNode 생성 (resolve용)
        temp_media = MediaNode(
            id=request.media_id,
            exif_date=request.date,
            file_path=node.get("file_path", ""),
        )
        linked_event_id = resolve_event_for_media(temp_media)

    return {
        "message": "정보가 업데이트되었습니다.",
        "media_id": request.media_id,
        "linked_event_id": linked_event_id,
    }
