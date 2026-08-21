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
    # 사람 사이의 관계. 구체적인 관계명은 properties.relation_type,
    # 분류는 properties.category.
    RELATED_TO = "related_to"


class RelationCategory(str, Enum):
    """사람 사이 관계의 분류

    같은 RELATED_TO 엣지를 쓰되 이 값으로 구분한다. 지금은 가족만 다룬다.
    친구·연인처럼 가족 밖 관계로 넓힐 때는 값을 여기에 더하면 된다 —
    엣지 구조와 category 필드는 그대로 두므로 스키마를 바꾸지 않고 확장된다.
    """
    FAMILY = "family"


# --- Node Data Classes ---

def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class PersonNode:
    id: str = field(default_factory=lambda: _gen_id("person"))
    node_type: str = field(default=NodeType.PERSON, init=False)
    name: str = ""
    # 아빠, 엄마, 딸, 아들, 할머니 등.
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


class MemoryState(str, Enum):
    """추억 하나에 기억이 얼마나 쌓였는가 (저장하지 않고 기억에서 파생한다)

    확인 상태(맞음/모름/이견)를 대신한다. 추억은 한 사람이 만들면 그 순간
    가족 공간에 게시되므로 "확인 대기"라는 상태가 없다. 남는 질문은 하나뿐이다 —
    이 기억에 가족이 얼마나 함께 있는가.

    VARIED는 문제 표시가 아니다. 가족이 다르게 기억하는 것은 고쳐야 할 오류가
    아니라 그대로 보존할 사실이다. 한쪽을 정답으로 정하지 않는다.
    """
    ALONE = "alone"    # 만든 사람의 기억만 있다
    SHARED = "shared"  # 가족이 기억을 더했다
    VARIED = "varied"  # 조금 다르게 기억하는 내용이 함께 있다


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
    # 이 추억을 만든 사람. 한 명이 만들면 그 자리에서 가족 공간에 게시된다 —
    # 다른 가족의 승인을 기다리지 않는다.
    author_id: Optional[str] = None
    # "나도 기억나요". 확인이 아니라 공감이다. 아무도 누르지 않아도 추억은 그대로
    # 남는다. [{"person_id": "P01", "at": "..."}]
    echoes: list = field(default_factory=list)
    # AI가 여러 사람의 기억을 엮어 쓴 "함께 기억한 이야기". 누가 맞는지 가리지
    # 않고 서로 다른 관점을 그대로 서술한다. 기억이 더 쌓이면 다시 쓴다.
    together_story: Optional[str] = None
    together_story_at: Optional[str] = None
    # 그 이야기를 쓸 때 근거로 삼은 기억 개수. 지금 개수보다 작으면 이야기가
    # 낡은 것이다 (새로 더해진 기억이 아직 들어가지 않았다).
    together_story_basis: int = 0
    # 그 이야기를 쓸 때 함께한 사람이 몇 명이었는지. 사진에서 나중에 지목한
    # 사람이 늘면 이 값보다 많아지고, 그때도 이야기는 낡은 것이다.
    together_story_persons: int = 0
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
    # 그 설명을 누가 썼는지. 노드 전체의 source(사진은 보통 exif)와 다른 축이다 —
    # 날짜는 카메라가 적었고 설명은 모델이 썼다. transcript_source와 같은 구조.
    #   ai_vision  : 모델이 사진을 보고 썼다
    #   user_input : 사람이 적었다
    scene_source: Optional[str] = None
    # detected_faces를 누가 정했는지. 화면이 "AI가 알아봤다"고 밝힐 수 있게 한다.
    #   ai_vision  : 얼굴 인식이 채웠다 (추정 — 사람이 끌 수 있다)
    #   user_input : 사람이 지목했다
    faces_source: Optional[str] = None
    # 사진에서 찾은 얼굴의 위치와 그 얼굴이 누구인지.
    # 상세 화면이 사진 위에 이름을 얹는 근거다 (services/faces.identify).
    # 비율 좌표라 원본 크기가 바뀌어도 그대로 쓴다.
    #   [{"box": {"left":.., "top":.., "width":.., "height":..},
    #     "person_id": "P01" | None, "similarity": 100.0, "reason": ""}]
    #
    # 저장하는 이유: Rekognition 호출이 사진당 여러 번이라 상세를 열 때마다
    # 다시 부르면 느리고 비싸다. 한 번 찾은 것을 들고 있는다.
    face_boxes: list = field(default_factory=list)
    confidence: str = Confidence.USER_UNVERIFIED
    source: str = SourceType.EXIF
    # --- 음성/영상 ---
    # 길이와 파형은 브라우저가 녹음 직후 계산해 보낸다. 서버에 오디오 디코더를
    # 두지 않기 위한 선택이다 (ffmpeg 의존성 없이 파형을 그린다).
    duration_sec: Optional[float] = None
    waveform: list = field(default_factory=list)  # 0~1 정규화된 피크
    # 음성을 글로 옮긴 원문. 요약이 아니라 말한 그대로를 보존한다.
    transcript: Optional[str] = None
    # 그 글을 누가 썼는지. 노드 전체의 source와 따로 둔다 — 목소리는 사람이
    # 남긴 것(interview)이지만 글은 기계가 옮긴 것(ai_stt)일 수 있고, 둘을 한
    # 필드로 합치면 어느 쪽 신뢰도인지 읽을 수 없다.
    #   ai_stt     : 브라우저 음성 인식이 옮기고 사람이 손대지 않았다
    #   user_input : 사람이 적었거나, 옮겨진 글을 고쳤다
    transcript_source: Optional[str] = None
    # 이 음성에서 말하는 사람 (NARRATED_BY 엣지와 함께 저장한다)
    speaker_id: Optional[str] = None
    # --- 권한 (기획안 08장 Asset 권한) ---
    # 올린 사람. 공개 범위를 정할 수 있는 사람이고, 비공개로 두면 이 사람만 본다.
    owner_id: Optional[str] = None
    visibility: str = "family"
    # visibility가 partial일 때 열람 가능한 인물
    allowed_ids: list = field(default_factory=list)


