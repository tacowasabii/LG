"""샘플 데이터 시드 스크립트 - 데모용 가족 시나리오 생성"""

import sys
import json
from pathlib import Path

# 프로젝트 루트를 path에 추가
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import DATA_DIR, MEDIA_DIR, GRAPH_FILE
from backend.models.graph_models import (
    PersonNode, EventNode, PlaceNode, MediaNode, MemoryNode,
    Edge, RelationType, Confidence, SourceType, MediaType,
)
from backend.services.graph_manager import GraphManager


def create_placeholder_image(path: Path, label: str):
    """플레이스홀더 이미지 생성 (간단한 SVG)"""
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">
  <rect width="400" height="300" fill="#e2e8f0"/>
  <text x="200" y="140" text-anchor="middle" font-family="sans-serif" font-size="16" fill="#64748b">{label}</text>
  <text x="200" y="170" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#94a3b8">Sample Photo</text>
</svg>'''
    path.write_text(svg)


def seed():
    """데모용 샘플 데이터 생성"""
    print("🌱 샘플 데이터 생성 중...")

    # 기존 데이터 초기화
    if GRAPH_FILE.exists():
        GRAPH_FILE.unlink()

    # GraphManager 재초기화
    gm = GraphManager()
    gm._initialized = False
    gm.__init__()

    # === 1. 가족 구성원 (Person) ===
    persons = {
        "dad": PersonNode(id="person_dad", name="김철수", relation="아빠", birth_year=1970),
        "mom": PersonNode(id="person_mom", name="이영희", relation="엄마", birth_year=1972),
        "son": PersonNode(id="person_son", name="김민준", relation="아들", birth_year=2000),
        "daughter": PersonNode(id="person_daughter", name="김서연", relation="딸", birth_year=2003),
    }

    for person in persons.values():
        gm.add_person(person)
    print(f"  ✓ 가족 구성원 {len(persons)}명 생성")

    # 가족 관계 엣지
    family_edges = [
        Edge(source="person_dad", target="person_mom", relation=RelationType.RELATED_TO, properties={"category": "family", "relation_type": "부부"}),
        Edge(source="person_dad", target="person_son", relation=RelationType.RELATED_TO, properties={"category": "family", "relation_type": "부자"}),
        Edge(source="person_dad", target="person_daughter", relation=RelationType.RELATED_TO, properties={"category": "family", "relation_type": "부녀"}),
        Edge(source="person_mom", target="person_son", relation=RelationType.RELATED_TO, properties={"category": "family", "relation_type": "모자"}),
        Edge(source="person_mom", target="person_daughter", relation=RelationType.RELATED_TO, properties={"category": "family", "relation_type": "모녀"}),
        Edge(source="person_son", target="person_daughter", relation=RelationType.RELATED_TO, properties={"category": "family", "relation_type": "남매"}),
    ]
    for edge in family_edges:
        gm.add_edge(edge)

    # === 2. 장소 (Place) ===
    places = {
        "busan": PlaceNode(id="place_busan", name="해운대 해수욕장", address="부산광역시 해운대구", lat=35.1587, lng=129.1604),
        "jeju": PlaceNode(id="place_jeju", name="제주 성산일출봉", address="제주도 서귀포시 성산읍", lat=33.4590, lng=126.9425),
        "home": PlaceNode(id="place_home", name="우리 집", address="서울특별시 강남구", lat=37.4979, lng=127.0276),
        "school": PlaceNode(id="place_school", name="민준이 초등학교", address="서울특별시 강남구", lat=37.5013, lng=127.0394),
    }

    for place in places.values():
        gm.add_place(place)
    print(f"  ✓ 장소 {len(places)}개 생성")

    # === 3. 이벤트 (Event) ===
    events = {
        "busan_trip": EventNode(
            id="event_busan_trip",
            title="2015 부산 가족여행",
            description="가족 모두 함께한 첫 부산 여행. 해운대에서 수영하고 자갈치 시장에서 회를 먹었다.",
            date_start="2015-07-20",
            date_end="2015-07-22",
            location_id="place_busan",
            confidence=Confidence.CONFIRMED,
            source=SourceType.USER_INPUT,
        ),
        "jeju_trip": EventNode(
            id="event_jeju_trip",
            title="2018 제주도 여행",
            description="민준이 고등학교 입학 전 마지막 가족 여행",
            date_start="2018-01-15",
            date_end="2018-01-18",
            location_id="place_jeju",
            confidence=Confidence.CONFIRMED,
            source=SourceType.USER_INPUT,
        ),
        "graduation": EventNode(
            id="event_graduation",
            title="민준이 초등학교 졸업",
            description="",  # 설명 없음 (인터뷰가 물어볼 자리)
            date_start="2013-02-15",
            location_id="place_school",
            confidence=Confidence.CONFIRMED,
            source=SourceType.USER_INPUT,
        ),
        "birthday_2020": EventNode(
            id="event_birthday_2020",
            title="서연이 생일파티 2020",
            description="서연이의 17번째 생일. 코로나 때문에 가족끼리만 집에서 축하했다.",
            date_start="2020-05-12",
            location_id="place_home",
            confidence=Confidence.CONFIRMED,
            source=SourceType.USER_INPUT,
        ),
        "new_year_2023": EventNode(
            id="event_new_year_2023",
            title="2023 설날",
            description="",  # 설명 없음
            date_start="2023-01-22",
            location_id=None,  # 장소 없음
            confidence=Confidence.AI_INFERRED,
            source=SourceType.AI_VISION,
        ),
    }

    for event in events.values():
        gm.add_event(event)
    print(f"  ✓ 이벤트 {len(events)}개 생성")

    # 이벤트-장소 연결
    event_place_edges = [
        Edge(source="event_busan_trip", target="place_busan", relation=RelationType.LOCATED_AT),
        Edge(source="event_jeju_trip", target="place_jeju", relation=RelationType.LOCATED_AT),
        Edge(source="event_graduation", target="place_school", relation=RelationType.LOCATED_AT),
        Edge(source="event_birthday_2020", target="place_home", relation=RelationType.LOCATED_AT),
    ]
    for edge in event_place_edges:
        gm.add_edge(edge)

    # 이벤트-참여자 연결
    participation_edges = [
        # 부산 여행 - 전 가족
        Edge(source="person_dad", target="event_busan_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_mom", target="event_busan_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_son", target="event_busan_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_daughter", target="event_busan_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        # 제주 여행 - 전 가족
        Edge(source="person_dad", target="event_jeju_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_mom", target="event_jeju_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_son", target="event_jeju_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_daughter", target="event_jeju_trip", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        # 졸업식 - 전 가족
        Edge(source="person_dad", target="event_graduation", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_mom", target="event_graduation", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_son", target="event_graduation", relation=RelationType.PARTICIPATED_IN, properties={"role": "주인공"}),
        # 생일 - 전 가족
        Edge(source="person_dad", target="event_birthday_2020", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_mom", target="event_birthday_2020", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_son", target="event_birthday_2020", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_daughter", target="event_birthday_2020", relation=RelationType.PARTICIPATED_IN, properties={"role": "주인공"}),
        # 설날 - 아빠, 엄마만 (나머지 참여자는 아직 기록에 없다)
        Edge(source="person_dad", target="event_new_year_2023", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
        Edge(source="person_mom", target="event_new_year_2023", relation=RelationType.PARTICIPATED_IN, properties={"role": "참여자"}),
    ]
    for edge in participation_edges:
        gm.add_edge(edge)

    # === 4. 미디어 (Media) - 플레이스홀더 ===
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    media_items = [
        MediaNode(
            id="media_busan_01",
            media_type=MediaType.PHOTO,
            file_path="/media-files/busan_beach_01.svg",
            thumbnail_path="/media-files/busan_beach_01.svg",
            original_filename="busan_beach_01.jpg",
            exif_date="2015-07-20T14:30:00",
            exif_lat=35.1587,
            exif_lng=129.1604,
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
            detected_faces=["person_dad", "person_son"],
        ),
        MediaNode(
            id="media_busan_02",
            media_type=MediaType.PHOTO,
            file_path="/media-files/busan_sunset_02.svg",
            thumbnail_path="/media-files/busan_sunset_02.svg",
            original_filename="busan_sunset_02.jpg",
            exif_date="2015-07-21T18:45:00",
            exif_lat=35.1587,
            exif_lng=129.1604,
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
            detected_faces=["person_mom", "person_daughter"],
        ),
        MediaNode(
            id="media_jeju_01",
            media_type=MediaType.PHOTO,
            file_path="/media-files/jeju_sunrise_01.svg",
            thumbnail_path="/media-files/jeju_sunrise_01.svg",
            original_filename="jeju_sunrise_01.jpg",
            exif_date="2018-01-16T06:30:00",
            exif_lat=33.4590,
            exif_lng=126.9425,
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
            detected_faces=["person_dad", "person_mom", "person_son", "person_daughter"],
        ),
        MediaNode(
            id="media_jeju_02",
            media_type=MediaType.PHOTO,
            file_path="/media-files/jeju_horse_02.svg",
            thumbnail_path="/media-files/jeju_horse_02.svg",
            original_filename="jeju_horse_02.jpg",
            exif_date="2018-01-17T11:00:00",
            exif_lat=33.4100,
            exif_lng=126.5700,
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
            detected_faces=["person_daughter"],
        ),
        MediaNode(
            id="media_graduation_01",
            media_type=MediaType.PHOTO,
            file_path="/media-files/graduation_01.svg",
            thumbnail_path="/media-files/graduation_01.svg",
            original_filename="graduation_01.jpg",
            exif_date="2013-02-15T10:00:00",
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
            detected_faces=["person_son"],
        ),
        MediaNode(
            id="media_birthday_01",
            media_type=MediaType.PHOTO,
            file_path="/media-files/birthday_2020_01.svg",
            thumbnail_path="/media-files/birthday_2020_01.svg",
            original_filename="birthday_2020_01.jpg",
            exif_date="2020-05-12T19:00:00",
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
            detected_faces=["person_daughter", "person_mom"],
        ),
        MediaNode(
            id="media_birthday_02",
            media_type=MediaType.VIDEO,
            file_path="/media-files/birthday_2020_video.svg",
            thumbnail_path="/media-files/birthday_2020_video.svg",
            original_filename="birthday_2020_video.mp4",
            exif_date="2020-05-12T19:30:00",
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
        ),
        MediaNode(
            id="media_voice_dad",
            media_type=MediaType.AUDIO,
            file_path="/media-files/dad_memory_busan.svg",
            thumbnail_path=None,
            original_filename="dad_memory_busan.m4a",
            exif_date="2024-03-10T20:00:00",
            confidence=Confidence.CONFIRMED,
            source=SourceType.AI_STT,
        ),
    ]

    for media in media_items:
        gm.add_media(media)
        # 플레이스홀더 이미지 생성
        filename = Path(media.file_path).name
        create_placeholder_image(MEDIA_DIR / filename, media.original_filename)

    print(f"  ✓ 미디어 {len(media_items)}개 생성 (플레이스홀더)")

    # 미디어-이벤트 연결
    media_event_edges = [
        Edge(source="media_busan_01", target="event_busan_trip", relation=RelationType.CAPTURED_DURING),
        Edge(source="media_busan_02", target="event_busan_trip", relation=RelationType.CAPTURED_DURING),
        Edge(source="media_jeju_01", target="event_jeju_trip", relation=RelationType.CAPTURED_DURING),
        Edge(source="media_jeju_02", target="event_jeju_trip", relation=RelationType.CAPTURED_DURING),
        Edge(source="media_graduation_01", target="event_graduation", relation=RelationType.CAPTURED_DURING),
        Edge(source="media_birthday_01", target="event_birthday_2020", relation=RelationType.CAPTURED_DURING),
        Edge(source="media_birthday_02", target="event_birthday_2020", relation=RelationType.CAPTURED_DURING),
        Edge(source="media_voice_dad", target="event_busan_trip", relation=RelationType.CAPTURED_DURING),
    ]
    for edge in media_event_edges:
        gm.add_edge(edge)

    # 미디어-인물 연결
    media_person_edges = [
        Edge(source="media_busan_01", target="person_dad", relation=RelationType.DEPICTS, properties={"confidence": 0.95}),
        Edge(source="media_busan_01", target="person_son", relation=RelationType.DEPICTS, properties={"confidence": 0.92}),
        Edge(source="media_busan_02", target="person_mom", relation=RelationType.DEPICTS, properties={"confidence": 0.93}),
        Edge(source="media_busan_02", target="person_daughter", relation=RelationType.DEPICTS, properties={"confidence": 0.91}),
        Edge(source="media_jeju_01", target="person_dad", relation=RelationType.DEPICTS, properties={"confidence": 0.90}),
        Edge(source="media_jeju_01", target="person_mom", relation=RelationType.DEPICTS, properties={"confidence": 0.88}),
        Edge(source="media_jeju_01", target="person_son", relation=RelationType.DEPICTS, properties={"confidence": 0.89}),
        Edge(source="media_jeju_01", target="person_daughter", relation=RelationType.DEPICTS, properties={"confidence": 0.87}),
        Edge(source="media_jeju_02", target="person_daughter", relation=RelationType.DEPICTS, properties={"confidence": 0.95}),
        Edge(source="media_graduation_01", target="person_son", relation=RelationType.DEPICTS, properties={"confidence": 0.96}),
        Edge(source="media_birthday_01", target="person_daughter", relation=RelationType.DEPICTS, properties={"confidence": 0.94}),
        Edge(source="media_birthday_01", target="person_mom", relation=RelationType.DEPICTS, properties={"confidence": 0.90}),
    ]
    for edge in media_person_edges:
        gm.add_edge(edge)

    # 미디어-장소 연결
    media_place_edges = [
        Edge(source="media_busan_01", target="place_busan", relation=RelationType.TAKEN_AT),
        Edge(source="media_busan_02", target="place_busan", relation=RelationType.TAKEN_AT),
        Edge(source="media_jeju_01", target="place_jeju", relation=RelationType.TAKEN_AT),
        Edge(source="media_graduation_01", target="place_school", relation=RelationType.TAKEN_AT),
        Edge(source="media_birthday_01", target="place_home", relation=RelationType.TAKEN_AT),
    ]
    for edge in media_place_edges:
        gm.add_edge(edge)

    # === 5. 기억 (Memory) ===
    memories = [
        MemoryNode(
            id="memory_dad_busan",
            content="그때 해운대에서 민준이가 파도에 넘어져서 바지가 다 젖었었지. 그래도 너무 신나서 계속 물에 들어갔어.",
            source_type=SourceType.INTERVIEW,
            contributor_id="person_dad",
            confidence=Confidence.CONFIRMED,
        ),
        MemoryNode(
            id="memory_mom_busan",
            content="자갈치 시장에서 회를 먹었는데, 서연이가 아직 날것을 못 먹어서 새우튀김만 먹었어요. 그래도 좋아했어요.",
            source_type=SourceType.INTERVIEW,
            contributor_id="person_mom",
            confidence=Confidence.CONFIRMED,
        ),
        MemoryNode(
            id="memory_son_jeju",
            content="제주도에서 말 타기 체험했는데 누나가 말 위에서 무서워서 울었어요. 저는 재밌었는데.",
            source_type=SourceType.INTERVIEW,
            contributor_id="person_son",
            confidence=Confidence.CONFIRMED,
        ),
    ]

    for memory in memories:
        gm.add_memory(memory)
    print(f"  ✓ 기억 {len(memories)}개 생성")

    # 기억-이벤트 연결
    memory_event_edges = [
        Edge(source="memory_dad_busan", target="event_busan_trip", relation=RelationType.ABOUT),
        Edge(source="memory_mom_busan", target="event_busan_trip", relation=RelationType.ABOUT),
        Edge(source="memory_son_jeju", target="event_jeju_trip", relation=RelationType.ABOUT),
    ]
    for edge in memory_event_edges:
        gm.add_edge(edge)

    # 기억-인물 연결 (누가 기억하는지)
    memory_person_edges = [
        Edge(source="person_dad", target="memory_dad_busan", relation=RelationType.REMEMBERS),
        Edge(source="person_mom", target="memory_mom_busan", relation=RelationType.REMEMBERS),
        Edge(source="person_son", target="memory_son_jeju", relation=RelationType.REMEMBERS),
    ]
    for edge in memory_person_edges:
        gm.add_edge(edge)

    # === 완료 ===
    gm.save()

    # 결과 요약
    graph_data = gm.get_full_graph()
    print(f"\n✅ 샘플 데이터 생성 완료!")
    print(f"   - 노드: {len(graph_data['nodes'])}개")
    print(f"   - 엣지: {len(graph_data['edges'])}개")
    print(f"   - Graph 파일: {GRAPH_FILE}")
    print(f"   - 미디어 디렉토리: {MEDIA_DIR}")

    # Gap 확인
    print(f"\n📋 예상 Memory Gap:")
    print(f"   - event_graduation: 설명 없음")
    print(f"   - event_new_year_2023: 설명 없음, 장소 없음")
    print(f"   - event_new_year_2023: 미디어 없음")
    print(f"   - event_jeju_trip: 딸(서연)의 기억 없음 (한쪽 관점)")


if __name__ == "__main__":
    seed()
