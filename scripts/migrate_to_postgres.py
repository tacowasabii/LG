"""graph.json -> Postgres 이전

    DATABASE_URL="postgresql://..." python scripts/migrate_to_postgres.py [--from data/graph.json]

하는 일
  1. JSON 파일에서 노드·엣지를 읽는다
  2. Postgres에 스키마를 만들고 한 트랜잭션으로 넣는다
  3. 개수와 표본을 대조해 결과를 보고한다

여러 번 돌려도 된다 (id 기준 UPSERT). --reset을 주면 넣기 전에 비운다.

이전이 끝나도 JSON 파일은 그대로 남는다. DATABASE_URL을 지우면 다시 JSON으로
돌아간다 — 되돌릴 길을 없애지 않는다.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from",
        dest="source",
        default=None,
        help="읽을 JSON 파일 (기본: STATE_DIR/graph.json)",
    )
    parser.add_argument("--reset", action="store_true", help="넣기 전에 대상을 비운다")
    args = parser.parse_args()

    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        print("DATABASE_URL이 없습니다. 이전할 대상을 지정하세요.")
        return 1

    from backend.config import GRAPH_FILE
    from backend.services.stores.pg_store import PostgresGraphStore

    source = Path(args.source) if args.source else GRAPH_FILE
    if not source.exists():
        print(f"읽을 파일이 없습니다: {source}")
        return 1

    with open(source, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    print(f"읽음: {source}")
    print(f"  노드 {len(nodes)} · 엣지 {len(edges)}")

    store = PostgresGraphStore(dsn)

    if args.reset:
        store.reset()
        print("  대상을 비웠습니다")

    # 한 트랜잭션으로 넣는다. 중간에 실패하면 아무것도 남지 않는다.
    with store.batch():
        for node in nodes:
            store._upsert(node)
        for edge in edges:
            store._upsert_edge(
                edge["source"],
                edge["target"],
                edge.get("relation", ""),
                edge.get("properties") or {},
            )

    moved_nodes = store.get_all_nodes()
    moved_edges = store.get_all_edges()
    print(f"넣음: 노드 {len(moved_nodes)} · 엣지 {len(moved_edges)}")

    # 대조 — 개수와 id 집합이 같은지 본다
    source_ids = {n["id"] for n in nodes}
    moved_ids = {n["id"] for n in moved_nodes}
    missing = source_ids - moved_ids
    if missing:
        print(f"  누락된 노드 {len(missing)}개: {sorted(missing)[:5]}")
        return 1

    # 엣지는 같은 (source,target)에 관계가 여럿이면 Postgres에서 더 많아질 수 있다.
    # JSON(NetworkX)은 마지막 하나만 남기기 때문이다.
    if len(moved_edges) != len(edges):
        print(
            f"  엣지 수가 다릅니다 (JSON {len(edges)} -> PG {len(moved_edges)}). "
            "같은 두 노드 사이의 여러 관계가 JSON에서 덮여 있었다면 정상입니다."
        )

    print("\n표본 확인")
    for node in moved_nodes[:3]:
        label = node.get("name") or node.get("title") or node.get("content", "")[:20]
        print(f"  {node['id']:<12} {node.get('node_type', ''):<8} {label}")

    print("\n이전 완료. 백엔드에 DATABASE_URL을 주면 Postgres를 씁니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
