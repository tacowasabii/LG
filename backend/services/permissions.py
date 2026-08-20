"""역할에 따른 쓰기 가드 (기획안 02장 Family Space · 08장 권한)

화면이 "지금 쓰는 사람"을 X-Viewer-Id 헤더(또는 viewer_id 쿼리)로 알려 주고,
서버는 그 사람의 역할로 쓰기를 막는다. 사용자 안내서가 약속한 문장을 지키기
위한 것이다: "열람자 — 보고 듣기만 (기록을 바꾸지 않음)".

  !! 이것은 보안 경계가 아니다.
  인증이 없으므로 헤더를 직접 바꾸면 우회된다. 여기서 막는 것은 실수다 —
  열람자로 쓰던 사람이 남의 기록을 지우거나 역할을 바꾸는 일. 진짜 경계는
  로그인이 붙는 자리에 생긴다. 그때 actor()가 토큰에서 사람을 읽으면 아래
  규칙은 그대로 쓸 수 있다.

누가 보냈는지 모를 때(헤더 없음)의 처리를 규칙마다 다르게 둔다.
  쓰기(require_writer)  : 통과시킨다. 인증이 없는 상태에서 막으면 보안은 얻지
                          못하고 화면만 죽는다.
  관리(require_admin)   : 막는다. 누가 했는지 남지 않는 관리 행위는 받지 않는다.
  삭제(require_owner)   : 소유자가 있는 기록이면 막는다. 지우는 일은 되돌릴 수 없다.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Query

from backend.models.graph_models import FamilyRole, NodeType
from backend.services.graph_manager import graph_manager

# 기록을 바꿀 수 있는 역할
WRITER_ROLES = {FamilyRole.OWNER.value, FamilyRole.CONTRIBUTOR.value}

ROLE_LABEL = {
    FamilyRole.OWNER.value: "가족 관리자",
    FamilyRole.CONTRIBUTOR.value: "기록자",
    FamilyRole.VIEWER.value: "열람자",
    FamilyRole.INVITED.value: "초대 대기",
}


async def current_actor(
    x_viewer_id: Optional[str] = Header(None, alias="X-Viewer-Id"),
    viewer_id: Optional[str] = Query(None, description="지금 쓰는 사람"),
) -> Optional[dict]:
    """요청을 보낸 사람의 인물 노드 (모르면 None)

    헤더를 먼저 본다. 쿼리는 GET 조회가 이미 쓰고 있어서 함께 받아 준다.
    """
    person_id = x_viewer_id or viewer_id
    if not person_id:
        return None

    person = graph_manager.get_node(person_id)
    if not person or person.get("node_type") != NodeType.PERSON:
        return None
    return person


def _role(actor: Optional[dict]) -> Optional[str]:
    if not actor:
        return None
    return actor.get("role") or FamilyRole.CONTRIBUTOR.value


def _space_has_owner() -> bool:
    return any(
        (p.get("role") or "") == FamilyRole.OWNER.value for p in graph_manager.get_persons()
    )


def require_writer(actor: Optional[dict]) -> None:
    """기록을 바꾸는 행위 — 열람자·초대 대기는 막는다"""
    role = _role(actor)
    if role is None:
        # 누가 보냈는지 모른다. 인증이 없는 상태에서 막아도 얻는 것이 없다.
        return
    if role not in WRITER_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{actor.get('name', '')}님은 {ROLE_LABEL.get(role, role)}입니다. "
                "기록을 바꾸려면 기록자 이상의 역할이 필요합니다."
            ),
        )


def require_admin(actor: Optional[dict]) -> None:
    """역할 변경·초대처럼 공간을 관리하는 행위

    아직 가족 관리자를 정하지 않은 공간에서는 기록자도 할 수 있다 (초기 설정).
    관리자가 정해지면 그 사람만 할 수 있다.
    """
    role = _role(actor)
    if role is None:
        raise HTTPException(
            status_code=403,
            detail="누가 하는 일인지 알 수 없습니다. 사용할 사람을 먼저 고르세요.",
        )

    if role == FamilyRole.OWNER.value:
        return

    if not _space_has_owner() and role == FamilyRole.CONTRIBUTOR.value:
        # 관리자가 아직 없는 공간. 첫 설정을 막으면 아무도 관리자를 정할 수 없다.
        return

    raise HTTPException(
        status_code=403,
        detail=(
            f"{actor.get('name', '')}님은 {ROLE_LABEL.get(role, role)}입니다. "
            "구성원과 초대는 가족 관리자가 정합니다."
        ),
    )


def require_owner_of(node: dict, actor: Optional[dict], what: str = "기록") -> None:
    """되돌릴 수 없는 행위 — 그 기록의 소유자나 가족 관리자만

    소유자가 비어 있는 기록(권한 개념이 생기기 전에 들어온 것)은 관리자와
    기록자가 정리할 수 있게 둔다. 그마저 막으면 시드 데이터를 아무도 못 지운다.
    """
    role = _role(actor)
    # 기억 문장의 주인은 그것을 남긴 사람이다. 원본(미디어)은 owner_id에 올린
    # 사람이 남고, 기억에는 contributor_id에 말한 사람이 남고, 추억(사건)에는
    # author_id에 만든 사람이 남는다 — 이름만 다르고 "이 기록은 누구의 것인가"는
    # 같은 질문이므로 규칙을 세 벌로 두지 않는다.
    owner_id = (
        node.get("owner_id") or node.get("contributor_id") or node.get("author_id")
    )

    if role is None:
        if owner_id:
            raise HTTPException(
                status_code=403,
                detail=f"이 {what}은 올린 사람만 지울 수 있습니다. 사용할 사람을 먼저 고르세요.",
            )
        return

    if role not in WRITER_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{actor.get('name', '')}님은 {ROLE_LABEL.get(role, role)}입니다. "
                f"{what}을 지울 수 없습니다."
            ),
        )

    if role == FamilyRole.OWNER.value:
        return
    if not owner_id or owner_id == actor["id"]:
        return

    owner = graph_manager.get_node(owner_id)
    owner_name = owner.get("name", "") if owner else owner_id
    raise HTTPException(
        status_code=403,
        detail=f"이 {what}은 {owner_name}님이 올렸습니다. 올린 사람이나 가족 관리자만 지울 수 있습니다.",
    )
