"""Postgres 저장소 회귀 테스트

    TEST_DATABASE_URL="postgresql://..." python tests/test_store_pg.py

TEST_DATABASE_URL이 없으면 건너뛴다. 운영에 쓰는 DATABASE_URL은 쳐다보지 않는다 —
테스트가 실수로 진짜 가족 데이터에 붙는 일을 만들지 않는다.

reset()·TRUNCATE도 쓰지 않는다. 테스트가 만든 노드(test_로 시작하는 id)만 넣고
끝에서 지운다. 그래서 데이터가 들어 있는 DB에 붙여도 안전하다.

여기서 지키는 것은 JSON 저장소와 다르게 동작했던 자리들이다.
  - 검색 질의의 %와 _가 와일드카드로 새지 않는가 (JSON은 글자 그대로 찾는다)
  - update_node가 동시 쓰기에서 남의 필드를 덮지 않는가
  - batch가 실패하면 아무것도 남지 않는가
  - 같은 두 노드 사이의 여러 관계가 모두 남는가 (JSON은 하나만 남는다 — 의도된 차이)
  - 목록 순서가 호출마다 흔들리지 않는가
"""

import os
import sys
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

DSN = os.getenv("TEST_DATABASE_URL", "").strip()

from backend.models.graph_models import (  # noqa: E402
    Edge,
    EventNode,
    MediaNode,
    PersonNode,
    RelationType,
)

PREFIX = "test_pgstore_"
PERSON = PREFIX + "person"
EVENT = PREFIX + "event"
MEDIA = PREFIX + "media"

store = None


def _fixture():
    """테스트용 노드 세 개와 관계를 넣는다"""
    store.add_person(PersonNode(id=PERSON, name="테스트인물", relation="이모"))
    store.add_event(EventNode(id=EVENT, title="테스트추억", description="100% 확실한 날"))
    store.add_media(MediaNode(id=MEDIA, original_filename="t.jpg", scene_description="바다_사진"))
    store.add_edge(Edge(source=MEDIA, target=EVENT, relation=RelationType.CAPTURED_DURING))
    store.add_edge(Edge(source=PERSON, target=EVENT, relation=RelationType.PARTICIPATED_IN))


def _cleanup():
    for node in store.get_all_nodes():
        if node["id"].startswith(PREFIX):
            store.delete_node(node["id"])


# --- 검색 -------------------------------------------------------------------


def test_search_finds_substring():
    """평범한 부분 일치는 그대로 동작한다"""
    assert [n["id"] for n in store.search_nodes("테스트인물")] == [PERSON]
    assert MEDIA in [n["id"] for n in store.search_nodes("바다_사진")]
    print("  부분 일치 OK")


def test_search_treats_wildcards_literally():
    """%와 _는 와일드카드가 아니라 글자다

    LIKE에 질의를 그대로 넣던 때는 "%" 한 글자가 전체 노드를 돌려줬다. 채팅이
    그것을 근거로 삼으면 답변이 오염된다 (JSON 저장소는 0건이다).
    """
    all_count = len(store.get_all_nodes())
    assert all_count > 0

    percent = store.search_nodes("%")
    assert len(percent) < all_count, f"%가 와일드카드로 동작한다 ({len(percent)}건)"
    # "100% 확실한" 을 가진 추억은 글자 그대로 찾혀야 한다
    assert [n["id"] for n in store.search_nodes("100% 확실")] == [EVENT]

    # 밑줄도 마찬가지 — "바다_사진"은 찾히고, "바다X사진"은 찾히지 않는다
    assert MEDIA in [n["id"] for n in store.search_nodes("바다_사진")]
    assert not [n for n in store.search_nodes("바다X사진")]
    print("  와일드카드 이스케이프 OK")


# --- 동시 쓰기 ---------------------------------------------------------------


def test_update_node_does_not_lose_concurrent_fields():
    """두 스레드가 같은 노드의 다른 필드를 고쳐도 둘 다 남는다

    autocommit 연결에서 SELECT ... FOR UPDATE만 쓰면 락이 그 문장 끝에서 풀려
    나중 UPDATE가 앞의 수정을 덮었다 (60개 중 54개만 남았다).
    """
    fields = 30
    store.update_node(EVENT, {f"probe_{tag}_{i}": None for tag in "ab" for i in range(fields)})

    barrier = threading.Barrier(2)
    errors = []

    def writer(tag):
        try:
            barrier.wait()
            for i in range(fields):
                store.update_node(EVENT, {f"probe_{tag}_{i}": tag})
        except Exception as e:  # 스레드에서 죽으면 조용히 통과하는 것을 막는다
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(tag,)) for tag in "ab"]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors

    node = store.get_node(EVENT)
    kept = sum(
        1 for tag in "ab" for i in range(fields) if node.get(f"probe_{tag}_{i}") == tag
    )
    assert kept == fields * 2, f"{fields * 2}개 중 {kept}개만 남았다 (동시 쓰기 유실)"

    store.update_node(EVENT, {f"probe_{tag}_{i}": None for tag in "ab" for i in range(fields)})
    print(f"  동시 쓰기 {fields * 2}개 모두 보존 OK")


