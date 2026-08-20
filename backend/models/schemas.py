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
    # 그 설명을 누가 썼는지: ai_vision(모델이 사진을 보고 씀) | user_input
    scene_source: Optional[str] = None
    # 영상·음성일 때. 브라우저가 재서 보낸 값이다 (서버에 디코더를 두지 않는다)
    duration_sec: Optional[float] = None
    linked_event_id: Optional[str] = None
    needs_info: bool = False  # EXIF 없을 때 True
    message: str = "업로드 완료"


class MediaPersonTagRequest(BaseModel):
    """이 기록에 있는 사람을 지목한다 (보낸 목록이 최종 상태가 된다)

    얼굴 인식이 없으므로 사람이 직접 지목하는 것이 detected_faces의 유일한
    출처다. 빈 목록을 보내면 태그를 모두 떼는 뜻이다.
    """
    person_ids: list[str] = []


class MediaListItem(BaseModel):
    id: str
    media_type: str
    file_path: str
    thumbnail_path: Optional[str] = None
    original_filename: str
    created_at: str
    exif_date: Optional[str] = None
    # --- 음성·영상 ---
    # 길이는 둘 다 채워진다 (브라우저가 잰다). 파형은 음성만.
    duration_sec: Optional[float] = None
    waveform: list[float] = []
    transcript: Optional[str] = None
    # 그 글을 누가 썼는지: ai_stt(기계가 옮김) | user_input(사람이 적거나 고침).
    # 목소리의 출처(source)와 다른 축이다 — 화면이 둘을 따로 밝힌다.
    transcript_source: Optional[str] = None
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
    scene_source: Optional[str] = None
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
    # 이 추억에 기억이 얼마나 쌓였는가 (alone | shared | varied).
    # 확인 상태가 아니다 — 추억은 만든 순간 게시되고 확인 대기가 없다.
    memory_state: Optional[dict] = None


class MemoryDraftRequest(BaseModel):
    """올린 사진·영상으로 초안을 만들어 달라는 요청

    기본은 날짜·장소로 갈라서 묶음마다 초안 하나다. 여러 사건의 사진을 한꺼번에
    올리는 것이 정상이기 때문이다 — 어떤 사진이 같은 사건인지 사용자에게 묻지
    않는다. 갈린 결과가 틀렸으면 merge로 다시 부른다.
    """
    media_ids: list[str] = []
    # True면 가르지 않고 전부 한 추억으로 본다 (화면의 "전부 하나의 추억으로")
    merge: bool = False


class MemoryCreateRequest(BaseModel):
    """추억 만들기 (AI 초안을 그대로 쓰거나 고친 결과)

    저장되는 즉시 가족 공간에 게시된다. 승인 절차가 없다.
    """
    title: str
    description: str = ""
    date_start: Optional[str] = None
    # 그래프에 있는 장소를 고르면 place_id, 새 이름을 적으면 place_name
    place_id: Optional[str] = None
    place_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    person_ids: list[str] = []
    media_ids: list[str] = []
    # 만든 사람. 없으면 X-Viewer-Id로 들어온 사람이 만든 것으로 본다.
    author_id: Optional[str] = None


class ContributionRequest(BaseModel):
    """내 기억 더하기 (원본을 덮어쓰지 않는다)"""
    content: str
    person_id: Optional[str] = None
    # 함께 올린 사진·영상
    media_ids: list[str] = []
    # 음성으로 남긴 경우 그 녹음 id (기억의 근거로 이어진다)
    audio_media_id: Optional[str] = None
    # 다른 가족과 조금 다르게 기억한다고 밝힌 경우.
    # 한쪽을 정답으로 정하지 않고 안내문만 뜬다.
    differs: bool = False
    # user_input | ai_stt — ai_stt면 AI가 읽기 좋게 정리하고 원문도 남긴다
    source_type: Optional[str] = None


class MemoryMediaRequest(BaseModel):
    """기존 추억에 사진·영상 추가 (사용자가 고른 경우에만)"""
    media_ids: list[str] = []


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


# --- 사진첩 ---

class AlbumEventRef(BaseModel):
    """이 사진이 속한 추억. 사진첩에서 추억 상세로 되짚어 갈 고리다."""
    id: str
    title: str


class AlbumPlaceRef(BaseModel):
    """사진이 찍힌 곳. 사진첩은 이름만 쓴다 (점을 찍는 화면은 지도다)."""
    id: str
    name: str


