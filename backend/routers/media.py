"""Media Router - 업로드, 목록, 상세, 삭제"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from typing import Optional
import shutil
from pathlib import Path

from backend.config import MEDIA_DIR
from backend.models.schemas import MediaUploadResponse, MediaListItem, MediaDetail, MediaSupplementRequest
from backend.models.graph_models import NodeType, RelationType, Edge, Confidence
from backend.services.media_analyzer import analyze_media, generate_thumbnail
from backend.services.event_resolver import resolve_event_for_media
from backend.services.graph_manager import graph_manager

router = APIRouter()


@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(file: UploadFile = File(...)):
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

    # Graph에 추가
    graph_manager.add_media(media_node)

    # EXIF 정보가 없으면 이벤트 연결을 보류하고 사용자 입력 요청
    has_exif = bool(media_node.exif_date)
    needs_info = not has_exif

    event_id = None
    if has_exif:
        # EXIF 있으면 자동 이벤트 매칭
        event_id = resolve_event_for_media(media_node)

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
        linked_event_id=event_id,
        needs_info=needs_info,
        message="업로드 완료. 추가 정보를 입력해주세요." if needs_info else "업로드 및 분석 완료",
    )


@router.get("", response_model=list[MediaListItem])
async def list_media(
    media_type: Optional[str] = Query(None, description="photo/video/audio"),
    person_id: Optional[str] = Query(None),
):
    """미디어 목록 조회"""
    media_nodes = graph_manager.get_media_nodes()

    # 필터링
    if media_type:
        media_nodes = [m for m in media_nodes if m.get("media_type") == media_type]

    if person_id:
        # person에 연결된 미디어만
        person_media_ids = set()
        edges = graph_manager.get_all_edges()
        for edge in edges:
            if edge["target"] == person_id and edge["relation"] == RelationType.DEPICTS:
                person_media_ids.add(edge["source"])
        media_nodes = [m for m in media_nodes if m["id"] in person_media_ids]

    # 최신순 정렬
    media_nodes.sort(
        key=lambda m: m.get("exif_date") or m.get("created_at") or "",
        reverse=True,
    )

    return [
        MediaListItem(
            id=m["id"],
            media_type=m.get("media_type", "photo"),
            file_path=m.get("file_path", ""),
            thumbnail_path=m.get("thumbnail_path"),
            original_filename=m.get("original_filename", ""),
            created_at=m.get("created_at", ""),
            exif_date=m.get("exif_date"),
        )
        for m in media_nodes
    ]


@router.get("/{media_id}", response_model=MediaDetail)
async def get_media_detail(media_id: str):
    """미디어 상세 조회"""
    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
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
