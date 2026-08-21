"""Media Router - 업로드, 목록, 상세, 삭제"""

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from typing import Optional
import json
import shutil

from backend.config import MEDIA_DIR
from backend.models.schemas import (
    AlbumResponse, FaceAssignRequest, FaceBox, MediaBulkDeleteRequest, MediaBulkDeleteResponse,
    MediaUploadResponse, MediaListItem, MediaDetail, MediaPersonTagRequest,
)
from backend.models.graph_models import (
    NodeType, MediaType, RelationType, Edge, Confidence, SourceType,
)
from backend.services.media_analyzer import analyze_media, erase_files, generate_thumbnail
from backend.services.event_resolver import (
    autotag_media_persons,
    events_of_media,
    set_media_persons,
    sync_participants_of_event,
)
from backend.services.graph_manager import graph_manager
from backend.services import album, geocoder, memories, permissions, visibility
from backend.services.permissions import current_actor

router = APIRouter()

# 한 번에 지울 수 있는 개수. 사진첩은 60장씩 받아 가므로 넉넉하다.
# 상한을 두는 이유는 조용히 잘라내지 않기 위해서다 — 넘으면 몇 개인지 밝히고 막는다.
MAX_BULK_DELETE = 200


@router.post("/upload", response_model=MediaUploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    # --- 음성 녹음이 함께 보내는 정보 ---
    # 브라우저가 녹음 직후 길이와 파형을 계산해 보낸다. 서버에 오디오 디코더를
    # 두지 않기 위한 선택이다. 사진 업로드에서는 전부 비어 있다.
    duration_sec: Optional[float] = Form(None),
    waveform: Optional[str] = Form(None),
    # 영상의 첫 장면. 브라우저가 캔버스로 뽑아 보낸다 — 서버에 ffmpeg를 두지
    # 않기 위한 분업이다 (frontend/src/lib/videoMeta.ts). 없으면 없이 간다.
    poster: Optional[UploadFile] = File(None),
    transcript: Optional[str] = Form(None),
    # 그 글을 누가 썼는지. ai_stt면 브라우저 음성 인식이 옮기고 사람이 손대지
    # 않은 것이다. 안 보내면 사람이 적은 것으로 본다.
    transcript_source: Optional[str] = Form(None),
    speaker_id: Optional[str] = Form(None),
    event_id: Optional[str] = Form(None),
    # 사진·영상에 찍힌 사람. 쉼표로 구분한 person_id.
    # 얼굴 인식이 없으므로 이 값이 detected_faces의 유일한 출처다.
    person_ids: Optional[str] = Form(None),
    # 올린 사람. 공개 범위를 정할 수 있는 사람이고, 비공개로 두면 이 사람만 본다.
    owner_id: Optional[str] = Form(None),
    actor: Optional[dict] = Depends(current_actor),
):
    """미디어 파일 업로드 + 자동 분석 + Graph 연결"""
    permissions.require_writer(actor)

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

    # 미디어 분석. 브라우저가 알려준 형식을 함께 넘긴다 — 녹음은 audio/webm으로
    # 오는데 .webm은 영상 확장자와 같아서, 확장자만 보면 목소리가 영상이 된다.
    media_node = analyze_media(str(save_path), file.filename, file.content_type)
    media_node.file_path = f"/media-files/{save_path.name}"

    # 썸네일 — 사진은 원본에서, 영상은 화면이 보낸 첫 장면에서
    if media_node.media_type == MediaType.PHOTO:
        thumb_path = MEDIA_DIR / f"thumb_{save_path.name}"
        thumb_result = generate_thumbnail(str(save_path), str(thumb_path))
        if thumb_result:
            media_node.thumbnail_path = f"/media-files/thumb_{save_path.name}"
    elif media_node.media_type == MediaType.VIDEO and poster is not None:
        media_node.thumbnail_path = _save_video_poster(save_path.stem, poster)

    # 음성으로 온 정보 반영 (녹음은 EXIF가 없으므로 화면이 보낸 값이 유일한 근거다)
    is_audio = media_node.media_type == MediaType.AUDIO
    if duration_sec is not None:
        media_node.duration_sec = duration_sec
    if waveform:
        media_node.waveform = _parse_waveform(waveform)
    if transcript:
        media_node.transcript = transcript
        # 기계가 옮긴 글을 사람이 쓴 것으로 남기면 신뢰도 표시가 거짓이 된다.
        # 화면이 ai_stt라고 밝힌 경우만 그렇게 적고, 나머지는 사람이 쓴 것으로 본다.
        media_node.transcript_source = (
            SourceType.AI_STT
            if transcript_source == SourceType.AI_STT.value
            else SourceType.USER_INPUT
        )
    if speaker_id and graph_manager.get_node(speaker_id):
        media_node.speaker_id = speaker_id
    if owner_id and graph_manager.get_node(owner_id):
        media_node.owner_id = owner_id
    elif actor:
        # 소유자를 따로 안 보냈으면 올린 사람이 소유자다
        media_node.owner_id = actor["id"]
    elif media_node.speaker_id:
        # 녹음은 말한 사람이 곧 올린 사람이다
        media_node.owner_id = media_node.speaker_id

    if is_audio:
        # 인터뷰 녹음은 말한 사람이 곧 출처다. 사람이 확인한 기록으로 본다.
        # 여기서 확정하는 것은 목소리다. 그것을 옮긴 글의 출처는 별개 축이라
        # transcript_source에 따로 남는다 — 기계가 옮긴 글이 섞여 들어온다.
        media_node.source = SourceType.INTERVIEW
        if media_node.speaker_id:
            media_node.confidence = Confidence.CONFIRMED

    # Graph에 추가
    graph_manager.add_media(media_node)

    # 찍힌 사람 연결 (Media -> Person)
    if person_ids:
        # 화면이 지목한 사람이 있으면 그것이 사실이다. 인식을 돌리지 않는다.
        media_node.detected_faces = set_media_persons(media_node.id, person_ids.split(","))
        media_node.faces_source = SourceType.USER_INPUT
    else:
        # 아무것도 안 왔으면 얼굴로 알아본다 (services/faces.py). 자격증명이 없거나
        # 등록된 얼굴이 없으면 빈 목록이고, 그때는 화면에서 직접 지목한다.
        recognized = autotag_media_persons(media_node.id)
        if recognized:
            media_node.detected_faces = recognized
            media_node.faces_source = SourceType.AI_VISION

    # 말하는 사람 연결 (Media -> Person). 사진에 찍힌 것과 구분되는 관계다.
    if media_node.speaker_id:
        graph_manager.add_edge(Edge(
            source=media_node.id,
            target=media_node.speaker_id,
            relation=RelationType.NARRATED_BY,
        ))

    # 어느 추억의 기록인지 화면이 알려준 경우(녹음 등)만 잇는다.
    #
    # 예전에는 EXIF를 읽어 사건을 자동으로 찾거나 없으면 새로 만들었다. 그것을
    # 없앤 이유는 두 가지다. (1) 자동으로 기억을 병합하지 않는다 — 어느 추억에
    # 속하는지는 올린 사람이 고른다. (2) 올리자마자 "2015년 기록" 같은 이름의
    # 빈 사건이 생겨 가족 공간이 제목 없는 껍데기로 채워졌다.
    #
    # 이제 업로드 다음 단계는 AI 초안이다 (POST /api/memories/draft).
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

    # 아직 어떤 추억에도 붙지 않았다는 뜻이다 (초안을 만들 차례).
    needs_info = not linked_event_id

    return MediaUploadResponse(
        id=media_node.id,
        media_type=media_node.media_type,
        file_path=media_node.file_path,
        thumbnail_path=media_node.thumbnail_path,
        duration_sec=media_node.duration_sec,
        original_filename=media_node.original_filename,
        exif_date=media_node.exif_date,
        exif_lat=media_node.exif_lat,
        exif_lng=media_node.exif_lng,
        place_guess=geocoder.coarse_name(media_node.exif_lat, media_node.exif_lng),
        detected_faces=media_node.detected_faces,
        scene_description=media_node.scene_description,
        scene_source=media_node.scene_source,
        faces_source=media_node.faces_source,
        linked_event_id=linked_event_id,
        needs_info=needs_info,
        message=(
            "업로드 완료. AI가 초안을 만들 차례입니다."
            if needs_info
            else "업로드 완료. 이 추억의 기록으로 이었습니다."
        ),
    )


