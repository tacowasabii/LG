"""실제 데이터셋(data/metadata/)에서 Graph를 생성하는 시드 스크립트

data/photos, data/video, data/metadata/*.json을 읽어
Memory Graph를 구성하고 미디어 파일을 서빙 가능하게 연결합니다.
"""

import argparse
import sys
import json
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import (
    DATABASE_URL,
    GRAPH_FILE,
    MEDIA_DIR,
    METADATA_DIR,
    PHOTOS_DIR,
    VIDEO_DIR,
)
from backend.models.graph_models import (
    PersonNode, EventNode, PlaceNode, MediaNode, MemoryNode,
    Edge, RelationType, RelationCategory, Confidence, SourceType, MediaType,
)
from backend.services.graph_manager import graph_manager


ROLE_KR = {
    "father": "아빠",
    "mother": "엄마",
    "daughter": "딸",
    "son": "아들",
    "grandmother": "할머니",
}


def seed():
    print("🌱 실제 데이터셋으로 Graph 생성 중...")

    # 기존 그래프 초기화. 저장소가 파일인지 DB인지 여기서 알 필요가 없다.
    gm = graph_manager
    gm.reset()

    # 미디어 디렉토리 준비 - photos와 video를 media로 복사/심링크
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # --- Load metadata ---
    persons_data = json.loads((METADATA_DIR / "persons.json").read_text(encoding="utf-8"))
    events_data = json.loads((METADATA_DIR / "events.json").read_text(encoding="utf-8"))
    media_data = json.loads((METADATA_DIR / "media.json").read_text(encoding="utf-8"))
    memories_data = json.loads((METADATA_DIR / "memories.json").read_text(encoding="utf-8"))

    # === 1. Persons ===
    for p in persons_data:
        birth_year = int(p["birth_date"][:4]) if p.get("birth_date") else None
        person = PersonNode(
            id=p["person_id"],
            name=p["name"],
            relation=ROLE_KR.get(p.get("role", ""), p.get("role", "")),
            birth_year=birth_year,
            birth_date=p.get("birth_date"),
        )
        gm.add_person(person)
    print(f"  ✓ 가족 구성원 {len(persons_data)}명")

    # 사람 사이의 관계 엣지. relation_type에 관계명, category에 분류를 담는다.
    # 지금은 가족만 있지만 분류가 엣지에 실려 있어 넓힐 때 구조를 바꾸지 않는다.
    person_relations = [
        ("P01", "P02", "부부", RelationCategory.FAMILY),
        ("P01", "P03", "부녀", RelationCategory.FAMILY),
        ("P01", "P04", "부자", RelationCategory.FAMILY),
        ("P02", "P03", "모녀", RelationCategory.FAMILY),
        ("P02", "P04", "모자", RelationCategory.FAMILY),
        ("P03", "P04", "남매", RelationCategory.FAMILY),
        ("P05", "P03", "조손", RelationCategory.FAMILY),
        ("P05", "P04", "조손", RelationCategory.FAMILY),
    ]
    for src, tgt, rel, category in person_relations:
        gm.add_edge(Edge(
            source=src, target=tgt, relation=RelationType.RELATED_TO,
            properties={"relation_type": rel, "category": category},
        ))

    # === 2. Places (events에서 추출) ===
    places_map = {}  # event_id → place_id
    for ev in events_data:
        place_id = f"place_{ev['event_id']}"
        place = PlaceNode(
            id=place_id,
            name=ev.get("location_name", ""),
            lat=ev.get("lat"),
            lng=ev.get("lon"),
        )
        gm.add_place(place)
        places_map[ev["event_id"]] = place_id
    print(f"  ✓ 장소 {len(places_map)}개")

    # === 3. Events ===
    for ev in events_data:
        place_id = places_map.get(ev["event_id"])
        event = EventNode(
            id=ev["event_id"],
            title=ev["title"],
            description=ev.get("summary", ""),
            date_start=ev.get("date"),
            location_id=place_id,
            confidence=Confidence.CONFIRMED,
            source=SourceType.USER_INPUT,
        )
        gm.add_event(event)

        # Event → Place
        if place_id:
            gm.add_edge(Edge(source=ev["event_id"], target=place_id, relation=RelationType.LOCATED_AT))

    print(f"  ✓ 이벤트 {len(events_data)}개")

    # 이벤트 참여자 (media에서 등장 인물을 모아서 이벤트에 연결)
    event_participants: dict[str, set] = {ev["event_id"]: set() for ev in events_data}
    for m in media_data:
        for person_id in m.get("people", []):
            event_participants[m["event_id"]].add(person_id)

    for event_id, participants in event_participants.items():
        for person_id in participants:
            gm.add_edge(Edge(
                source=person_id,
                target=event_id,
                relation=RelationType.PARTICIPATED_IN,
                properties={"role": "참여자"},
            ))

    # === 4. Media ===
    photo_count = 0
    video_count = 0

    for m in media_data:
        filename = m["file_name"]
        src_path = PHOTOS_DIR / filename

        # 파일을 media 디렉토리로 복사 (이미 있으면 스킵)
        dest_path = MEDIA_DIR / filename
        if not dest_path.exists() and src_path.exists():
            shutil.copy2(str(src_path), str(dest_path))

        loc = m.get("location", {})
        taken_at = m.get("taken_at", "")

        media_node = MediaNode(
            id=m["media_id"],
            media_type=MediaType.PHOTO,
            file_path=f"/media-files/{filename}",
            thumbnail_path=f"/media-files/{filename}",
            original_filename=filename,
            exif_date=taken_at,
            exif_lat=loc.get("lat"),
            exif_lng=loc.get("lon"),
            exif_camera=m.get("camera", {}).get("model"),
            detected_faces=m.get("people", []),
            scene_description=m.get("description"),
            confidence=Confidence.CONFIRMED,
            source=SourceType.EXIF,
        )
        gm.add_media(media_node)
        photo_count += 1

        # Media → Event
        gm.add_edge(Edge(source=m["media_id"], target=m["event_id"], relation=RelationType.CAPTURED_DURING))

        # Media → Place
        place_id = places_map.get(m["event_id"])
        if place_id:
            gm.add_edge(Edge(source=m["media_id"], target=place_id, relation=RelationType.TAKEN_AT))

        # Media → Person (DEPICTS)
        for person_id in m.get("people", []):
            gm.add_edge(Edge(
                source=m["media_id"],
                target=person_id,
                relation=RelationType.DEPICTS,
                properties={"confidence": 1.0},
            ))

    # Video files
    if VIDEO_DIR.exists():
        for vid_file in VIDEO_DIR.iterdir():
            if vid_file.suffix.lower() in (".mp4", ".mov", ".avi"):
                dest_path = MEDIA_DIR / vid_file.name
                if not dest_path.exists():
                    shutil.copy2(str(vid_file), str(dest_path))

                # 파일명에서 이벤트 ID 추출 (E001.mp4 → E01, E007_01.mp4 → E07)
                stem = vid_file.stem
                event_id = None
                if stem.startswith("E"):
                    # E001 → E01, E006 → E06, E007_01 → E07
                    eid_part = stem.split("_")[0]
                    num = int(eid_part[1:])
                    event_id = f"E{num:02d}"

                vid_id = f"video_{stem}"
                vid_node = MediaNode(
                    id=vid_id,
                    media_type=MediaType.VIDEO,
                    file_path=f"/media-files/{vid_file.name}",
                    thumbnail_path=None,
                    original_filename=vid_file.name,
                    confidence=Confidence.CONFIRMED,
                    source=SourceType.USER_INPUT,
                )
                gm.add_media(vid_node)
                video_count += 1

                if event_id and event_id in event_participants:
                    gm.add_edge(Edge(source=vid_id, target=event_id, relation=RelationType.CAPTURED_DURING))

    print(f"  ✓ 사진 {photo_count}개 + 영상 {video_count}개")

    # === 5. Memories ===
    for mem in memories_data:
        memory = MemoryNode(
            id=mem["memory_id"],
            content=mem["content"],
            source_type=SourceType.INTERVIEW,
            contributor_id=mem.get("speaker"),
            confidence=Confidence.CONFIRMED,
        )
        gm.add_memory(memory)

        # Memory → Event
        if mem.get("event_id"):
            gm.add_edge(Edge(source=mem["memory_id"], target=mem["event_id"], relation=RelationType.ABOUT))

        # Person → Memory (REMEMBERS)
        if mem.get("speaker"):
            gm.add_edge(Edge(source=mem["speaker"], target=mem["memory_id"], relation=RelationType.REMEMBERS))

    print(f"  ✓ 기억 {len(memories_data)}개")

    # === Save ===
    gm.save()
    graph_data = gm.get_full_graph()
    print(f"\n✅ 실제 데이터셋 Graph 생성 완료!")
    print(f"   - 노드: {len(graph_data['nodes'])}개")
    print(f"   - 엣지: {len(graph_data['edges'])}개")
    print(f"   - 저장소: {_store_label()}")
    print(f"   - 미디어 서빙: {MEDIA_DIR}")


def _store_label() -> str:
    """어디에 넣었는지 (파일 경로를 무조건 찍으면 Postgres일 때 거짓말이 된다)"""
    return "Postgres (DATABASE_URL)" if DATABASE_URL else str(GRAPH_FILE)


def main() -> int:
    parser = argparse.ArgumentParser(description="metadata에서 Memory Graph를 만든다")
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="저장소가 비어 있을 때만 시드한다 (컨테이너 시작 시 사용)",
    )
    args = parser.parse_args()

    # 부팅마다 무조건 시드하면 가족이 쌓은 기억이 배포마다 날아간다 (seed()가
    # 먼저 reset()을 하기 때문이다). 그래서 "이미 데이터가 있나"를 저장소에
    # 직접 묻는다. 파일 존재로 판정하면 Postgres에서는 graph.json이 생기지 않아
    # 매 부팅 재시드 -> TRUNCATE가 된다 (실제로 그 상태였다).
    if args.if_empty and graph_manager.get_all_nodes():
        print(f"[seed] 이미 데이터가 있습니다. 건너뜁니다: {_store_label()}")
        return 0

    seed()
    return 0


if __name__ == "__main__":
    sys.exit(main())
