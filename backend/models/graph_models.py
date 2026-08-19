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
    FAMILY_OF = "family_of"


# --- Node Data Classes ---

def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class PersonNode:
    id: str = field(default_factory=lambda: _gen_id("person"))
    node_type: str = field(default=NodeType.PERSON, init=False)
    name: str = ""
    relation: str = ""  # 아빠, 엄마, 아들, 딸 등
    birth_year: Optional[int] = None
    # 연도만으로는 나이가 1살까지 어긋난다 (생일 경과 여부를 알 수 없음)
    birth_date: Optional[str] = None  # ISO date string
    thumbnail_url: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


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
    # e.g., {"role": "주인공"}, {"confidence": 0.9}, {"relation_type": "부자"}


# --- Utility ---

def node_to_dict(node) -> dict:
    """Convert any node dataclass to dict for serialization."""
    return asdict(node)


def edge_to_dict(edge: Edge) -> dict:
    return asdict(edge)
