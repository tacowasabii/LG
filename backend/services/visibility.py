"""공개 범위 판정 (기획안 08장 Asset 권한 · 인물 동의)

기획안이 부가기능이 아니라 사업 지속 가능성이라고 못 박은 부분이다.
설정만 저장하고 실제로 가려 주지 않으면 아무 의미가 없으므로, 기록을 내보내는
모든 통로가 이 모듈을 지나게 한다.

    미디어 목록 · 추억 요약의 썸네일 · 인물 상세 · 채팅 근거 검색

두 가지 규칙이 겹친다.
  1. Asset 권한   기록 자체의 공개 범위 (family / partial / private)
  2. 인물 동의    그 기록에 등장하는 사람이 비공개를 요청했는가

둘 중 하나라도 막으면 가린다. 소유자는 자기 기록을 항상 볼 수 있다.

기억 문장(Memory)도 같은 판정을 지난다. 원본 사진만 가리고 그 사진을 설명한
인터뷰 문장은 그대로 보여 주면, 가린 것이 아니라 형태만 바꿔 보여 준 것이 된다.
  - 기억을 남긴 본인은 언제나 본다
  - 기여자가 비공개를 요청했으면 나머지 가족에게 가린다 (그 사람의 목소리다)
  - 근거로 이어진 원본(EVIDENCED_BY)이 있는데 그중 볼 수 있는 것이 하나도 없으면
    가린다. 볼 수 없는 사진의 내용을 문장으로 옮겨 말하는 일을 막는다.
근거가 아예 없는 기억(대부분의 인터뷰 답변)은 위 두 규칙만 지나면 보인다 —
근거 없음을 이유로 가리면 기억 대부분이 사라진다.

viewer_id가 없으면(누가 보는지 모르면) 가족 전체 공개만 통과시킨다.
로그인이 붙기 전까지는 화면이 "지금 보는 사람"을 넘겨 준다.

성능: 목록 한 번에 수천 건이 들어오므로, 인물 동의 판정에 필요한 엣지를 목록마다
한 번만 색인한다. 예전에는 노드마다 전체 엣지를 순회해서 미디어 1만 × 엣지 5만이면
5억 번을 돌았다. 비공개를 요청한 사람이 아무도 없으면 엣지를 아예 읽지 않는다.
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.models.graph_models import NodeType, RelationType, Visibility
from backend.services.graph_manager import graph_manager

# 사람이 "등장한다"고 볼 관계 (사진에 찍힘 · 목소리의 주인)
APPEARANCE_RELATIONS = (RelationType.DEPICTS, RelationType.NARRATED_BY)


class ConsentIndex:
    """인물 동의 판정에 필요한 것만 미리 모아 둔다

    - private_persons: 비공개를 요청한 사람들
    - appearing: 기록 id -> 그 기록에 등장하는 사람들

    비공개 요청이 하나도 없으면 엣지를 읽지 않는다 (대부분의 경우).
    """

    __slots__ = ("private_persons", "appearing", "_evidence")

    def __init__(self) -> None:
        self.private_persons: set[str] = {
            person["id"]
            for person in graph_manager.get_persons()
            if person.get("private_request")
        }

        self.appearing: dict[str, set[str]] = {}
        # 기억 -> 근거 원본. 기억을 판정할 때만 필요하므로 그때 한 번 만든다.
        self._evidence: Optional[dict[str, set[str]]] = None
        if not self.private_persons:
            return

        for edge in graph_manager.get_all_edges():
            if edge["relation"] not in APPEARANCE_RELATIONS:
                continue
            if edge["target"] not in self.private_persons:
                # 비공개를 요청하지 않은 사람은 판정에 영향이 없다
                continue
            self.appearing.setdefault(edge["source"], set()).add(edge["target"])

    def evidence_of(self, memory_id: str) -> set[str]:
        """이 기억이 근거로 가리키는 원본들 (EVIDENCED_BY)"""
        if self._evidence is None:
            index: dict[str, set[str]] = {}
            for edge in graph_manager.get_all_edges():
                if edge["relation"] == RelationType.EVIDENCED_BY:
                    index.setdefault(edge["source"], set()).add(edge["target"])
            self._evidence = index
        return self._evidence.get(memory_id, set())

    def blocks(self, node: dict, viewer_id: Optional[str]) -> bool:
        """등장 인물의 비공개 요청에 걸리는가

        본인은 자기가 나온 기록을 볼 수 있다. 막히는 것은 나머지 가족이다.
        """
        if not self.private_persons:
            return False

        # 노드에 박혀 있는 것(얼굴 인식 결과·화자)과 엣지로 이어진 것을 함께 본다
        appearing = set(self.appearing.get(node["id"], ()))
        appearing.update(
            person_id
            for person_id in (node.get("detected_faces") or [])
            if person_id in self.private_persons
        )
        speaker_id = node.get("speaker_id")
        if speaker_id and speaker_id in self.private_persons:
            appearing.add(speaker_id)

        return any(person_id != viewer_id for person_id in appearing)


def can_view(
    node: dict,
    viewer_id: Optional[str],
    index: Optional[ConsentIndex] = None,
) -> bool:
    """이 사람이 이 기록을 볼 수 있는가

    index를 주면 인물 동의 색인을 재사용한다. 목록을 걸러낼 때는 반드시 넘긴다.
    """
    if not node:
        return False

    node_type = node.get("node_type")

    if node_type == NodeType.MEMORY:
        return _can_view_memory(node, viewer_id, index or ConsentIndex())

    # 사람·추억·장소에는 공개 범위를 두지 않는다. 가려야 하는 것은 원본 기록과
    # 그 기록을 말로 옮긴 기억이다.
    if node_type != NodeType.MEDIA:
        return True

    owner_id = node.get("owner_id")
    if viewer_id and owner_id and viewer_id == owner_id:
        return True

    # 공개 범위 필드가 없는 기록(권한 개념이 생기기 전에 들어온 것)은 가족 전체로
    # 본다. 제품의 기본값과 같은 값이다. 여기서 "안전하게" private으로 잡으면 기존
    # 기록 전부가 사라진다 — 동의를 지키는 게 아니라 기억을 잃는 것이 된다.
    visibility = node.get("visibility") or Visibility.FAMILY

    if visibility == Visibility.PRIVATE:
        # 올린 사람만 본다. 소유자가 비어 있으면 아무도 볼 수 없다 —
        # 비공개로 바꿀 때 소유자를 함께 기록해야 한다 (family.set_media_visibility).
        return False

    if visibility == Visibility.PARTIAL:
        if not viewer_id:
            return False
        if viewer_id not in (node.get("allowed_ids") or []):
            return False

    # 가족 전체 공개라도, 등장 인물이 비공개를 요청했으면 가린다
    return not (index or ConsentIndex()).blocks(node, viewer_id)


def _can_view_memory(
    memory: dict, viewer_id: Optional[str], index: ConsentIndex
) -> bool:
    """기억 문장을 이 사람이 볼 수 있는가

    원본만 가리고 그 원본을 설명한 문장을 그대로 보여 주면 동의를 지킨 것이
    아니다 (기획안 08장 "삭제·이관"과 "출처 보존"이 같은 곳을 가리킨다).
    """
    contributor_id = memory.get("contributor_id")

    # 자기가 남긴 기억은 언제나 본다
    if viewer_id and contributor_id and contributor_id == viewer_id:
        return True

    # 기여자가 비공개를 요청했으면 나머지 가족에게 가린다 — 그 사람의 목소리다
    if contributor_id and contributor_id in index.private_persons:
        return False

    evidence_ids = index.evidence_of(memory.get("id", ""))
    if not evidence_ids:
        # 근거가 없는 기억(대부분의 인터뷰 답변)은 여기서 막지 않는다.
        # 근거 없음을 이유로 가리면 기억 대부분이 사라진다.
        return True

    # 근거로 이어진 원본 중 하나라도 볼 수 있으면 문장도 볼 수 있다
    return any(
        can_view(graph_manager.get_node(media_id), viewer_id, index)
        for media_id in evidence_ids
    )


def _filter(nodes: Iterable[dict], viewer_id: Optional[str]) -> list[dict]:
    """색인을 한 번만 만들어 목록 전체를 판정한다"""
    index = ConsentIndex()
    return [node for node in nodes if can_view(node, viewer_id, index)]


def filter_media(nodes: Iterable[dict], viewer_id: Optional[str]) -> list[dict]:
    """미디어 목록에서 볼 수 없는 것을 걷어낸다"""
    return _filter(nodes, viewer_id)


def filter_memories(nodes: Iterable[dict], viewer_id: Optional[str]) -> list[dict]:
    """기억 목록에서 볼 수 없는 것을 걷어낸다

    추억 상세 · 인물 상세 · 기억 이어가기 목록 · 내보내기가 모두 이걸 지난다.
    """
    return _filter(nodes, viewer_id)


def filter_search_results(nodes: Iterable[dict], viewer_id: Optional[str]) -> list[dict]:
    """채팅 검색 결과에서 가려야 할 원본을 걷어낸다

    답변의 근거로도 쓰이지 않게 검색 단계에서 뺀다. 근거 뱃지에서만 감추면
    LLM이 본문에서 그 사진의 장면 설명을 말해 버린다.
    """
    return _filter(nodes, viewer_id)


def summary(viewer_id: Optional[str]) -> dict:
    """지금 이 사람에게 몇 개가 가려지는지 (화면에 밝히기 위한 값)"""
    media = graph_manager.get_media_nodes()
    visible = filter_media(media, viewer_id)
    return {
        "viewer_id": viewer_id,
        "media_total": len(media),
        "visible": len(visible),
        "hidden": len(media) - len(visible),
    }