def _save_video_poster(stem: str, poster: UploadFile) -> Optional[str]:
    """영상 첫 장면을 썸네일로 저장한다

    화면이 보낸 그림을 그대로 두지 않고 Pillow로 다시 저장한다. 남이 보낸
    파일이므로 (a) 정말 이미지인지, (b) 크기가 터무니없지 않은지를 여기서
    가른다. 실패하면 None을 돌려주고 업로드 자체는 성공시킨다 — 썸네일이 없는
    것은 불편이고, 업로드가 막히는 것은 기록을 잃는 것이다.
    """
    raw_path = MEDIA_DIR / f"poster_raw_{stem}"
    final_name = f"thumb_{stem}.jpg"

    try:
        with open(raw_path, "wb") as f:
            shutil.copyfileobj(poster.file, f)

        if generate_thumbnail(str(raw_path), str(MEDIA_DIR / final_name)):
            return f"/media-files/{final_name}"
        return None
    except Exception as e:
        print(f"[media] 영상 썸네일을 만들지 못했습니다 ({type(e).__name__}: {e})")
        return None
    finally:
        if raw_path.exists():
            raw_path.unlink()


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
    """미디어 노드를 목록 항목으로. 음성은 화자·사건·질문까지 붙여 내려준다

    음성 재생 화면(홈·인물·채팅·TV)이 "누가 언제 어느 사건에서 무슨 질문에
    답했는지"를 함께 보여줘야 하므로, 목록 한 번으로 그릴 수 있게 여기서 풀어
    준다.
    """
    is_audio = node.get("media_type") == MediaType.AUDIO

    speaker_name = None
    event_id = None
    event_title = None
    question = None

    if is_audio:
        speaker_id = node.get("speaker_id")
        if speaker_id:
            speaker = graph_manager.get_node(speaker_id)
            speaker_name = speaker.get("name") if speaker else None

        # 무슨 질문에 답한 목소리인지 (질문은 그 답을 남긴 기억에 있다)
        question = memories.question_for_media(node["id"])

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
        transcript_source=node.get("transcript_source"),
        speaker_id=node.get("speaker_id"),
        speaker_name=speaker_name,
        event_id=event_id,
        event_title=event_title,
        question=question,
        source=node.get("source"),
    )


