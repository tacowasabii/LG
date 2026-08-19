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


class EventListItem(BaseModel):
    id: str
    title: str
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    location_name: Optional[str] = None
    participant_count: int = 0
    media_count: int = 0


# --- Chat ---

class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


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
