"""Memory Graph 저장소 인터페이스

지금까지 그래프는 `graph.json` 한 개였다. 쓸 때마다 파일 전체를 다시 쓰고, 락이
없어 동시 업로드에서 마지막 저장이 이겼다. 실제 가족 아카이브(수천~수만 장)에서는
그대로 쓸 수 없다.

그래서 저장소를 갈아끼울 수 있게 인터페이스를 분리했다. 호출부(서비스·라우터 18곳)는
`graph_manager`라는 이름 하나만 알고, 그 뒤에 어떤 구현이 있는지 모른다.

    DATABASE_URL 없음  ->  JsonGraphStore     (로컬 개발·데모)
    DATABASE_URL 있음  ->  PostgresGraphStore (실제 데이터)

두 구현의 의미 차이는 하나뿐이고, 여기 적어 둔다.

    같은 (source, target) 쌍에 관계가 둘 이상일 때
      JSON(NetworkX DiGraph): 마지막 관계만 남는다 (덮어쓴다)
      Postgres:               관계마다 한 줄로 모두 남는다

    영상이 어떤 사람을 담고(DEPICTS) 동시에 그 사람이 말한다면(NARRATED_BY),
    JSON에서는 한쪽이 사라진다. Postgres 쪽이 옳고, 그래서 고치지 않고 남겨 둔다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator, Optional

from backend.models.graph_models import (
    Edge,
    EventNode,
    MediaNode,
    MemoryNode,
    PersonNode,
    PlaceNode,
)

# 텍스트 검색 대상 필드.
# - relation이 포함돼야 "엄마", "딸" 같은 호칭으로 인물을 찾을 수 있다
#   (가족이 이름 대신 쓰는 가장 자연스러운 표현이다)
# - scene_description은 사진이 가진 유일한 텍스트다. 빼면 미디어 노드가
#   검색으로 도달 불가능해서 "광안리 사진" 같은 질의가 사진에 닿지 못한다
SEARCH_FIELDS = (
    "name",
    "title",
    "relation",
    "description",
    "content",
    "address",
    "scene_description",
)


class GraphStore(ABC):
    """호출부가 의존하는 표면. 새 구현은 이걸 모두 채워야 한다."""

    # 검색 대상 필드. 예전에는 JSON 저장소 클래스의 속성이었고 테스트가 그걸
    # 직접 읽는다. 구현이 공유하는 값이므로 인터페이스에 둔다.
    SEARCH_FIELDS = SEARCH_FIELDS

    # --- 쓰기 ---

    @abstractmethod
    def add_person(self, person: PersonNode) -> dict: ...

    @abstractmethod
    def add_event(self, event: EventNode) -> dict: ...

    @abstractmethod
    def add_place(self, place: PlaceNode) -> dict: ...

    @abstractmethod
    def add_media(self, media: MediaNode) -> dict: ...

    @abstractmethod
    def add_memory(self, memory: MemoryNode) -> dict: ...

    @abstractmethod
    def update_node(self, node_id: str, updates: dict) -> Optional[dict]: ...

    @abstractmethod
    def delete_node(self, node_id: str) -> bool: ...

    @abstractmethod
    def add_edge(self, edge: Edge) -> dict: ...

    @abstractmethod
    def remove_edge(self, source: str, target: str) -> bool: ...

    @abstractmethod
    def reset(self) -> None:
        """그래프를 비운다 (시드 재생성용)

        시드 스크립트가 파일을 지우는 방식에 의존하고 있었다. 저장소가 파일이
        아닐 수도 있으니 지우는 일도 저장소가 맡는다.
        """

    @contextmanager
    def batch(self) -> Iterator[None]:
        """여러 번 쓸 때 저장을 한 번으로 모은다

        대량 수집에서 결정적이다. JSON 저장소는 쓰기마다 파일 전체를 다시 쓰기
        때문에, 사진 400장을 한 장씩 넣으면 24초가 걸렸다.
        기본 구현은 아무것도 모으지 않는다 (구현이 원할 때만 최적화한다).
        """
        yield

    # --- 읽기 ---

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[dict]: ...

    @abstractmethod
    def get_all_nodes(self) -> list[dict]: ...

    @abstractmethod
    def get_all_edges(self) -> list[dict]: ...

    @abstractmethod
    def get_nodes_by_type(self, node_type: str) -> list[dict]: ...

    @abstractmethod
    def get_connected_nodes(
        self, node_id: str, relation: Optional[str] = None
    ) -> list[dict]: ...

    @abstractmethod
    def search_nodes(self, query: str) -> list[dict]: ...

    @abstractmethod
    def get_event_detail(self, event_id: str) -> Optional[dict]: ...

    @abstractmethod
    def get_person_detail(self, person_id: str) -> Optional[dict]: ...

    # --- 편의 (구현 공통) ---

    def get_full_graph(self) -> dict:
        return {"nodes": self.get_all_nodes(), "edges": self.get_all_edges()}

    def get_persons(self) -> list[dict]:
        from backend.models.graph_models import NodeType

        return self.get_nodes_by_type(NodeType.PERSON)

    def get_events(self) -> list[dict]:
        from backend.models.graph_models import NodeType

        return self.get_nodes_by_type(NodeType.EVENT)

    def get_places(self) -> list[dict]:
        from backend.models.graph_models import NodeType

        return self.get_nodes_by_type(NodeType.PLACE)

    def get_media_nodes(self) -> list[dict]:
        from backend.models.graph_models import NodeType

        return self.get_nodes_by_type(NodeType.MEDIA)

    def get_memories(self) -> list[dict]:
        from backend.models.graph_models import NodeType

        return self.get_nodes_by_type(NodeType.MEMORY)

    def get_events_in_range(
        self, start: Optional[str] = None, end: Optional[str] = None
    ) -> list[dict]:
        """시간 범위 내 이벤트 (날짜가 ISO 문자열이라 문자열 비교로 충분하다)"""
        filtered = []
        for event in self.get_events():
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
        """이벤트에 연결된 미디어 (CAPTURED_DURING)"""
        from backend.models.graph_models import NodeType, RelationType

        return [
            node
            for node in self.get_connected_nodes(event_id, RelationType.CAPTURED_DURING)
            if node.get("node_type") == NodeType.MEDIA
        ]