@router.get("/album", response_model=AlbumResponse)
async def get_album(
    cursor: Optional[str] = Query(None, description="이전 응답의 next_cursor"),
    limit: int = Query(album.DEFAULT_LIMIT, ge=1, le=album.MAX_LIMIT),
    types: Optional[str] = Query(None, description="photo,video — 비우면 둘 다"),
    year: Optional[int] = Query(None, description="촬영 연도 (EXIF 기준)"),
    person_id: Optional[str] = Query(None, description="이 사람이 지목된 사진만"),
    event_id: Optional[str] = Query(None, description="이 추억에 붙은 사진만"),
    event_status: str = Query("all", description="all|linked|unlinked"),
    sort: str = Query("captured_desc", description="captured_desc|captured_asc|uploaded_desc"),
    group_by: str = Query("month", description="month|event — 무엇으로 묶어 볼까"),
    q: Optional[str] = Query(None, description="파일명·추억 제목·인물·장소명"),
    viewer_id: Optional[str] = Query(None, description="지금 보는 사람 (공개 범위 적용)"),
):
    """사진첩 — 가족이 모은 사진·영상을 촬영 순서대로

    이 라우트는 반드시 `/{media_id}` 위에 있어야 한다. 아래에 두면 FastAPI가
    "album"을 media_id로 읽어 404를 돌려준다.

    목록·정렬·필터·페이지는 전부 데이터 처리다. AI를 끼우지 않는다
    (backend/services/album.py 첫 주석).
    """
    return album.query(
        viewer_id=viewer_id,
        types=types,
        year=year,
        person_id=person_id,
        event_id=event_id,
        event_status=event_status,
        sort=sort,
        group_by=group_by,
        q=q,
        cursor=cursor,
        limit=limit,
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
        scene_source=node.get("scene_source"),
        faces_source=node.get("faces_source"),
        face_boxes=_face_boxes(node),
        confidence=node.get("confidence", "user_unverified"),
        linked_events=[{"id": e["id"], "title": e.get("title", "")} for e in linked_events],
        linked_persons=[{"id": p["id"], "name": p.get("name", "")} for p in linked_persons],
    )