class MemoryKind(str, Enum):
    """이 기억이 추억에서 어떤 자리인가

    상세 화면이 "최초 작성자의 기억"과 "가족이 더한 기억"을 따로 세워 보여주기
    때문에 구분이 필요하다. 더한 기억은 원본을 덮어쓰지 않는다.
    """
    AUTHOR = "author"              # 추억을 만든 사람이 처음 쓴 기억
    CONTRIBUTION = "contribution"  # 가족이 나중에 더한 기억


@dataclass
class MemoryNode:
    id: str = field(default_factory=lambda: _gen_id("memory"))
    node_type: str = field(default=NodeType.MEMORY, init=False)
    content: str = ""
    # 이 기억이 어떤 질문에 대한 답인가 (인터뷰로 남긴 기억만 채워진다).
    # 답만 남기면 "모르겠어요" 같은 짧은 답이 무엇에 대한 것인지 사라진다 —
    # 채팅이 그 기억을 근거로 잡아도 무엇을 모른다는 것인지 말할 수 없었다.
    question: Optional[str] = None
    source_type: str = SourceType.USER_INPUT
    contributor_id: Optional[str] = None  # person_id
    confidence: str = Confidence.CONFIRMED
    # author = 만든 사람의 첫 기억, contribution = 가족이 더한 기억
    kind: str = MemoryKind.CONTRIBUTION
    # AI가 읽기 좋게 다듬은 문장. content(사람이 말한 원문)는 덮어쓰지 않는다 —
    # 화면은 원문을 함께 되짚을 수 있게 둔다 (출처 보존).
    polished: Optional[str] = None
    # 다른 가족과 조금 다르게 기억한다고 밝힌 기억. 한쪽을 정답으로 정하지 않고
    # 화면에는 "가족들이 조금 다르게 기억하고 있어요"로만 알린다.
    differs: bool = False
    # 이 기억과 함께 올린 사진·영상 (EVIDENCED_BY 엣지와 함께 저장한다)
    media_ids: list = field(default_factory=list)
    # 이 문장에서 뽑아낸 작은 "기억 맥락" (선택). 원문(content)은 손대지 않는다 —
    # 여기 들어오는 것은 파생값이고, 추억의 제목·날짜·장소·정체성은 이 값으로
    # 바뀌지 않는다 (services/memory_context.py).
    #
    #   {"speaker_id": "P02", "subject_person_ids": ["P03"],
    #    "scene": "부산 바다", "action": "물장구치던",
    #    "highlight": "가장 재미있게 기억하는 순간",
    #    "confidence": "explicit" | "inferred",
    #    "unmatched": ["큰엄마"],            그래프에 없어서 잇지 못한 호칭
    #    "media_ids": ["E01_001"],           이 맥락이 가리키는 원본
    #    "media_basis": "attached" | "scene" | "person" | None,
    #    "visual_treatment": "subject-focus" | None}
    #
    # 별도 노드로 떼어 두지 않은 이유: 맥락은 기억에 딸린 값이라 기억을 지우면
    # 함께 사라져야 한다. 노드로 두면 거둔 말의 맥락이 그래프에 남고 Film 자막에서
    # 계속 읽힌다.
    context: Optional[dict] = None
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
