"""Postgres 저장소 (실제 데이터)

JSON 파일 저장소가 실제 아카이브에서 부딪히는 세 가지를 없앤다.
  - 쓸 때마다 파일 전체 재작성  ->  행 단위 UPSERT
  - 락이 없어 동시 업로드에서 유실  ->  트랜잭션
  - 검색이 전수 스캔  ->  trigram 색인으로 부분 일치

스키마는 노드 두 종류가 아니라 `nodes`/`edges` 두 표뿐이다. 인물·사건·장소·기록·
기억의 필드가 서로 다르고 앞으로 더 늘어날 것이므로, 공통 컬럼(id·node_type)만
빼고 나머지는 JSONB에 둔다. 새 필드를 넣을 때 마이그레이션이 필요 없다.

    nodes(id, node_type, data jsonb, search_text, created_at, updated_at)
    edges(source, target, relation, properties jsonb, created_at)

search_text는 쓸 때 만들어 둔 검색용 문자열이다. 한국어는 기본 형태소 사전이 없어
to_tsvector가 제대로 동작하지 않으므로, 지금 코드가 하는 것과 같은 부분 일치를
pg_trgm으로 색인한다 (의미가 바뀌지 않는다).

JSON 저장소와 다른 점 하나: 같은 (source, target)에 관계가 둘 이상이면 여기서는
모두 남는다. NetworkX DiGraph는 마지막 하나만 남긴다 (stores/base.py 주석 참고).
"""

from __future__ import annotations

import atexit
import json
import threading
from contextlib import contextmanager
from enum import Enum
from typing import Iterator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.models.graph_models import (
    Edge,
    EventNode,
    MediaNode,
    MemoryNode,
    NodeType,
    PersonNode,
    PlaceNode,
    RelationType,
    edge_to_dict,
    node_to_dict,
)
from backend.services.stores.base import SEARCH_FIELDS, GraphStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id          text PRIMARY KEY,
    node_type   text NOT NULL,
    data        jsonb NOT NULL,
    search_text text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS nodes_type_idx ON nodes (node_type);

CREATE TABLE IF NOT EXISTS edges (
    source     text NOT NULL,
    target     text NOT NULL,
    relation   text NOT NULL,
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, target, relation)
);

CREATE INDEX IF NOT EXISTS edges_source_idx ON edges (source);
CREATE INDEX IF NOT EXISTS edges_target_idx ON edges (target);
CREATE INDEX IF NOT EXISTS edges_relation_idx ON edges (relation);
"""

# 부분 일치 검색용. 확장이 없는 환경(권한 부족 등)에서도 죽지 않게 따로 시도한다.
TRIGRAM = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS nodes_search_trgm_idx
    ON nodes USING gin (search_text gin_trgm_ops);
"""


def _text(value) -> str:
    """열거형에서 값만 꺼낸다

    class NodeType(str, Enum) 의 인스턴스는 문자열이지만 str()은 __str__을 타서
    'NodeType.PERSON'을 준다. 그 값으로 조회하면 아무것도 안 나온다 (실제로
    겪었다: 인물 0명 -> 시드가 없다고 판정). 값만 꺼내 쓴다.
    """
    return value.value if isinstance(value, Enum) else str(value)


def _search_text(data: dict) -> str:
    return " ".join(str(data.get(field) or "") for field in SEARCH_FIELDS).lower()