def _face_boxes(node: dict) -> list[FaceBox]:
    """저장해 둔 얼굴 위치에 이름을 붙여 내려보낸다

    여는 것만으로 유료 호출이 일어나지 않게 저장된 것만 읽는다
    (faces.stored_boxes). 찾는 것은 업로드·초안·다시 찾기에서만 한다.
    """
    from backend.services import faces

    out: list[FaceBox] = []
    for item in faces.stored_boxes(node):
        box = item.get("box") or {}
        person_id = item.get("person_id")
        person = graph_manager.get_node(person_id) if person_id else None
        if person and person.get("node_type") != NodeType.PERSON:
            person = None
        out.append(FaceBox(
            left=box.get("left", 0.0),
            top=box.get("top", 0.0),
            width=box.get("width", 0.0),
            height=box.get("height", 0.0),
            person_id=person_id if person else None,
            name=(person or {}).get("name"),
            relation=(person or {}).get("relation"),
            similarity=item.get("similarity") or 0.0,
            reason=item.get("reason") or "",
        ))
    return out


@router.post("/{media_id}/faces/detect")
async def detect_media_faces(
    media_id: str,
    actor: Optional[dict] = Depends(current_actor),
):
    """이 사진에서 얼굴을 다시 찾는다 (사람이 눌렀을 때만)

    돈이 드는 호출이라 화면을 여는 것만으로 돌지 않는다. 얼굴 등록이 늘어난
    뒤에 다시 눌러 보라는 뜻으로 화면에 버튼을 둔다.

    사람이 지목한 인물 목록(detected_faces)은 건드리지 않는다. 여기서 채우는
    것은 위치와 "이 얼굴이 누구로 보이는가"까지다.
    """
    permissions.require_writer(actor)

    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")
    if not visibility.can_view(node, actor["id"] if actor else None):
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    from backend.services import faces

    if not faces.enabled():
        raise HTTPException(
            status_code=400,
            detail="얼굴 인식이 꺼져 있습니다 (AWS 자격증명이 없습니다).",
        )
    if node.get("media_type") != MediaType.PHOTO:
        raise HTTPException(status_code=400, detail="사진에서만 얼굴을 찾습니다.")

    faces.identify_and_store(media_id)
    fresh = graph_manager.get_node(media_id)
    return {"media_id": media_id, "face_boxes": _face_boxes(fresh)}


