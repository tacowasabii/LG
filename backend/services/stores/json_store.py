"""JSON 파일 저장소 (기본값 · 로컬 개발과 데모)

NetworkX 그래프를 메모리에 들고 `graph.json` 한 개로 영속화한다. 추억 8개·사진
28장 규모에서는 이만큼 단순한 게 좋다. 다만 쓸 때마다 파일 전체를 다시 쓰고 락이
없어서, 실제 아카이브 규모나 동시 업로드에서는 Postgres 저장소를 쓴다.

batch()가 저장을 모아 준다. 사진 400장을 한 장씩 넣으면 24초, batch로 감싸면
한 번만 쓴다.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator, Optional

import networkx as nx

from backend.config import GRAPH_FILE
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


class JsonGraphStore(GraphStore):
    """싱글톤. 그래프를 메모리에 유지하고 JSON으로 영속화한다."""

    _instance: Optional["JsonGraphStore"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.graph = nx.DiGraph()
        # batch() 안에서는 저장을 미룬다
        self._defer_saves = False
        self._dirty = False
        self._load()

    # --- 영속화 ---

    def _load(self):
        if GRAPH_FILE.exists():
            with open(GRAPH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for node in data.get("nodes", []):
                node_id = node["id"]
                self.graph.add_node(node_id, **node)
            for edge in data.get("edges", []):
                self.graph.add_edge(
                    edge["source"],
                    edge["target"],
                    relation=edge.get("relation", ""),
                    properties=edge.get("properties", {}),
                )

    def save(self):
        if self._defer_saves:
            self._dirty = True
            return

        GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [self.graph.nodes[n] for n in self.graph.nodes],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "relation": d.get("relation", ""),
                    "properties": d.get("properties", {}),
                }
                for u, v, d in self.graph.edges(data=True)
            ],
        }
        with open(GRAPH_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @contextmanager
    def batch(self) -> Iterator[None]:
        """저장을 한 번으로 모은다. 예외가 나도 그때까지 쓴 것은 저장한다."""
        outer = self._defer_saves
        self._defer_saves = True
        try:
            yield
        finally:
            self._defer_saves = outer
            if not outer and self._dirty:
                self._dirty = False
                self.save()

    def reset(self) -> None:
        self.graph = nx.DiGraph()
        self._dirty = False
        if GRAPH_FILE.exists():
            GRAPH_FILE.unlink()

    # --- 노드 ---

    def _add(self, node) -> dict:
        data = node_to_dict(node)
        self.graph.add_node(node.id, **data)
        self.save()
        return data

    def add_person(self, person: PersonNode) -> dict:
        return self._add(person)

    def add_event(self, event: EventNode) -> dict:
        return self._add(event)

    def add_place(self, place: PlaceNode) -> dict:
        return self._add(place)

    def add_media(self, media: MediaNode) -> dict:
        return self._add(media)

    def add_memory(self, memory: MemoryNode) -> dict:
        return self._add(memory)

    def update_node(self, node_id: str, updates: dict) -> Optional[dict]:
        if node_id not in self.graph.nodes:
            return None
        self.graph.nodes[node_id].update(updates)
        self.save()
        return dict(self.graph.nodes[node_id])

    def delete_node(self, node_id: str) -> bool:
        if node_id not in self.graph.nodes:
            return False
        self.graph.remove_node(node_id)
        self.save()
        return True

    def get_node(self, node_id: str) -> Optional[dict]:
        if node_id not in self.graph.nodes:
            return None
        return dict(self.graph.nodes[node_id])

    # --- 엣지 ---

    def add_edge(self, edge: Edge) -> dict:
        self.graph.add_edge(
            edge.source,
            edge.target,
            relation=edge.relation,
            properties=edge.properties,
        )
        self.save()
        return edge_to_dict(edge)

    def remove_edge(self, source: str, target: str) -> bool:
        if self.graph.has_edge(source, target):
            self.graph.remove_edge(source, target)
            self.save()
            return True
        return False

    # --- 조회 ---

    def get_all_nodes(self) -> list[dict]:
        return [dict(self.graph.nodes[n]) for n in self.graph.nodes]

    def get_all_edges(self) -> list[dict]:
        return [
            {
                "source": u,
                "target": v,
                "relation": d.get("relation", ""),
                "properties": d.get("properties", {}),
            }
            for u, v, d in self.graph.edges(data=True)
        ]

    def get_nodes_by_type(self, node_type: str) -> list[dict]:
        return [
            dict(self.graph.nodes[n])
            for n in self.graph.nodes
            if self.graph.nodes[n].get("node_type") == node_type
        ]

    def get_connected_nodes(
        self, node_id: str, relation: Optional[str] = None
    ) -> list[dict]:
        """특정 노드와 연결된 모든 노드 (방향 무시)"""
        if node_id not in self.graph.nodes:
            return []

        connected = set()
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if relation is None or data.get("relation") == relation:
                connected.add(target)
        for source, _, data in self.graph.in_edges(node_id, data=True):
            if relation is None or data.get("relation") == relation:
                connected.add(source)

        return [dict(self.graph.nodes[n]) for n in connected if n in self.graph.nodes]

    def search_nodes(self, query: str) -> list[dict]:
        """간단한 텍스트 검색 (이름·제목·호칭·설명·내용·주소·장면설명)"""
        query_lower = query.lower()
        results = []
        for n in self.graph.nodes:
            node = self.graph.nodes[n]
            searchable = " ".join(
                str(node.get(field) or "") for field in SEARCH_FIELDS
            ).lower()
            if query_lower in searchable:
                results.append(dict(node))
        return results

    def get_event_detail(self, event_id: str) -> Optional[dict]:
        """Event + 연결된 Person/Media/Memory 상세"""
        event = self.get_node(event_id)
        if not event or event.get("node_type") != NodeType.EVENT:
            return None

        participants = []
        media = []
        memories = []
        location = None

        for source, _, data in self.graph.in_edges(event_id, data=True):
            source_node = self.graph.nodes.get(source)
            if not source_node:
                continue
            if source_node.get("node_type") == NodeType.PERSON:
                participants.append(dict(source_node))
            elif source_node.get("node_type") == NodeType.MEDIA:
                media.append(dict(source_node))
            elif source_node.get("node_type") == NodeType.MEMORY:
                memories.append(dict(source_node))

        for _, target, data in self.graph.out_edges(event_id, data=True):
            target_node = self.graph.nodes.get(target)
            if not target_node:
                continue
            if target_node.get("node_type") == NodeType.PLACE:
                location = dict(target_node)

        # 기억이 ABOUT으로만 이어진 경우도 담는다
        seen = {m["id"] for m in memories}
        for source, target, data in self.graph.edges(data=True):
            if target != event_id or data.get("relation") != RelationType.ABOUT:
                continue
            source_node = self.graph.nodes.get(source)
            if (
                source_node
                and source_node.get("node_type") == NodeType.MEMORY
                and source_node["id"] not in seen
            ):
                memories.append(dict(source_node))
                seen.add(source_node["id"])

        event["participants"] = participants
        event["media"] = media
        event["memories"] = memories
        event["location"] = location
        return event

    def get_person_detail(self, person_id: str) -> Optional[dict]:
        """Person + 참여 Event/Media/Memory 상세"""
        person = self.get_node(person_id)
        if not person or person.get("node_type") != NodeType.PERSON:
            return None

        events = []
        media = []
        memories = []

        for _, target, data in self.graph.out_edges(person_id, data=True):
            target_node = self.graph.nodes.get(target)
            if not target_node:
                continue
            if target_node.get("node_type") == NodeType.EVENT:
                events.append(dict(target_node))
            elif target_node.get("node_type") == NodeType.MEMORY:
                memories.append(dict(target_node))

        for source, _, data in self.graph.in_edges(person_id, data=True):
            source_node = self.graph.nodes.get(source)
            if not source_node:
                continue
            if source_node.get("node_type") == NodeType.MEDIA:
                media.append(dict(source_node))

        person["events"] = events
        person["media"] = media
        person["memories"] = memories
        return person