class PostgresGraphStore(GraphStore):
    """행 단위로 읽고 쓴다. 메모리에 그래프를 들고 있지 않다."""

    def __init__(self, dsn: str):
        self.pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "row_factory": dict_row},
            open=True,
        )
        # batch() 안에서 쓰는 연결. 스레드마다 따로 둔다 (FastAPI가 sync 핸들러를
        # 스레드풀에서 돌리므로 전역으로 두면 서로 트랜잭션을 침범한다).
        self._local = threading.local()
        # 스크립트가 끝날 때 배경 스레드를 정리한다 (안 하면 종료가 5초 지연되고
        # "couldn't stop thread" 경고가 남는다)
        atexit.register(self.close)
        self._init_schema()

    # --- 연결 ---

    @contextmanager
    def _conn(self) -> Iterator[psycopg.Connection]:
        existing = getattr(self._local, "conn", None)
        if existing is not None:
            # batch 중이면 그 트랜잭션 안에서 계속한다
            yield existing
            return
        with self.pool.connection() as conn:
            yield conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(SCHEMA)
            try:
                conn.execute(TRIGRAM)
            except psycopg.Error as e:
                # 확장을 못 만들면 검색은 색인 없이 동작한다 (느리지만 정확하다)
                print(f"[pg] pg_trgm 색인을 만들지 못했습니다. 검색이 느려집니다: {e}")

    @contextmanager
    def batch(self) -> Iterator[None]:
        """여러 번 쓰기를 한 트랜잭션으로 묶는다 (대량 수집)"""
        if getattr(self._local, "conn", None) is not None:
            yield  # 이미 batch 안이다
            return

        with self.pool.connection() as conn:
            conn.autocommit = False
            self._local.conn = conn
            try:
                yield
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                self._local.conn = None
                conn.autocommit = True

    def reset(self) -> None:
        with self._conn() as conn:
            conn.execute("TRUNCATE nodes, edges")

    # --- 노드 ---

    def _upsert(self, data: dict) -> dict:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO nodes (id, node_type, data, search_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                   SET node_type = EXCLUDED.node_type,
                       data = EXCLUDED.data,
                       search_text = EXCLUDED.search_text,
                       updated_at = now()
                """,
                (
                    data["id"],
                    _text(data.get("node_type", "")),
                    json.dumps(data),
                    _search_text(data),
                ),
            )
        return data

    def add_person(self, person: PersonNode) -> dict:
        return self._upsert(node_to_dict(person))

    def add_event(self, event: EventNode) -> dict:
        return self._upsert(node_to_dict(event))

    def add_place(self, place: PlaceNode) -> dict:
        return self._upsert(node_to_dict(place))

    def add_media(self, media: MediaNode) -> dict:
        return self._upsert(node_to_dict(media))

    def add_memory(self, memory: MemoryNode) -> dict:
        return self._upsert(node_to_dict(memory))

    def update_node(self, node_id: str, updates: dict) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM nodes WHERE id = %s FOR UPDATE", (node_id,)
            ).fetchone()
            if not row:
                return None

            data = dict(row["data"])
            data.update(updates)
            conn.execute(
                """
                UPDATE nodes
                   SET data = %s, search_text = %s, updated_at = now()
                 WHERE id = %s
                """,
                (json.dumps(data), _search_text(data), node_id),
            )
        return data

    def delete_node(self, node_id: str) -> bool:
        with self._conn() as conn:
            # 엣지를 먼저 지운다 (NetworkX가 노드를 지울 때 하던 것과 같다)
            conn.execute(
                "DELETE FROM edges WHERE source = %s OR target = %s", (node_id, node_id)
            )
            result = conn.execute("DELETE FROM nodes WHERE id = %s", (node_id,))
            return result.rowcount > 0

    def get_node(self, node_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM nodes WHERE id = %s", (node_id,)
            ).fetchone()
        return dict(row["data"]) if row else None

    # --- 엣지 ---

    def _upsert_edge(
        self, source: str, target: str, relation: str, properties: dict
    ) -> None:
        """엣지 한 줄. 이전 스크립트도 이걸 쓴다."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO edges (source, target, relation, properties)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source, target, relation) DO UPDATE
                   SET properties = EXCLUDED.properties
                """,
                (source, target, _text(relation), json.dumps(properties or {})),
            )

    def add_edge(self, edge: Edge) -> dict:
        self._upsert_edge(edge.source, edge.target, edge.relation, edge.properties or {})
        return edge_to_dict(edge)

    def remove_edge(self, source: str, target: str) -> bool:
        """두 노드 사이의 관계를 모두 지운다 (NetworkX의 remove_edge와 같은 의미)"""
        with self._conn() as conn:
            result = conn.execute(
                "DELETE FROM edges WHERE source = %s AND target = %s", (source, target)
            )
            return result.rowcount > 0

    # --- 조회 ---

    def _rows_to_nodes(self, rows) -> list[dict]:
        return [dict(row["data"]) for row in rows]

    def get_all_nodes(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT data FROM nodes ORDER BY created_at, id").fetchall()
        return self._rows_to_nodes(rows)

    def get_all_edges(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT source, target, relation, properties FROM edges ORDER BY created_at"
            ).fetchall()
        return [
            {
                "source": row["source"],
                "target": row["target"],
                "relation": row["relation"],
                "properties": dict(row["properties"] or {}),
            }
            for row in rows
        ]

    def get_nodes_by_type(self, node_type: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM nodes WHERE node_type = %s ORDER BY created_at, id",
                (_text(node_type),),
            ).fetchall()
        return self._rows_to_nodes(rows)

    def get_connected_nodes(
        self, node_id: str, relation: Optional[str] = None
    ) -> list[dict]:
        """특정 노드와 연결된 모든 노드 (방향 무시)"""
        sql = """
            SELECT n.data
              FROM nodes n
             WHERE n.id IN (
                   -- 캐스팅이 없으면 relation을 생략했을 때(NULL) 타입을 못 정한다
                   SELECT target FROM edges
                    WHERE source = %(id)s
                      AND (%(rel)s::text IS NULL OR relation = %(rel)s::text)
                   UNION
                   SELECT source FROM edges
                    WHERE target = %(id)s
                      AND (%(rel)s::text IS NULL OR relation = %(rel)s::text)
             )
        """
        params = {"id": node_id, "rel": _text(relation) if relation else None}
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return self._rows_to_nodes(rows)

    def search_nodes(self, query: str) -> list[dict]:
        """부분 일치 검색 (JSON 저장소의 동작과 같다)"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM nodes WHERE search_text LIKE %s",
                (f"%{query.lower()}%",),
            ).fetchall()
        return self._rows_to_nodes(rows)

    def get_event_detail(self, event_id: str) -> Optional[dict]:
        event = self.get_node(event_id)
        if not event or event.get("node_type") != NodeType.EVENT:
            return None

        with self._conn() as conn:
            incoming = conn.execute(
                """
                SELECT n.data, e.relation
                  FROM edges e JOIN nodes n ON n.id = e.source
                 WHERE e.target = %s
                """,
                (event_id,),
            ).fetchall()
            outgoing = conn.execute(
                """
                SELECT n.data
                  FROM edges e JOIN nodes n ON n.id = e.target
                 WHERE e.source = %s AND n.node_type = %s
                 LIMIT 1
                """,
                (event_id, _text(NodeType.PLACE)),
            ).fetchone()

        participants, media, memories = [], [], []
        seen_memory: set[str] = set()

        for row in incoming:
            node = dict(row["data"])
            node_type = node.get("node_type")
            if node_type == NodeType.PERSON:
                participants.append(node)
            elif node_type == NodeType.MEDIA:
                media.append(node)
            elif node_type == NodeType.MEMORY and node["id"] not in seen_memory:
                memories.append(node)
                seen_memory.add(node["id"])

        event["participants"] = participants
        event["media"] = media
        event["memories"] = memories
        event["location"] = dict(outgoing["data"]) if outgoing else None
        return event

    def get_person_detail(self, person_id: str) -> Optional[dict]:
        person = self.get_node(person_id)
        if not person or person.get("node_type") != NodeType.PERSON:
            return None

        with self._conn() as conn:
            outgoing = conn.execute(
                """
                SELECT n.data
                  FROM edges e JOIN nodes n ON n.id = e.target
                 WHERE e.source = %s AND n.node_type = ANY(%s)
                """,
                (person_id, [_text(NodeType.EVENT), _text(NodeType.MEMORY)]),
            ).fetchall()
            incoming = conn.execute(
                """
                SELECT n.data
                  FROM edges e JOIN nodes n ON n.id = e.source
                 WHERE e.target = %s AND n.node_type = %s
                """,
                (person_id, _text(NodeType.MEDIA)),
            ).fetchall()

        events, memories = [], []
        for row in outgoing:
            node = dict(row["data"])
            if node.get("node_type") == NodeType.EVENT:
                events.append(node)
            else:
                memories.append(node)

        person["events"] = events
        person["media"] = self._rows_to_nodes(incoming)
        person["memories"] = memories
        return person

    # --- JSON 저장소와의 호환 ---

    def save(self) -> None:
        """JSON 저장소에는 있는 메서드. Postgres는 쓸 때 이미 저장된다."""
        return None

    def close(self) -> None:
        """연결 풀을 닫는다 (프로세스 종료·앱 shutdown)"""
        try:
            self.pool.close()
        except Exception:
            pass
