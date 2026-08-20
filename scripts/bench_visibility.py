"""공개 범위 판정 성능 측정 (실제 데이터 규모를 가정)

    STATE_DIR=<임시경로> python scripts/bench_visibility.py [--media 2000] [--people 50]

지금 그래프는 미디어 28개라 어떤 구현이든 빠르다. 실제 가족 아카이브(수천~수만 장)
에서 무엇이 터지는지 보려면 규모를 키워서 재야 한다.

비교 대상
  old  노드마다 전체 엣지를 순회한다 (2026-08-20 이전 구현)
  new  목록당 한 번만 색인한다 (backend/services/visibility.py)

주의: STATE_DIR을 지정하지 않으면 data/graph.json을 덮어쓴다. 반드시 임시 경로에서 돌린다.
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import GRAPH_FILE, STATE_DIR  # noqa: E402
from backend.models.graph_models import (  # noqa: E402
    Edge,
    MediaNode,
    MediaType,
    PersonNode,
    RelationType,
)
from backend.services import visibility  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402


def old_blocked(node: dict, viewer_id) -> bool:
    """예전 구현 — 노드마다 전체 엣지를 순회한다"""
    appearing = set(node.get("detected_faces") or [])
    if node.get("speaker_id"):
        appearing.add(node["speaker_id"])

    for edge in graph_manager.get_all_edges():
        if edge["source"] != node["id"]:
            continue
        if edge["relation"] in (RelationType.DEPICTS, RelationType.NARRATED_BY):
            appearing.add(edge["target"])

    for person_id in appearing:
        if person_id == viewer_id:
            continue
        person = graph_manager.get_node(person_id)
        if person and person.get("private_request"):
            return True
    return False


def old_can_view(node, viewer_id) -> bool:
    """예전 경로 — 소유자·공개 범위 판정은 같고 인물 동의만 옛 방식으로"""
    owner_id = node.get("owner_id")
    if viewer_id and owner_id and viewer_id == owner_id:
        return True
    visibility_value = node.get("visibility") or "family"
    if visibility_value == "private":
        return False
    if visibility_value == "partial" and viewer_id not in (node.get("allowed_ids") or []):
        return False
    return not old_blocked(node, viewer_id)


def old_filter(nodes, viewer_id):
    return [n for n in nodes if old_can_view(n, viewer_id)]


def build(media_count: int, people_count: int, faces_per_media: int = 3):
    """합성 그래프를 만든다 (실제 아카이브의 연결 밀도를 흉내)"""
    people = []
    for i in range(people_count):
        person = PersonNode(name=f"사람{i}", relation="가족")
        graph_manager.add_person(person)
        people.append(person.id)

    media_nodes = []
    for i in range(media_count):
        node = MediaNode(
            media_type=MediaType.PHOTO,
            file_path=f"/media-files/bench-{i}.jpg",
            original_filename=f"bench-{i}.jpg",
            owner_id=people[i % people_count],
        )
        graph_manager.add_media(node)
        media_nodes.append(node)

        for j in range(faces_per_media):
            graph_manager.add_edge(
                Edge(
                    source=node.id,
                    target=people[(i + j) % people_count],
                    relation=RelationType.DEPICTS,
                )
            )

    return people, media_nodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", type=int, default=2000)
    parser.add_argument("--people", type=int, default=50)
    args = parser.parse_args()

    if STATE_DIR == ROOT_DIR / "data":
        print("STATE_DIR을 임시 경로로 지정하고 돌리세요. data/graph.json을 덮어씁니다.")
        return 1

    print(f"합성 그래프 생성: 미디어 {args.media} · 인물 {args.people}")
    started = time.perf_counter()
    people, media_nodes = build(args.media, args.people)
    print(f"  생성 {time.perf_counter() - started:.1f}초")
    print(f"  노드 {len(graph_manager.get_all_nodes())} · 엣지 {len(graph_manager.get_all_edges())}")

    viewer = people[0]
    nodes = [graph_manager.get_node(n.id) for n in media_nodes]

    # 1) 비공개 요청이 없는 상태 (평상시)
    for label, fn in (("old", old_filter), ("new", visibility.filter_media)):
        started = time.perf_counter()
        result = fn(nodes, viewer)
        print(f"[요청 없음] {label}: {time.perf_counter() - started:6.3f}초 · 통과 {len(result)}")

    # 2) 한 사람이 비공개를 요청한 상태 (색인이 실제로 쓰이는 경로)
    graph_manager.update_node(people[1], {"private_request": True})
    for label, fn in (("old", old_filter), ("new", visibility.filter_media)):
        started = time.perf_counter()
        result = fn(nodes, viewer)
        print(f"[요청 있음] {label}: {time.perf_counter() - started:6.3f}초 · 통과 {len(result)}")

    print(f"\n측정에 쓴 그래프: {GRAPH_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
