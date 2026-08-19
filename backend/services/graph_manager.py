"""Memory Graph 관리 - NetworkX 기반 + JSON 영속화"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import networkx as nx

from backend.config import GRAPH_FILE
from backend.models.graph_models import (
    PersonNode, EventNode, PlaceNode, MediaNode, MemoryNode,
    Edge, NodeType, RelationType, node_to_dict, edge_to_dict,
)


class GraphManager:
    """싱글톤 패턴으로 Graph를 메모리에 유지하고 JSON으로 영속화"""

    _instance: Optional[GraphManager] = None

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
        self._load()

    # --- Persistence ---

    def _load(self):
        """JSON 파일에서 Graph 로드"""
        if GRAPH_FILE.exists():
            with open(GRAPH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for node in data.get("nodes", []):
                node_id = node["id"]
                self.graph.add_node(node_id, **node)
            for edge in data.get("edges", []):
                self.graph.add_edge(
                    edge["source"], edge["target"],
                    relation=edge.get("relation", ""),
                    properties=edge.get("properties", {}),
                )

    def save(self):
        """Graph를 JSON 파일로 저장"""
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

    # --- Node CRUD ---

    def add_person(self, person: PersonNode) -> dict:
        data = node_to_dict(person)
        self.graph.add_node(person.id, **data)
        self.save()
        return data

    def add_event(self, event: EventNode) -> dict:
        data = node_to_dict(event)
        self.graph.add_node(event.id, **data)
        self.save()
        return data

    def add_place(self, place: PlaceNode) -> dict:
        data = node_to_dict(place)
        self.graph.add_node(place.id, **data)
        self.save()
        return data

    def add_media(self, media: MediaNode) -> dict:
        data = node_to_dict(media)
        self.graph.add_node(media.id, **data)
        self.save()
        return data

    def add_memory(self, memory: MemoryNode) -> dict:
        data = node_to_dict(memory)
        self.graph.add_node(memory.id, **data)
        self.save()
        return data

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

    # --- Edge CRUD ---

    def add_edge(self, edge: Edge) -> dict:
        self.graph.add_edge(
            edge.source, edge.target,
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

    # --- Query Helpers ---

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

    def get_full_graph(self) -> dict:
        return {
            "nodes": self.get_all_nodes(),
            "edges": self.get_all_edges(),
        }

    def get_nodes_by_type(self, node_type: str) -> list[dict]:
        return [
            dict(self.graph.nodes[n])
            for n in self.graph.nodes
            if self.graph.nodes[n].get("node_type") == node_type
        ]

    def get_persons(self) -> list[dict]:
        return self.get_nodes_by_type(NodeType.PERSON)

    def get_events(self) -> list[dict]:
        return self.get_nodes_by_type(NodeType.EVENT)

    def get_places(self) -> list[dict]:
        return self.get_nodes_by_type(NodeType.PLACE)

    def get_media_nodes(self) -> list[dict]:
        return self.get_nodes_by_type(NodeType.MEDIA)

    def get_memories(self) -> list[dict]:
        return self.get_nodes_by_type(NodeType.MEMORY)

    def get_connected_nodes(self, node_id: str, relation: Optional[str] = None) -> list[dict]:
        """특정 노드와 연결된 모든 노드 (방향 무시)"""
        if node_id not in self.graph.nodes:
            return []
        connected = set()
        # outgoing
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if relation is None or data.get("relation") == relation:
                connected.add(target)
        # incoming
        for source, _, data in self.graph.in_edges(node_id, data=True):
            if relation is None or data.get("relation") == relation:
                connected.add(source)
        return [dict(self.graph.nodes[n]) for n in connected if n in self.graph.nodes]

    def get_event_detail(self, event_id: str) -> Optional[dict]:
        """Event + 연결된 Person/Media/Memory 상세"""
        event = self.get_node(event_id)
        if not event or event.get("node_type") != NodeType.EVENT:
            return None

        participants = []
        media = []
        memories = []
        location = None

        # incoming edges (Person -> Event, Media -> Event, Memory -> Event)
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

        # outgoing edges (Event -> Place)
        for _, target, data in self.graph.out_edges(event_id, data=True):
            target_node = self.graph.nodes.get(target)
            if not target_node:
                continue
            if target_node.get("node_type") == NodeType.PLACE:
                location = dict(target_node)

        # Also check: memories ABOUT this event
        for source, target, data in self.graph.edges(data=True):
            if target == event_id and data.get("relation") == RelationType.ABOUT:
                source_node = self.graph.nodes.get(source)
                if source_node and source_node.get("node_type") == NodeType.MEMORY:
                    if source_node not in memories:
                        memories.append(dict(source_node))

        event["participants"] = participants
        event["media"] = media
        event["memories"] = memories
        event["location"] = location
        return event

    def get_person_detail(self, person_id: str) -> Optional[dict]:
        """Person + 참여 Event/Media 상세"""
        person = self.get_node(person_id)
        if not person or person.get("node_type") != NodeType.PERSON:
            return None

        events = []
        media = []

        # outgoing: Person -> Event (PARTICIPATED_IN)
        for _, target, data in self.graph.out_edges(person_id, data=True):
            target_node = self.graph.nodes.get(target)
            if not target_node:
                continue
            if target_node.get("node_type") == NodeType.EVENT:
                events.append(dict(target_node))

        # incoming: Media -> Person (DEPICTS)
        for source, _, data in self.graph.in_edges(person_id, data=True):
            source_node = self.graph.nodes.get(source)
            if not source_node:
                continue
            if source_node.get("node_type") == NodeType.MEDIA:
                media.append(dict(source_node))

        person["events"] = events
        person["media"] = media
        return person

    # 텍스트 검색 대상 필드.
    # relation이 포함돼야 "엄마", "딸" 같은 호칭으로 인물을 찾을 수 있다.
    # (가족이 이름 대신 쓰는 가장 자연스러운 표현이다)
    SEARCH_FIELDS = ("name", "title", "relation", "description", "content", "address")

    def search_nodes(self, query: str) -> list[dict]:
        """간단한 텍스트 검색 (이름, 제목, 호칭, 설명, 내용, 주소에서)"""
        query_lower = query.lower()
        results = []
        for n in self.graph.nodes:
            node = self.graph.nodes[n]
            searchable = " ".join(
                str(node.get(field) or "") for field in self.SEARCH_FIELDS
            ).lower()
            if query_lower in searchable:
                results.append(dict(node))
        return results

    def get_events_in_range(self, start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
        """시간 범위 내 이벤트 검색"""
        events = self.get_events()
        filtered = []
        for event in events:
            event_date = event.get("date_start", "")
            if not event_date:
                continue
            if start and event_date < start:
                continue
            if end and event_date > end:
                continue
            filtered.append(event)
        return sorted(filtered, key=lambda e: e.get("date_start", ""))

    def get_media_for_event(self, event_id: str) -> list[dict]:
        """이벤트에 연결된 미디어 목록"""
        media = []
        for source, target, data in self.graph.in_edges(event_id, data=True):
            if data.get("relation") == RelationType.CAPTURED_DURING:
                source_node = self.graph.nodes.get(source)
                if source_node and source_node.get("node_type") == NodeType.MEDIA:
                    media.append(dict(source_node))
        return media


# Global instance
graph_manager = GraphManager()