@router.put("/{media_id}/faces")
async def assign_media_face(
    media_id: str,
    request: FaceAssignRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """얼굴 하나가 누구인지 정한다 (상세 화면에서 상자를 눌렀을 때)

    얼굴별 지정과 사진 전체 인물 목록을 함께 맞춘다. 상자에만 남기면 인물별
    조회와 공개 범위 판정이 그것을 못 읽는다 (그쪽은 detected_faces를 본다).

    사람이 정한 것이므로 faces_source는 user_input이 된다 — 화면이 "AI가
    알아봄"이라고 계속 적으면 거짓이 된다.
    """
    permissions.require_writer(actor)

    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")
    if not visibility.can_view(node, actor["id"] if actor else None):
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    from backend.services import faces

    boxes = faces.assign_face(media_id, request.face_index, request.person_id)
    if boxes is None:
        raise HTTPException(status_code=400, detail="그런 얼굴이 없습니다.")

    # 상자에 남은 사람들로 사진 전체 목록을 맞춘다
    named = [b["person_id"] for b in boxes if b.get("person_id")]
    set_media_persons(media_id, named)

    fresh = graph_manager.get_node(media_id)
    return {
        "media_id": media_id,
        "face_boxes": _face_boxes(fresh),
        "detected_faces": fresh.get("detected_faces") or [],
    }


@router.put("/{media_id}/persons")
async def set_media_person_tags(
    media_id: str,
    request: MediaPersonTagRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """이 기록에 있는 사람을 지목한다 (보낸 목록이 최종 상태가 된다)

    얼굴 인식이 없으므로 이 요청이 detected_faces의 유일한 출처다.
    최종 목록을 받는 이유는 화면이 켜고 끄는 그대로를 그래프에 반영하기
    위해서다 — 더하기만 있으면 잘못 지목한 사람을 뗄 수 없다.
    """
    permissions.require_writer(actor)

    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    if not visibility.can_view(node, actor["id"] if actor else None):
        # 볼 수 없는 기록의 존재를 응답으로 알려주지 않는다
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    tagged = set_media_persons(media_id, request.person_ids)
    return {"media_id": media_id, "detected_faces": tagged}


def _authorize_delete(media_id: str, actor: Optional[dict]) -> dict:
    """지울 수 있는 기록을 돌려준다. 아니면 그 이유로 막는다

    한 장 삭제와 여러 장 삭제가 같은 판정을 지나야 한다. 규칙이 두 벌이면
    한쪽만 고쳐졌을 때 남의 사진이 지워진다.
    """
    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    if not visibility.can_view(node, actor["id"] if actor else None):
        # 볼 수 없는 기록의 존재를 삭제 응답으로 알려주지 않는다
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다.")

    permissions.require_owner_of(node, actor, what="기록")
    return node


@router.post("/bulk-delete", response_model=MediaBulkDeleteResponse)
async def bulk_delete_media(
    request: MediaBulkDeleteRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """여러 원본을 한 번에 지운다 (사진첩의 선택 삭제)

    한 장씩 DELETE를 여러 번 부르지 않는 이유는 두 가지다.

      1. JSON 저장소는 쓰기마다 파일 전체를 다시 쓴다. 50장이면 50번이다.
         batch()로 묶어 저장을 한 번으로 모은다.
      2. 하나가 막혀도 나머지는 지워져야 하고, 무엇이 왜 막혔는지를 함께
         돌려줘야 한다. 요청이 50개로 흩어지면 화면이 그것을 다시 모아야 한다.

    판정은 한 장 삭제와 같다(_authorize_delete). 남의 기록이 섞여 있으면 그것만
    남고 failed에 이유가 담긴다 — 하나 때문에 전부 되돌리지 않는다. 되돌리면
    "왜 아무것도 안 지워졌지"가 되고, 사용자는 어느 것이 남의 것인지 모른다.
    """
    # 같은 id를 두 번 보내도 한 번만 (순서는 보낸 그대로 둔다)
    wanted: list[str] = []
    for media_id in request.media_ids:
        media_id = (media_id or "").strip()
        if media_id and media_id not in wanted:
            wanted.append(media_id)

    if not wanted:
        raise HTTPException(status_code=400, detail="지울 기록을 고르지 않았습니다.")

    if len(wanted) > MAX_BULK_DELETE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"한 번에 {MAX_BULK_DELETE}개까지 지울 수 있습니다. "
                f"{len(wanted)}개를 보냈습니다 — 나눠서 지워 주세요."
            ),
        )

    deletable: list[dict] = []
    failed: list[dict] = []

    # 지우기 전에 전부 판정한다. 파일을 먼저 건드리고 중간에 막히면 되돌릴 수 없다.
    for media_id in wanted:
        try:
            deletable.append(_authorize_delete(media_id, actor))
        except HTTPException as e:
            failed.append({"id": media_id, "reason": str(e.detail)})

    if deletable:
        # 지우기 전에 읽어 둔다 (한 장 삭제와 같은 이유)
        events = {
            event_id for node in deletable for event_id in events_of_media(node["id"])
        }

        # 저장을 한 번으로 모은다. 여기서 예외가 나면 Postgres는 전부 되돌리므로,
        # 파일은 이 묶음이 끝난 뒤에 지운다.
        with graph_manager.batch():
            for node in deletable:
                graph_manager.delete_node(node["id"])
            for event_id in events:
                sync_participants_of_event(event_id)

        for node in deletable:
            erase_files(node)

    deleted = [node["id"] for node in deletable]
    if deleted and failed:
        message = f"{len(deleted)}개를 지웠습니다. {len(failed)}개는 지우지 못했습니다."
    elif deleted:
        message = f"{len(deleted)}개를 지웠습니다."
    else:
        message = "지운 것이 없습니다."

    return MediaBulkDeleteResponse(deleted=deleted, failed=failed, message=message)


@router.delete("/{media_id}")
async def delete_media(
    media_id: str,
    actor: Optional[dict] = Depends(current_actor),
):
    """미디어 삭제 — 올린 사람이나 가족 관리자만"""
    node = _authorize_delete(media_id, actor)

    # 지우기 전에 읽어 둔다. 지운 뒤에는 어느 사건에 붙어 있었는지 알 수 없다.
    events = events_of_media(media_id)

    graph_manager.delete_node(media_id)
    erase_files(node)

    # 사진에서 온 참여자는 그 사진이 있는 동안만이다. 마지막 사진이 사라졌는데
    # 사건에 남으면, 이야기가 근거 없이 그 사람을 계속 부른다.
    for event_id in events:
        sync_participants_of_event(event_id)

    return {"message": "삭제 완료", "id": media_id}
