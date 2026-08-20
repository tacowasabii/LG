"""Memory Graph 접근점

여기가 저장소를 고르는 유일한 자리다. 서비스·라우터 18곳은 `graph_manager`라는
이름만 알고, 그 뒤가 JSON 파일인지 Postgres인지 모른다.

    DATABASE_URL 없음  ->  JsonGraphStore     (로컬 개발·데모)
    DATABASE_URL 있음  ->  PostgresGraphStore (실제 데이터)

두 구현은 같은 인터페이스를 채운다 (backend/services/stores/base.py).
의미 차이는 그 파일 주석에 적어 두었다 — 같은 두 노드 사이에 관계가 둘 이상일 때
JSON은 마지막 하나만 남기고 Postgres는 모두 남긴다.

이전은 scripts/migrate_to_postgres.py 가 한다.
"""

from __future__ import annotations

from backend.config import DATABASE_URL
from backend.services.stores.base import SEARCH_FIELDS, GraphStore
from backend.services.stores.json_store import JsonGraphStore


def create_store() -> GraphStore:
    """환경에 맞는 저장소를 만든다"""
    if DATABASE_URL:
        # psycopg는 DATABASE_URL이 있을 때만 import한다. 로컬에서 이 패키지가
        # 없어도 앱이 뜨게 하려는 것이다.
        from backend.services.stores.pg_store import PostgresGraphStore

        return PostgresGraphStore(DATABASE_URL)

    return JsonGraphStore()


graph_manager: GraphStore = create_store()

# 예전 이름. 시드 스크립트와 테스트가 클래스를 직접 쓰고 있어 남겨 둔다.
GraphManager = JsonGraphStore

__all__ = ["graph_manager", "create_store", "GraphStore", "GraphManager", "SEARCH_FIELDS"]