class AlbumMediaItem(BaseModel):
    """사진첩 한 칸

    MediaListItem과 나눠 둔 이유: 목록 화면은 사건·인물·장소·공개 범위를 함께
    그려야 하는데, 그것을 기존 항목에 더하면 그 목록을 쓰는 홈·인물·채팅·TV의
    응답이 함께 무거워진다. 반대로 음성 전용 필드(파형·전사문)는 여기 없다.
    """
    id: str
    media_type: str
    file_path: str
    thumbnail_path: Optional[str] = None
    original_filename: str
    # 촬영일. exif_date가 없으면 올린 시각으로 채우고 has_exif=False로 밝힌다 —
    # 올린 시각을 촬영일이라 말하면 1998년 사진이 2026년 칸에 들어간다.
    captured_at: Optional[str] = None
    uploaded_at: str
    # 영상 길이 (브라우저가 재서 보낸 값)
    duration_sec: Optional[float] = None
    event: Optional[AlbumEventRef] = None
    # 사람이 직접 지목한 사람들만. 얼굴 인식이 없으므로 AI가 채우지 않는다.
    people: list[PersonRef] = []
    place: Optional[AlbumPlaceRef] = None
    visibility: str = "family"
    owner_id: Optional[str] = None
    # 촬영일을 카메라가 적었는가. False면 화면이 "날짜를 알 수 없는 사진"으로 묶는다.
    has_exif: bool = False


class AlbumResponse(BaseModel):
    items: list[AlbumMediaItem] = []
    # 다음 페이지를 부를 때 그대로 되돌려 보낸다. 없으면 마지막 페이지다.
    next_cursor: Optional[str] = None
    # 지금 조건에 맞는 전체 개수 (이 페이지 개수가 아니다)
    total: int = 0
    # 연도 필터만 뺀 조건에서 고를 수 있는 연도들 (최신순).
    # 고른 연도 때문에 나머지가 사라지면 되돌아갈 수 없다.
    available_years: list[int] = []


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
    # 기억이 쌓인 정도: alone(만든 사람의 기억만) | shared(가족이 더했다) |
    # varied(조금 다르게 기억하는 내용이 있다)
    state: str = "alone"
    # 나도 기억나요를 누른 사람 수
    echo_count: int = 0


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
    # 실제 모델이 이 답변을 썼는가. False면 키가 없거나 호출이 실패해 대체
    # 문장으로 답한 것이다 — 화면이 그 사실을 밝힌다.
    llm_used: bool = True
    # 어떤 모델이었는지 (폴백이면 None)
    model: Optional[str] = None
    # 어디로 갔는지: exaone(사내망) · friendli · bedrock. 모델 id만으로는 구분이
    # 안 된다 — Friendli는 전용 엔드포인트 id가 모델 이름 자리에 오기 때문이다.
    provider: Optional[str] = None


# --- Interview ---

class InterviewStartRequest(BaseModel):
    target_type: str = "event"  # "event" | "media" | "auto"
    target_id: Optional[str] = None
    # 지금 화면 앞에서 답할 사람. 인터뷰 대상이 이 사람이 된다 —
    # 질문받는 사람과 답하는 사람이 어긋나면 답변의 주인도 흐려진다.
    speaker_id: Optional[str] = None


class InterviewStartResponse(BaseModel):
    session_id: str
    question: str
    context: Optional[dict] = None  # 관련 미디어/이벤트 정보


class InterviewAnswerRequest(BaseModel):
    session_id: str
    answer: str
    # 누구의 기억으로 저장할지. 없으면 질문이 지목한 인물에게 귀속한다.
    # 기획안 08장의 귀속 원칙 — 답한 사람이 화면에서 정해지므로 그대로 받는다.
    speaker_id: Optional[str] = None
    # 말로 답한 경우 먼저 업로드된 음성 미디어 id.
    # 기억 문장에서 원본 음성으로 되짚을 수 있게 EVIDENCED_BY로 잇는다.
    audio_media_id: Optional[str] = None


class ExtractedFromAnswer(BaseModel):
    """답변에서 뽑아 그래프에 이은 것 (기획안 02장 "답변에서 사건·인물·시점 추출")

    화면이 그대로 보여 준다. 그래프가 조용히 자라면 말한 사람은 자기 말이
    어디로 갔는지 알 수 없다.
    """
    # 그래프에 있는 인물로 맞춰진 것 [{id, name, term}]
    persons: list[dict] = []
    place: Optional[dict] = None
    date: Optional[str] = None
    # 비어 있어서 이 답변으로 채운 사건 필드 (date_start · location_id)
    filled: list[str] = []
    # 답변에 나왔지만 그래프에 없어서 잇지 않은 표현. 없는 사람을 만들지 않는다.
    unmatched: list[str] = []


class InterviewAnswerResponse(BaseModel):
    session_id: str
    next_question: Optional[str] = None
    is_complete: bool = False
    extracted: Optional[ExtractedFromAnswer] = None
    updated_nodes: list[str] = []  # 업데이트된 노드 ID
    message: str = ""


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
    # 다른 가족의 추억에 "나도 기억나요"를 남긴 횟수
    echo_count: int = 0


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
    # 화면이 사진에 걸 카메라 움직임 (zoom-in | pan-left | zoom-out | pan-right).
    # None이면 아무것도 걸지 않는다 — 원본 영상이거나, 아래 클립을 재생하는 장면이다.
    # 무엇을 걸지는 서버만 정한다. 화면이 따로 고르면 ai_effects와 어긋난다.
    motion: Optional[str] = None
    # 미리 만들어 둔 미세 모션 클립. 있으면 사진 대신 이것을 재생한다.
    motion_url: Optional[str] = None
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
