"""Pydantic 스키마 (API Request/Response)"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# --- Enums for API ---

class MediaTypeEnum(str, Enum):
    photo = "photo"
    video = "video"
    audio = "audio"


class ConfidenceEnum(str, Enum):
    confirmed = "confirmed"
    ai_inferred = "ai_inferred"
    user_unverified = "user_unverified"


# --- Media ---

class MediaUploadResponse(BaseModel):
    id: str
    media_type: str
    file_path: str
    thumbnail_path: Optional[str] = None
    original_filename: str
    exif_date: Optional[str] = None
    exif_lat: Optional[float] = None
    exif_lng: Optional[float] = None
    detected_faces: list[str] = []
    scene_description: Optional[str] = None
    linked_event_id: Optional[str] = None
    needs_info: bool = False  # EXIF 없을 때 True
    message: str = "업로드 완료"


class MediaSupplementRequest(BaseModel):
    """EXIF 없는 미디어에 사용자가 추가 정보를 제공"""
    media_id: str
    date: Optional[str] = None  # ISO date (예: "2015-07-20")
    event_id: Optional[str] = None  # 기존 이벤트에 연결
    description: Optional[str] = None


class MediaListItem(BaseModel):
    id: str
    media_type: str
    file_path: str
    thumbnail_path: Optional[str] = None
    original_filename: str
    created_at: str
    exif_date: Optional[str] = None
    # --- 음성 (media_type == "audio") ---
    duration_sec: Optional[float] = None
    waveform: list[float] = []
    transcript: Optional[str] = None
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    event_id: Optional[str] = None
    event_title: Optional[str] = None
    # 이 기록이 어디서 왔는지: exif | user_input | ai_vision | ai_stt | interview
    source: Optional[str] = None


class MediaDetail(BaseModel):
    id: str
    media_type: str
    file_path: str
    thumbnail_path: Optional[str] = None
    original_filename: str
    created_at: str
    exif_date: Optional[str] = None
    exif_lat: Optional[float] = None
    exif_lng: Optional[float] = None
    exif_camera: Optional[str] = None
    detected_faces: list[str] = []
    scene_description: Optional[str] = None
    confidence: str = "user_unverified"
    linked_events: list[dict] = []
    linked_persons: list[dict] = []


# --- Graph ---

class GraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class PersonCreate(BaseModel):
    name: str
    relation: str = ""
    birth_year: Optional[int] = None
    thumbnail_url: Optional[str] = None


class PersonResponse(BaseModel):
    id: str
    name: str
    relation: str
    birth_year: Optional[int] = None
    thumbnail_url: Optional[str] = None
    events: list[dict] = []
    media: list[dict] = []
    # 이 인물이 남긴 기억 (REMEMBERS 엣지)
    memories: list[dict] = []


class EventResponse(BaseModel):
    id: str
    title: str
    description: str
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    location: Optional[dict] = None
    confidence: str
    participants: list[dict] = []
    media: list[dict] = []
    memories: list[dict] = []
    # 가족 확인 상태 (confidence와 다른 축: 자료 출처 vs 가족이 확인했는지)
    verification: Optional[dict] = None


class VerifyRequest(BaseModel):
    person_id: str
    action: str  # "confirm" | "correct" | "unknown" | "dispute"
    # 이견일 때 그 사람의 기억. 사실을 덮어쓰지 않고 별도 Memory로 보존된다.
    note: Optional[str] = None
    # 수정일 때 고칠 값. title · date_start · description · location_id 만 받는다
    # (확인 화면이 그래프 편집기가 되지 않게).
    corrections: Optional[dict] = None


class VerifyResponse(BaseModel):
    event_id: str
    verification: dict
    created_memory_id: Optional[str] = None
    # 수정일 때 무엇이 무엇으로 바뀌었는지 [{field, before, after}]
    changes: list[dict] = []
    message: str


class PlaceRef(BaseModel):
    """좌표까지 포함한 장소. 지도가 이름만으로는 점을 찍을 수 없다."""
    id: str
    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None


class PersonRef(BaseModel):
    id: str
    name: str
    relation: Optional[str] = None
    thumbnail_url: Optional[str] = None


class EventListItem(BaseModel):
    """타임라인·지도·TV가 함께 쓰는 사건 요약

    화면마다 사건 상세를 다시 부르지 않도록 한 번에 내려준다.
    지도는 좌표, TV는 장소명과 확인 상태, 타임라인은 참여자와 썸네일이 필요하다.
    """
    id: str
    title: str
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    location_name: Optional[str] = None
    participant_count: int = 0
    media_count: int = 0
    # --- 아래부터 화면이 목데이터로 채우던 부분 ---
    place: Optional[PlaceRef] = None
    participants: list[PersonRef] = []
    # 미리보기용 썸네일 경로 (최대 3장)
    media_thumbs: list[str] = []
    memory_count: int = 0
    voice_count: int = 0
    # 가족 확인 상태: confirmed | supported | inferred | conflicted
    state: str = "inferred"


# --- Chat ---

class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    # 지금 묻는 사람. 이 사람이 볼 수 없는 기록은 근거에서 빠진다 (기획안 08장).
    viewer_id: Optional[str] = None


class SourceItem(BaseModel):
    type: str  # "media" | "event" | "memory" | "person"
    id: str
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    confidence: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem] = []
    confidence: str = "confirmed"
    conversation_id: Optional[str] = None


# --- Interview ---

class InterviewStartRequest(BaseModel):
    target_type: str = "event"  # "event" | "media" | "auto"
    target_id: Optional[str] = None


class InterviewStartResponse(BaseModel):
    session_id: str
    question: str
    context: Optional[dict] = None  # 관련 미디어/이벤트 정보


class InterviewAnswerRequest(BaseModel):
    session_id: str
    answer: str
    # 누구의 기억으로 저장할지. 없으면 Gap이 지목한 인물에게 귀속한다.
    # 기획안 08장의 귀속 원칙 — 답한 사람이 화면에서 정해지므로 그대로 받는다.
    speaker_id: Optional[str] = None
    # 말로 답한 경우 먼저 업로드된 음성 미디어 id.
    # 기억 문장에서 원본 음성으로 되짚을 수 있게 EVIDENCED_BY로 잇는다.
    audio_media_id: Optional[str] = None


class InterviewAnswerResponse(BaseModel):
    session_id: str
    next_question: Optional[str] = None
    is_complete: bool = False
    updated_nodes: list[str] = []  # 업데이트된 노드 ID
    message: str = ""


# --- Gaps ---

class GapItem(BaseModel):
    id: str
    event_id: Optional[str] = None
    event_title: Optional[str] = None
    gap_type: str  # "missing_date" | "missing_place" | "missing_person_memory" | "no_media" | "single_perspective"
    description: str
    suggested_question: str
    target_person: Optional[str] = None  # 질문 대상
    priority: int = 1  # 1~5


class GapsResponse(BaseModel):
    gaps: list[GapItem]
    total: int


# --- Family Space / 공개 범위 ---

class FamilyMemberItem(BaseModel):
    id: str
    name: str
    relation: str = ""
    birth_year: Optional[int] = None
    thumbnail_url: Optional[str] = None
    # owner | contributor | viewer | invited
    role: str = "contributor"
    joined_at: Optional[str] = None
    # 이 사람이 등장하는 기록을 가족 공유에서 빼 달라는 요청
    private_request: bool = False
    asset_count: int = 0
    memory_count: int = 0
    verified_count: int = 0


class InviteItem(BaseModel):
    code: str
    # 서버가 앱 주소(APP_BASE_URL)를 알 때만 채운다. 비어 있으면 화면이
    # 자기 origin에 join_path를 붙인다.
    link: str = ""
    join_path: str = ""
    person_id: Optional[str] = None
    created_at: str
    expires_at: str
    expires_in_hours: int = 72


class VisibilitySummary(BaseModel):
    viewer_id: Optional[str] = None
    media_total: int = 0
    visible: int = 0
    hidden: int = 0


class FamilySpaceResponse(BaseModel):
    space_name: str
    members: list[FamilyMemberItem] = []
    invites: list[InviteItem] = []
    # 누가 얼마나 모았는지
    ownership: list[dict] = []
    # 지금 보는 사람에게 몇 개가 가려지는지
    visibility: VisibilitySummary


class MemberUpdateRequest(BaseModel):
    role: Optional[str] = None
    private_request: Optional[bool] = None


class InviteRequest(BaseModel):
    # 특정 인물을 초대하면 그 사람이 '초대 대기'로 바뀐다
    person_id: Optional[str] = None


class InviteResponse(BaseModel):
    code: str
    link: str = ""
    join_path: str = ""
    person_id: Optional[str] = None
    created_at: str
    expires_at: str
    expires_in_hours: int = 72
    used_at: Optional[str] = None
    used_by: Optional[str] = None


class JoinRequest(BaseModel):
    code: str
    # 이미 그래프에 있는 사람으로 들어오는 경우
    person_id: Optional[str] = None
    # 새로 들어오는 경우
    name: Optional[str] = None
    relation: Optional[str] = None


class JoinResponse(BaseModel):
    space_name: str
    member: FamilyMemberItem


class VisibilityRequest(BaseModel):
    # family | partial | private
    visibility: str
    allowed_ids: Optional[list[str]] = None
    owner_id: Optional[str] = None


# --- Memory Film ---

class FilmRequest(BaseModel):
    event_id: str
    # 30 | 45 | 60 — 화면이 고른 길이. 넘치는 장면은 서버가 잘라낸다.
    length_sec: int = 45
    # child | adult | elder — 장면 길이와 내레이션 어투가 달라진다
    audience: str = "adult"


class FilmScene(BaseModel):
    media_id: str
    thumb: str
    file_path: str
    subtitle: str
    note: str = ""
    duration_sec: int
    # 이 장면의 근거가 되는 원본
    source_label: str
    # 적용된 AI 효과. 빈 배열이면 원본 그대로다. 화면은 이 목록을 반드시 노출한다.
    ai_effects: list[str] = []
    # 이 장면에 깔리는 실제 가족 음성
    voice_id: Optional[str] = None


class FilmResponse(BaseModel):
    event_id: str
    title: str
    subtitle: str = ""
    narration: str = ""
    scenes: list[FilmScene] = []
    total_sec: int = 0
    audience: str = "adult"
    requested_sec: int = 45
    # 길이에 맞추려고 뺀 장면 수 — 몇 장면이 빠졌는지 화면이 밝힐 수 있게
    omitted_scenes: int = 0


class AnniversaryItem(BaseModel):
    date: str
    label: str
    event_id: str
    days_left: int
    reason: str = ""


# --- TV Journey ---

class TVJourneyRequest(BaseModel):
    query: str  # "우리 가족의 2015년", "부산 여행" 등
    style: str = "timeline"  # "timeline" | "story" | "people"


class TVSlide(BaseModel):
    type: str  # "photo" | "video" | "title" | "narration"
    media_id: Optional[str] = None
    file_path: Optional[str] = None
    caption: str = ""
    event_id: Optional[str] = None
    event_title: Optional[str] = None
    date: Optional[str] = None


class TVJourneyResponse(BaseModel):
    id: str
    title: str
    slides: list[TVSlide]
    narration: str = ""
    total_duration_sec: int = 0
