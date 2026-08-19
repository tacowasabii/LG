"""Graph 노드/엣지 데이터 모델 (내부 저장용)"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import uuid
from datetime import datetime


# --- Enums ---

class NodeType(str, Enum):
    PERSON = "person"
    EVENT = "event"
    PLACE = "place"
    MEDIA = "media"
    MEMORY = "memory"


class MediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"


class Confidence(str, Enum):
    CONFIRMED = "confirmed"
    AI_INFERRED = "ai_inferred"
    USER_UNVERIFIED = "user_unverified"


class SourceType(str, Enum):
    EXIF = "exif"
    USER_INPUT = "user_input"
    AI_VISION = "ai_vision"
    AI_STT = "ai_stt"
    INTERVIEW = "interview"


class RelationType(str, Enum):
    PARTICIPATED_IN = "participated_in"
    TAKEN_AT = "taken_at"
    CAPTURED_DURING = "captured_during"
    DEPICTS = "depicts"
    LOCATED_AT = "located_at"
    REMEMBERS = "remembers"
    ABOUT = "about"
    # 이 음성·영상에서 말하는 사람 (Media -> Person).
    # DEPICTS(사진에 찍힌 사람)와 구분한다. 목소리의 주인은 화면에 없을 수도 있다.
    NARRATED_BY = "narrated_by"
    # 이 기억의 근거가 되는 원본 기록 (Memory -> Media).
    # 기획안의 "출처 보존" — 기억 문장에서 원본 음성으로 되짚을 수 있어야 한다.
    EVIDENCED_BY = "evidenced_by"
    # 사람 사이의 관계. 가족에 한정하지 않는다 (친구·연인도 같은 엣지로 표현).
    # 구체적인 관계명은 properties.relation_type, 분류는 properties.category.
    RELATED_TO = "related_to"


class RelationCategory(str, Enum):
    """사람 사이 관계의 분류

    같은 RELATED_TO 엣지를 쓰되 이 값으로 구분한다. 가족만 다루던 스키마를
    친구·연인까지 넓히면서 도입했다.
    """
    FAMILY = "family"
    FRIEND = "friend"
    PARTNER = "partner"


# --- Node Data Classes ---

def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class PersonNode:
    id: str = field(default_factory=lambda: _gen_id("person"))
    node_type: str = field(default=NodeType.PERSON, init=False)
    name: str = ""
    # 아빠, 엄마, 딸, 아들, 할머니 / 친구, 연인 등. 가족에 한정하지 않는다.
    relation: str = ""
    birth_year: Optional[int] = None
    # 연도만으로는 나이가 1살까지 어긋난다 (생일 경과 여부를 알 수 없음)
    birth_date: Optional[str] = None  # ISO date string
    thumbnail_url: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # --- 가족 공간 (기획안 02장 Family Space · 08장 인물 동의) ---
    # 기본값은 기록자. 시드 데이터의 인물도 모두 참여자로 본다.
    role: str = "contributor"
    joined_at: Optional[str] = None
    # 이 사람이 등장하는 기록을 가족 공유에서 빼 달라는 요청.
    # 원본을 지우지 않는다 — 올린 사람만 볼 수 있게 된다.
    private_request: bool = False


class FamilyRole(str, Enum):
    """가족 공간에서의 역할 (기획안 02장 Family Space)

    권한이 아니라 참여 방식의 구분이다. 열람자도 함께 보고 듣지만 기록을 바꾸지
    않고, 초대 대기는 아직 참여하지 않은 상태다.
    """
    OWNER = "owner"            # 가족 관리자 — 초대·공개 범위·삭제를 결정한다
    CONTRIBUTOR = "contributor"  # 기록자 — 올리고 기억을 남기고 확인에 참여한다
    VIEWER = "viewer"          # 열람자 — 함께 보지만 바꾸지 않는다
    INVITED = "invited"        # 초대 대기 — 링크를 보냈고 아직 들어오지 않았다


class Visibility(str, Enum):
    """기록 하나의 공개 범위 (기획안 08장 Asset 권한)

    가족 데이터는 기본 비공개다. FAMILY는 "이 가족 공간 안에서 전체"를 뜻하고,
    바깥으로 나가는 범위는 없다.
    """
    FAMILY = "family"    # 참여한 구성원 모두
    PARTIAL = "partial"  # allowed_ids에 있는 사람만
    PRIVATE = "private"  # 올린 사람만


class VerifyAction(str, Enum):
    """가족이 사건을 확인할 때 할 수 있는 행동

    기획안: "맞음 / 수정 / 모름". 이견(dispute)은 사실을 지우는 대신 다른 버전의
    기억으로 보존한다.
    """
    CONFIRM = "confirm"      # 맞음
    UNKNOWN = "unknown"      # 모르겠어요 (확인 불가도 정보다)
    DISPUTE = "dispute"      # 내 기억은 다르다


class VerificationState(str, Enum):
    """사건의 확인 상태 (저장하지 않고 verifications·기억에서 파생한다)"""
    CONFIRMED = "confirmed"    # 가족 확인 완료
    SUPPORTED = "supported"    # 다중 근거 일치
    INFERRED = "inferred"      # AI 추정·확인 필요
    CONFLICTED = "conflicted"  # 기억 또는 근거 충돌


@dataclass
class EventNode:
    id: str = field(default_factory=lambda: _gen_id("event"))
    node_type: str = field(default=NodeType.EVENT, init=False)
    title: str = ""
    description: str = ""
    date_start: Optional[str] = None  # ISO date string
    date_end: Optional[str] = None
    location_id: Optional[str] = None
    confidence: str = Confidence.USER_UNVERIFIED
    source: str = SourceType.USER_INPUT
    # 가족 확인 이력. 확인자와 확인 시점을 함께 남긴다 (기획안 공통 속성).
    # [{"person_id": "P01", "action": "confirm", "at": "...", "note": "..."}]
    # confidence(자료 출처의 신뢰도)와는 별개 축이다.
    verifications: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PlaceNode:
    id: str = field(default_factory=lambda: _gen_id("place"))
    node_type: str = field(default=NodeType.PLACE, init=False)
    name: str = ""
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MediaNode:
    id: str = field(default_factory=lambda: _gen_id("media"))
    node_type: str = field(default=NodeType.MEDIA, init=False)
    media_type: str = MediaType.PHOTO
    file_path: str = ""
    thumbnail_path: Optional[str] = None
    original_filename: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # EXIF metadata
    exif_date: Optional[str] = None
    exif_lat: Optional[float] = None
    exif_lng: Optional[float] = None
    exif_camera: Optional[str] = None
    # AI analysis results
    detected_faces: list = field(default_factory=list)  # list of person_ids
    scene_description: Optional[str] = None
    confidence: str = Confidence.USER_UNVERIFIED
    source: str = SourceType.EXIF
    # --- 음성/영상 ---
    # 길이와 파형은 브라우저가 녹음 직후 계산해 보낸다. 서버에 오디오 디코더를
    # 두지 않기 위한 선택이다 (ffmpeg 의존성 없이 파형을 그린다).
    duration_sec: Optional[float] = None
    waveform: list = field(default_factory=list)  # 0~1 정규화된 피크
    # 음성을 글로 옮긴 원문. 요약이 아니라 말한 그대로를 보존한다.
    transcript: Optional[str] = None
    # 이 음성에서 말하는 사람 (NARRATED_BY 엣지와 함께 저장한다)
    speaker_id: Optional[str] = None
    # --- 권한 (기획안 08장 Asset 권한) ---
    # 올린 사람. 공개 범위를 정할 수 있는 사람이고, 비공개로 두면 이 사람만 본다.
    owner_id: Optional[str] = None
    visibility: str = "family"
    # visibility가 partial일 때 열람 가능한 인물
    allowed_ids: list = field(default_factory=list)


@dataclass
class MemoryNode:
    id: str = field(default_factory=lambda: _gen_id("memory"))
    node_type: str = field(default=NodeType.MEMORY, init=False)
    content: str = ""
    source_type: str = SourceType.USER_INPUT
    contributor_id: Optional[str] = None  # person_id
    confidence: str = Confidence.CONFIRMED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# --- Edge Data Class ---

@dataclass
class Edge:
    source: str = ""  # node id
    target: str = ""  # node id
    relation: str = RelationType.PARTICIPATED_IN
    properties: dict = field(default_factory=dict)
    # e.g., {"role": "주인공"}, {"confidence": 0.9},
    #       {"relation_type": "부자", "category": "family"}


# --- Utility ---

def node_to_dict(node) -> dict:
    """Convert any node dataclass to dict for serialization."""
    return asdict(node)


def edge_to_dict(edge: Edge) -> dict:
    return asdict(edge)
