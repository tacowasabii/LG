"""가족 공간 (기획안 02장 CORE · COLLECT · Family Space)

구성원은 그래프의 인물 노드 그대로다. 사람 목록을 따로 두면 "사진 속 그 사람"과
"이 서비스를 쓰는 사람"이 갈라지고, 기억의 귀속이 흐려진다. 그래서 역할과 동의를
인물 노드에 얹었다.

공간 이름과 초대 코드는 그래프에 넣을 것이 아니라 운영 설정이라 별도 파일에 둔다.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from backend.config import DATA_DIR
from backend.models.graph_models import FamilyRole, NodeType, RelationType
from backend.services.graph_manager import graph_manager

SPACE_FILE = DATA_DIR / "family_space.json"

# 초대 링크가 살아 있는 시간
INVITE_TTL_HOURS = 72

ROLE_ORDER = [
    FamilyRole.OWNER.value,
    FamilyRole.CONTRIBUTOR.value,
    FamilyRole.VIEWER.value,
    FamilyRole.INVITED.value,
]


def _load_space() -> dict:
    if SPACE_FILE.exists():
        with open(SPACE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"space_name": "", "invites": []}


def _save_space(data: dict) -> None:
    SPACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SPACE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _default_space_name() -> str:
    """공간 이름을 정하지 않았으면 어른들의 이름으로 만든다"""
    persons = graph_manager.get_persons()
    parents = [p for p in persons if p.get("relation") in ("아빠", "엄마")]
    names = [p.get("name", "") for p in sorted(parents, key=lambda p: p.get("birth_year") or 0)]
    if names:
        return "·".join(names) + " 가족"
    return "우리 가족"


def _counts_for(person_id: str) -> dict:
    """이 사람이 이 공간에 남긴 것"""
    assets = 0
    memories = 0

    for media in graph_manager.get_media_nodes():
        if media.get("owner_id") == person_id:
            assets += 1

    for memory in graph_manager.get_memories():
        if memory.get("contributor_id") == person_id:
            memories += 1

    verified = 0
    for event in graph_manager.get_events():
        for record in event.get("verifications") or []:
            if record.get("person_id") == person_id:
                verified += 1

    return {"asset_count": assets, "memory_count": memories, "verified_count": verified}


def list_members() -> list[dict]:
    """구성원 목록. 역할 순서로 정렬한다 (관리자 → 기록자 → 열람자 → 초대 대기)"""
    members = []
    for person in graph_manager.get_persons():
        role = person.get("role") or FamilyRole.CONTRIBUTOR.value
        members.append({
            "id": person["id"],
            "name": person.get("name", ""),
            "relation": person.get("relation", ""),
            "birth_year": person.get("birth_year"),
            "thumbnail_url": person.get("thumbnail_url"),
            "role": role,
            "joined_at": person.get("joined_at"),
            "private_request": bool(person.get("private_request")),
            **_counts_for(person["id"]),
        })

    members.sort(key=lambda m: (ROLE_ORDER.index(m["role"]) if m["role"] in ROLE_ORDER else 9, m["name"]))
    return members


def get_space() -> dict:
    space = _load_space()
    name = space.get("space_name") or _default_space_name()

    # 만료된 초대는 목록에서 뺀다
    now = datetime.now()
    invites = [
        invite
        for invite in space.get("invites", [])
        if invite.get("expires_at") and datetime.fromisoformat(invite["expires_at"]) > now
    ]

    return {
        "space_name": name,
        "members": list_members(),
        "invites": invites,
    }


def update_member(
    person_id: str,
    role: Optional[str] = None,
    private_request: Optional[bool] = None,
) -> Optional[dict]:
    """역할·비공개 요청 변경"""
    person = graph_manager.get_node(person_id)
    if not person or person.get("node_type") != NodeType.PERSON:
        return None

    updates: dict = {}

    if role is not None:
        if role not in ROLE_ORDER:
            raise ValueError("알 수 없는 역할입니다: " + role)
        updates["role"] = role
        # 초대 대기에서 벗어나는 순간이 참여 시점이다
        if role != FamilyRole.INVITED.value and not person.get("joined_at"):
            updates["joined_at"] = datetime.now().date().isoformat()

    if private_request is not None:
        updates["private_request"] = bool(private_request)

    if updates:
        graph_manager.update_node(person_id, updates)

    return next((m for m in list_members() if m["id"] == person_id), None)


def create_invite(person_id: Optional[str] = None) -> dict:
    """초대 링크 발급

    특정 인물을 지목하면 그 사람을 초대 대기로 표시한다. 지목하지 않으면
    누구나 쓸 수 있는 링크가 된다 (QR로 띄우는 경우).
    """
    space = _load_space()
    code = "HS-" + secrets.token_hex(2).upper() + "-" + secrets.token_hex(2).upper()
    expires_at = datetime.now() + timedelta(hours=INVITE_TTL_HOURS)

    invite = {
        "code": code,
        "link": "https://homestory.lge.com/join/" + code,
        "person_id": person_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "expires_in_hours": INVITE_TTL_HOURS,
    }

    space.setdefault("invites", []).append(invite)
    space["space_name"] = space.get("space_name") or _default_space_name()
    _save_space(space)

    if person_id:
        person = graph_manager.get_node(person_id)
        if person and person.get("node_type") == NodeType.PERSON:
            graph_manager.update_node(person_id, {"role": FamilyRole.INVITED.value})

    return invite


def rename_space(name: str) -> dict:
    space = _load_space()
    space["space_name"] = name.strip() or _default_space_name()
    _save_space(space)
    return get_space()


def ownership_summary() -> list[dict]:
    """누가 얼마나 모았는지 (소유자가 비어 있는 기록은 따로 센다)"""
    rows = []
    for member in list_members():
        if member["asset_count"] > 0:
            rows.append({"id": member["id"], "name": member["name"], "count": member["asset_count"]})

    unowned = sum(1 for m in graph_manager.get_media_nodes() if not m.get("owner_id"))
    if unowned:
        rows.append({"id": None, "name": "소유자 미지정", "count": unowned})

    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows


def set_media_visibility(
    media_id: str,
    visibility: str,
    allowed_ids: Optional[list[str]] = None,
    owner_id: Optional[str] = None,
) -> Optional[dict]:
    """기록 하나의 공개 범위를 정한다"""
    from backend.models.graph_models import Visibility

    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        return None

    valid = {v.value for v in Visibility}
    if visibility not in valid:
        raise ValueError("알 수 없는 공개 범위입니다: " + visibility)

    updates: dict = {"visibility": visibility}
    if allowed_ids is not None:
        updates["allowed_ids"] = [
            person_id
            for person_id in allowed_ids
            if graph_manager.get_node(person_id)
        ]
    if owner_id is not None:
        updates["owner_id"] = owner_id

    graph_manager.update_node(media_id, updates)
    return graph_manager.get_node(media_id)


def delete_cascade_preview(media_id: str) -> Optional[dict]:
    """이 원본을 지우면 무엇이 함께 사라지는지 (기획안 08장 삭제 전파)

    지우기 전에 보여주기 위한 것이다. 실제 삭제는 DELETE /api/media/{id}가 한다.
    """
    node = graph_manager.get_node(media_id)
    if not node or node.get("node_type") != NodeType.MEDIA:
        return None

    edges = [
        edge
        for edge in graph_manager.get_all_edges()
        if edge["source"] == media_id or edge["target"] == media_id
    ]

    derived = []
    if node.get("thumbnail_path") and node["thumbnail_path"] != node.get("file_path"):
        derived.append({"label": "썸네일 1개", "detail": node["thumbnail_path"].split("/")[-1]})

    events = [
        graph_manager.get_node(edge["target"])
        for edge in edges
        if edge["source"] == media_id and edge["relation"] == RelationType.CAPTURED_DURING
    ]
    for event in events:
        if event:
            derived.append({
                "label": "Memory Film 장면",
                "detail": event.get("title", "") + " 구성에서 빠집니다",
            })

    # 이 원본을 근거로 삼은 기억 — 문장은 남고 연결만 끊긴다
    evidencing = [
        edge["source"]
        for edge in edges
        if edge["target"] == media_id and edge["relation"] == RelationType.EVIDENCED_BY
    ]
    if evidencing:
        derived.append({
            "label": "기억 " + str(len(evidencing)) + "개의 음성 근거",
            "detail": "기억 문장은 지워지지 않고 연결만 끊깁니다",
        })

    derived.append({
        "label": "그래프 연결 " + str(len(edges)) + "개",
        "detail": " · ".join(sorted({edge["relation"] for edge in edges})),
    })

    return {
        "media_id": media_id,
        "target": node.get("original_filename") or media_id,
        "scene_description": node.get("scene_description"),
        "derived": derived,
    }
