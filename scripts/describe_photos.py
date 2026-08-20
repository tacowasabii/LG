"""사진 장면 설명 채우기 (backfill)

    python scripts/describe_photos.py            # 설명이 없는 사진 전부
    python scripts/describe_photos.py --limit 5  # 앞 5장만
    python scripts/describe_photos.py --redo     # 이미 있는 것까지 다시 읽는다

추억 초안은 세 장만 읽는다 (services/vision.DRAFT_LIMIT). 사용자를 기다리게 하는
경로라서 상한을 둔 것이고, 그래서 나머지 사진은 설명이 비어 있다.

설명이 비어 있으면 잃는 것은 초안이 아니라 검색과 채팅이다.
    graph_search   사진을 내용으로 찾지 못한다 ("바다 나온 사진")
    chat_engine    답변 컨텍스트에 "장면: …"이 붙지 않는다
    stores/base    Postgres trigram 색인에 사진 텍스트가 없다

그래서 나머지는 여기서 미리 채운다. 발표 전에 한 번 돌려 두면 검색이 사진 내용까지
닿는다. scripts/generate_profiles.py 와 같은 성격의 일회성 보강 작업이다.

실측: 장당 약 8초. 24장이면 3분쯤 걸린다.
Bedrock 자격증명이 없으면 아무것도 하지 않고 알린다 (services/vision.py).
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import MediaType  # noqa: E402
from backend.services import llm_client, vision  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402


def _photos(redo: bool) -> list[dict]:
    nodes = [
        node
        for node in graph_manager.get_media_nodes()
        if node.get("media_type") == MediaType.PHOTO
    ]
    if redo:
        return nodes
    return [node for node in nodes if not (node.get("scene_description") or "").strip()]


async def main() -> int:
    parser = argparse.ArgumentParser(description="사진 장면 설명 채우기")
    parser.add_argument("--limit", type=int, default=None, help="앞 N장만")
    parser.add_argument(
        "--redo",
        action="store_true",
        help="이미 설명이 있는 사진까지 다시 읽는다 (시드 설명을 모델 설명으로 바꿀 때)",
    )
    args = parser.parse_args()

    if not llm_client.bedrock_enabled():
        print(
            "Bedrock 자격증명이 없습니다. .env에 AWS_ACCESS_KEY_ID / "
            "AWS_SECRET_ACCESS_KEY 를 넣으세요 (.env.example 참고).\n"
            "EXAONE 게이트웨이는 이미지를 받지 않으므로 여기서는 폴백하지 않습니다."
        )
        return 1

    targets = _photos(args.redo)
    if args.limit is not None:
        targets = targets[: args.limit]

    if not targets:
        print("채울 사진이 없습니다. (--redo 로 이미 있는 것까지 다시 읽을 수 있습니다)")
        return 0

    if args.redo:
        # describe_missing은 비어 있는 것만 고르므로, 다시 읽으려면 먼저 비운다
        for node in targets:
            graph_manager.update_node(node["id"], {"scene_description": None, "scene_source": None})
            node["scene_description"] = None

    print(f"사진 {len(targets)}장을 읽습니다 (장당 약 8초)...\n")

    filled = await vision.describe_missing(targets, limit=None)

    for node in targets:
        fresh = graph_manager.get_node(node["id"])
        description = (fresh or {}).get("scene_description")
        name = (fresh or {}).get("original_filename") or node["id"]
        if description:
            print(f"  {name}\n    {description}\n")
        else:
            print(f"  {name}\n    (읽지 못했습니다 — 설명을 비워 둡니다)\n")

    print(f"{filled}/{len(targets)}장을 채웠습니다.")
    if filled < len(targets):
        print("못 채운 사진은 다시 돌리면 됩니다 (이미 채운 것은 건너뜁니다).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