# --- 트랜잭션 ---------------------------------------------------------------


def test_batch_rolls_back_on_failure():
    """batch 안에서 터지면 그 안에서 쓴 것이 남지 않는다"""
    doomed = PREFIX + "rollback"
    try:
        with store.batch():
            store.add_person(PersonNode(id=doomed, name="사라질 사람"))
            raise RuntimeError("중간에 실패")
    except RuntimeError:
        pass

    assert store.get_node(doomed) is None, "실패한 batch의 노드가 남았다"
    print("  batch 롤백 OK")


# --- 엣지 -------------------------------------------------------------------


def test_multiple_relations_between_same_pair_are_kept():
    """같은 두 노드 사이의 다른 관계는 모두 남는다 (JSON과 의도된 차이)"""
    store.add_edge(Edge(source=MEDIA, target=PERSON, relation=RelationType.DEPICTS))
    store.add_edge(Edge(source=MEDIA, target=PERSON, relation=RelationType.NARRATED_BY))

    relations = {
        e["relation"]
        for e in store.get_all_edges()
        if e["source"] == MEDIA and e["target"] == PERSON
    }
    assert relations == {RelationType.DEPICTS, RelationType.NARRATED_BY}, relations

    # remove_edge는 그 쌍의 관계를 모두 지운다 (NetworkX와 같은 의미)
    assert store.remove_edge(MEDIA, PERSON) is True
    assert not [
        e for e in store.get_all_edges() if e["source"] == MEDIA and e["target"] == PERSON
    ]
    print("  복수 관계 보존 · 일괄 삭제 OK")


def test_delete_node_removes_its_edges():
    """노드를 지우면 그 노드에 걸린 관계도 사라진다"""
    temp = PREFIX + "orphan"
    store.add_person(PersonNode(id=temp, name="지울 사람"))
    store.add_edge(Edge(source=temp, target=EVENT, relation=RelationType.PARTICIPATED_IN))

    assert store.delete_node(temp) is True
    assert store.get_node(temp) is None
    assert not [e for e in store.get_all_edges() if temp in (e["source"], e["target"])]
    assert store.delete_node(temp) is False
    print("  노드 삭제 시 엣지 정리 OK")


# --- 순서 -------------------------------------------------------------------


def test_listing_order_is_stable():
    """같은 질의를 두 번 하면 같은 순서로 온다

    순서가 흔들리면 추억 썸네일 3장과 TV 재생 순서가 호출마다 바뀐다.
    """
    first = [n["id"] for n in store.get_connected_nodes(EVENT)]
    second = [n["id"] for n in store.get_connected_nodes(EVENT)]
    assert first == second, (first, second)
    assert set(first) == {PERSON, MEDIA}, first

    assert [n["id"] for n in store.get_nodes_by_type("person")] == [
        n["id"] for n in store.get_nodes_by_type("person")
    ]
    print("  목록 순서 고정 OK")


# --- 상세 -------------------------------------------------------------------


def test_details_group_by_node_type():
    """추억·인물 상세가 종류별로 갈라 담긴다"""
    detail = store.get_event_detail(EVENT)
    assert [p["id"] for p in detail["participants"]] == [PERSON]
    assert [m["id"] for m in detail["media"]] == [MEDIA]
    assert detail["memories"] == []

    # 추억 id로 인물 상세를 물으면 None (종류를 확인한다)
    assert store.get_person_detail(EVENT) is None
    assert store.get_event_detail(PERSON) is None
    print("  상세 분류 OK")


TESTS = [
    test_search_finds_substring,
    test_search_treats_wildcards_literally,
    test_update_node_does_not_lose_concurrent_fields,
    test_batch_rolls_back_on_failure,
    test_multiple_relations_between_same_pair_are_kept,
    test_delete_node_removes_its_edges,
    test_listing_order_is_stable,
    test_details_group_by_node_type,
]


if __name__ == "__main__":
    if not DSN:
        print(
            "TEST_DATABASE_URL이 없어 건너뜁니다.\n"
            '  TEST_DATABASE_URL="postgresql://user@host:5432/db" '
            "python tests/test_store_pg.py"
        )
        sys.exit(0)

    from backend.services.stores.pg_store import PostgresGraphStore

    store = PostgresGraphStore(DSN)
    _cleanup()
    _fixture()

    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {test.__name__}: {type(e).__name__} {e}")

    _cleanup()
    store.close()
    print()
    print(f"{len(TESTS) - failures}/{len(TESTS)} 통과")
    sys.exit(1 if failures else 0)
