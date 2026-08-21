"""시드 사진을 정답 메타데이터의 id로 되돌린다

배포 화면에서 사진을 지우고 같은 파일을 다시 올리면 노드 id가 새로 발급된다
(E06_001 -> media_deb40ef6). 파일도 추억 연결도 살아 있어서 화면에는 그대로
보이지만, 정답표(data/metadata/media.json)가 그 사진을 E06_001로 적어 두었기
때문에 Trust Harness의 Relation Accuracy가 그 관계를 찾지 못한다. 배포에서
기대 154개 중 15개가 이렇게 빠져 90.3이 나왔다 — E06 사진 3장 × (추억 연결
1개 + 인물 4명).

다시 올린 사진은 인물 정보도 잃는다. 업로드 경로는 EXIF(촬영일시·좌표)는
읽어 오지만 "이 사진에 누가 있나"는 모른다 — 그건 메타데이터가 사람 손으로
준 값(manual_ground_truth)이다. 그래서 되돌리면 점수와 함께 화면도 낫는다.

seed_from_metadata.py는 쓸 수 없다. 그 스크립트는 gm.reset()으로 시작해서
배포 DB를 비운다 — 가족이 올린 사진과 남긴 기억이 함께 사라진다.

    python scripts/restore_seed_media.py --dry-run     # 계획만 본다 (쓰지 않는다)
    python scripts/restore_seed_media.py               # 어긋난 것 전부
    python scripts/restore_seed_media.py --media E06_001 E06_002 E06_003

배포를 고칠 때는 그 저장소를 붙여 돌린다. 붙이지 않으면 로컬 graph.json을 고친다.

    DATABASE_URL="postgresql://..." python scripts/restore_seed_media.py

고친 뒤에도 /trust 화면의 숫자는 그대로다. 그 화면은 저장된 리포트 파일을
읽고, 그 파일은 채점을 다시 돌릴 때만 쓰인다 (POST /api/trust/run).
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import (  # noqa: E402
    DATA_DIR,
    DATABASE_URL,
    MEDIA_DIR,
    METADATA_DIR,
    PHOTOS_DIR,
    STATE_DIR,
)
from backend.models.graph_models import (  # noqa: E402
    Confidence,
    Edge,
    EventNode,
    MediaNode,
    MediaType,
    PlaceNode,
    RelationType,
    SourceType,
)
from backend.services.graph_manager import graph_manager as gm  # noqa: E402


def _store_label() -> str:
    return "Postgres" if DATABASE_URL else "graph.json"


def _load_metadata() -> list[dict]:
    with open(METADATA_DIR / "media.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _load_events() -> dict[str, dict]:
    with open(METADATA_DIR / "events.json", "r", encoding="utf-8") as f:
        return {row["event_id"]: row for row in json.load(f)}


def _media_node(item: dict) -> MediaNode:
    """정답표 한 줄을 시드가 만들던 것과 같은 노드로

    필드를 seed_from_metadata.py와 맞춘다. 여기서 갈리면 되돌린 사진이 옆
    사진과 다르게 보인다 (촬영일 없는 사진으로 묶이거나, 신뢰도가 낮게 뜬다).
    """
    filename = item["file_name"]
    loc = item.get("location", {})
    return MediaNode(
        id=item["media_id"],
        media_type=MediaType.PHOTO,
        file_path=f"/media-files/{filename}",
        thumbnail_path=f"/media-files/{filename}",
        original_filename=filename,
        exif_date=item.get("taken_at", ""),
        exif_lat=loc.get("lat"),
        exif_lng=loc.get("lon"),
        exif_camera=item.get("camera", {}).get("model"),
        detected_faces=item.get("people", []),
        scene_description=item.get("description"),
        confidence=Confidence.CONFIRMED,
        source=SourceType.EXIF,
    )


def _wanted_edges(item: dict) -> list[Edge]:
    """정답표가 이 사진에 요구하는 관계

    Trust Harness가 대조하는 세 가지(추억 연결·인물·참여자)에, 시드가 함께
    만들던 장소 연결을 더한다. 장소 노드가 없는 그래프에서는 그것만 건너뛴다 —
    없는 노드로 가는 엣지를 만들면 고아 엣지가 되어 Asset Integrity가 깨진다.
    """
    media_id = item["media_id"]
    event_id = item["event_id"]

    edges = [Edge(source=media_id, target=event_id, relation=RelationType.CAPTURED_DURING)]

    place_id = f"place_{event_id}"
    if gm.get_node(place_id):
        edges.append(Edge(source=media_id, target=place_id, relation=RelationType.TAKEN_AT))

    for person_id in item.get("people", []):
        edges.append(Edge(
            source=media_id,
            target=person_id,
            relation=RelationType.DEPICTS,
            properties={"confidence": 1.0},
        ))
        # 사진에 찍힌 사람은 그 추억의 참여자다 (시드와 같은 규칙)
        edges.append(Edge(
            source=person_id,
            target=event_id,
            relation=RelationType.PARTICIPATED_IN,
            properties={"role": "참여자"},
        ))

    return edges


def _plan_events(items: list[dict], events_data: dict[str, dict]) -> list[dict]:
    """사진이 붙어야 할 추억이 그래프에 남아 있는지

    추억 노드가 사라진 채로 사진만 되살리면 captured_during·participated_in이
    없는 노드를 가리켜 고아 엣지가 된다 — Asset Integrity가 깨지고, 화면에서는
    어디에도 속하지 않은 사진이 된다. 그래서 추억을 먼저 되살린다.

    실제로 배포에서 E01("1998 부산 가족여행") 추억이 삭제된 채로 그 사진 3장만
    다시 올라온 상태를 만났다. 그때 사진만 되돌리면 고아 엣지가 6개 생긴다.
    """
    plans: dict[str, dict] = {}
    for item in items:
        event_id = item["event_id"]
        if event_id in plans or gm.get_node(event_id):
            continue
        row = events_data.get(event_id)
        if row:
            plans[event_id] = {"event_id": event_id, "row": row}
    return list(plans.values())


def _apply_events(event_plans: list[dict]) -> None:
    """추억과 그 장소를 시드가 만들던 것과 같게 되살린다"""
    for plan in event_plans:
        event_id = plan["event_id"]
        row = plan["row"]

        place_id = f"place_{event_id}"
        if not gm.get_node(place_id):
            gm.add_place(PlaceNode(
                id=place_id,
                name=row.get("location_name", ""),
                lat=row.get("lat"),
                lng=row.get("lon"),
            ))
            print(f"  {event_id}: 장소 {place_id} 를 되살렸다")

        gm.add_event(EventNode(
            id=event_id,
            title=row["title"],
            description=row.get("summary", ""),
            date_start=row.get("date"),
            location_id=place_id,
            confidence=Confidence.CONFIRMED,
            source=SourceType.USER_INPUT,
        ))
        gm.add_edge(Edge(source=event_id, target=place_id, relation=RelationType.LOCATED_AT))
        print(f"  {event_id}: 추억을 되살렸다 — {row['title']}")


def _plan(items: list[dict], events_data: dict[str, dict]) -> list[dict]:
    """무엇을 고칠지 먼저 정한다

    상태를 셋으로 나눈다.

      renamed  정답표의 id가 그래프에 없고, 같은 파일명을 가진 다른 노드가 있다
               — 지우고 다시 올린 사진이다. 그 노드를 지우고 원래 id로 다시 만든다
      missing  id도 대체 노드도 없다 — 사진이 아예 지워졌다. 원래 id로 만든다
      edges    노드는 제자리에 있는데 정답 관계 일부가 없다 — 빠진 것만 더한다
    """
    existing_edges = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in gm.get_all_edges()
    }
    by_filename: dict[str, list[dict]] = {}
    for node in gm.get_media_nodes():
        by_filename.setdefault(node.get("original_filename", ""), []).append(node)

    plans = []
    for item in items:
        if item.get("type", "photo") != "photo":
            print(f"  건너뜀: {item['media_id']} 는 사진이 아니다 ({item.get('type')})")
            continue

        # 추억이 그래프에도 정답표에도 없으면 이 사진은 손대지 않는다. 되살려도
        # 없는 노드로 가는 엣지가 되고, 그것이 고아 엣지다.
        event_id = item["event_id"]
        if not gm.get_node(event_id) and event_id not in events_data:
            print(
                f"  건너뜀: {item['media_id']} 의 추억 {event_id} 이 "
                "그래프에도 정답표에도 없다"
            )
            continue

        media_id = item["media_id"]
        node = gm.get_node(media_id)
        wanted = _wanted_edges(item)
        missing_edges = [
            e for e in wanted
            if (e.source, e.target, e.relation) not in existing_edges
        ]

        if node:
            if not missing_edges:
                continue
            plans.append({
                "item": item,
                "status": "edges",
                "replacements": [],
                "edges": missing_edges,
                "recreate": False,
            })
            continue

        replacements = [
            other for other in by_filename.get(item["file_name"], [])
            if other["id"] != media_id
        ]
        plans.append({
            "item": item,
            "status": "renamed" if replacements else "missing",
            "replacements": replacements,
            # 노드를 새로 만들면 그 노드에 걸린 관계가 하나도 없다. 빠진 것만
            # 고르지 않고 정답 관계를 전부 다시 잇는다.
            "edges": wanted,
            "recreate": True,
        })

    return plans


def _describe(plan: dict) -> None:
    item = plan["item"]
    status = plan["status"]
    head = {
        "renamed": "id가 바뀌었다",
        "missing": "노드가 없다",
        "edges": "관계가 빠졌다",
    }[status]
    print(f"  [{item['media_id']}] {head} — {item['file_name']}")

    for other in plan["replacements"]:
        faces = other.get("detected_faces") or []
        print(f"      지울 노드: {other['id']}  (인물 {len(faces)}명)")
    if plan["recreate"]:
        print(f"      다시 만들 노드: {item['media_id']}  (인물 {len(item.get('people', []))}명)")
    print(f"      이을 관계: {len(plan['edges'])}개")


def _remote_store() -> bool:
    """지금 고치는 그래프가 이 컴퓨터 밖에 있는가

    배포 DB에 붙어 로컬에서 돌리는 경우다. 그래프는 원격 Postgres인데 MEDIA_DIR은
    이 컴퓨터의 data/media를 가리킨다 — 여기서 파일을 확인하거나 복사해도 배포
    볼륨과는 상관이 없다. 그래서 그때는 파일을 손대지 않고, 손대지 않았다고 밝힌다.

    노드만 지우고 파일은 남기기 때문에 그쪽 볼륨의 원본은 그대로다. 되살린 노드는
    같은 경로(/media-files/<파일명>)를 가리키므로 그 파일을 그대로 다시 쓴다.
    """
    return bool(DATABASE_URL) and STATE_DIR == DATA_DIR


def _ensure_file(item: dict) -> str:
    """서빙되는 자리에 원본 파일을 확보한다

    배포에서 MEDIA_DIR은 볼륨이고 PHOTOS_DIR은 이미지에 구워진 읽기 전용
    자산이다. 대체 노드가 가리키던 파일이 이미 그 자리에 있으면 그대로 쓴다 —
    같은 사진을 다시 올린 것이라 내용이 같다.
    """
    if _remote_store():
        return "확인하지 않았다 (원격 그래프 · 파일은 그쪽 볼륨에 있다)"

    filename = item["file_name"]
    dest = MEDIA_DIR / filename
    if dest.exists():
        return "이미 있다"

    src = PHOTOS_DIR / filename
    if not src.exists():
        return "원본이 없다 (data/photos에 없음)"

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dest))
    return "data/photos에서 복사했다"


def _apply(plans: list[dict]) -> None:
    for plan in plans:
        item = plan["item"]

        if plan["recreate"]:
            print(f"  {item['media_id']}: 파일 — {_ensure_file(item)}")
            # 대체 노드는 노드만 지운다. erase_files(라우터의 삭제 경로)를 쓰지
            # 않는 이유는 그 파일이 방금 확보한 그 파일이기 때문이다 — 지우면
            # 되살린 노드가 없는 파일을 가리킨다.
            for other in plan["replacements"]:
                gm.delete_node(other["id"])
                print(f"  {item['media_id']}: 노드 {other['id']} 지웠다 (파일은 남긴다)")
            gm.add_media(_media_node(item))
            print(f"  {item['media_id']}: 노드 다시 만들었다")
        elif not (gm.get_node(item["media_id"]) or {}).get("detected_faces") and item.get("people"):
            # 관계만 더하는 경우. depicts의 근거가 노드의 detected_faces라서,
            # 엣지만 넣으면 사진 상세는 여전히 인물을 모른다.
            gm.update_node(item["media_id"], {"detected_faces": item["people"]})
            print(f"  {item['media_id']}: 인물 {len(item['people'])}명을 노드에 채웠다")

        for edge in plan["edges"]:
            gm.add_edge(edge)
        print(f"  {item['media_id']}: 관계 {len(plan['edges'])}개 이었다")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--media",
        nargs="+",
        default=None,
        help="되돌릴 media_id (없으면 어긋난 것 전부)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="계획만 보고 아무것도 쓰지 않는다",
    )
    args = parser.parse_args()

    items = _load_metadata()
    if args.media:
        wanted = set(args.media)
        found = {item["media_id"] for item in items} & wanted
        if wanted - found:
            print(f"정답표에 없는 media_id: {', '.join(sorted(wanted - found))}")
            return 1
        items = [item for item in items if item["media_id"] in wanted]

    print(f"저장소: {_store_label()}    정답표 {len(items)}건을 본다")
    if _remote_store():
        # 파일을 확인할 수 없는 실행이다. 확인한 척하지 않는다.
        print("원격 그래프에 붙어 있다. 파일은 건드리지 않는다 —")
        print(f"  이 컴퓨터의 {MEDIA_DIR} 는 그쪽 볼륨이 아니다.")
        print("  노드만 지우므로 그쪽 원본은 남고, 되살린 노드가 그 파일을 다시 쓴다.")
    print()

    from backend.services import trust_harness

    before = trust_harness.score_relations()
    print(
        f"복구 전  관계 {before['found']}/{before['expected']} 일치 · "
        f"누락 {before['missing_count']}개 · {before['accuracy']}\n"
    )

    events_data = _load_events()
    event_plans = _plan_events(items, events_data)
    plans = _plan(items, events_data)
    if not (plans or event_plans):
        print("어긋난 것이 없다. 고칠 것이 없다.")
        return 0

    if event_plans:
        print(f"되살릴 추억 {len(event_plans)}개")
        for plan in event_plans:
            print(f"  [{plan['event_id']}] {plan['row']['title']}")
        print()

    print(f"고칠 것 {len(plans)}건")
    for plan in plans:
        _describe(plan)

    if args.dry_run:
        print("\n--dry-run 이라 아무것도 쓰지 않았다.")
        return 0

    print("\n적용")
    # 한 트랜잭션으로 묶는다. 중간에 실패하면 반쯤 지워진 그래프가 남는다 —
    # 대체 노드는 지웠는데 새 노드를 못 만든 상태가 제일 나쁘다.
    # 추억을 먼저 되살린다. 사진의 관계가 그 노드를 가리킨다.
    with gm.batch():
        _apply_events(event_plans)
        _apply(plans)

    after = trust_harness.score_relations()
    print(
        f"\n복구 후  관계 {after['found']}/{after['expected']} 일치 · "
        f"누락 {after['missing_count']}개 · {after['accuracy']}"
    )
    if after["missing_count"]:
        print("아직 빠진 관계 (앞 20개):")
        for row in after["missing"]:
            print(f"  {row['source']} -> {row['target']} : {row['relation']}")

    # 없는 노드를 가리키는 엣지가 생겼는지 함께 본다. 되살리는 일이 그것을
    # 만들면 관계 점수는 올라가고 자산 점수가 내려간다.
    asset = trust_harness.score_asset_integrity()
    print(
        f"고아 엣지 {asset['orphan_edge_count']}개 · "
        f"파일 없는 미디어 {asset['missing_file_count']}개 (자산 {asset['score']})"
    )

    print(
        "\n/trust 화면은 저장된 리포트를 읽는다. 숫자를 갱신하려면 채점을 다시 돌린다:"
        "\n  POST /api/trust/run   또는   python scripts/run_trust_harness.py"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
