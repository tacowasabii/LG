"""Memory Graph 저장소 구현들

    stores/base.py       인터페이스 (호출부가 의존하는 표면)
    stores/json_store.py graph.json 한 개 (기본값 · 로컬 개발과 데모)
    stores/pg_store.py   Postgres (실제 데이터)

고르는 곳은 backend/services/graph_manager.py 하나뿐이다.
"""
