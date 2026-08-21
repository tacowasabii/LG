"""아무것도 걸리지 않은 장소를 거둔다 (이미 남아 있는 것 치우기)

    python scripts/prune_orphan_places.py                 # 무엇이 지워질지만 보여준다
    python scripts/prune_orphan_places.py --delete         # 실제로 지운다
    python scripts/prune_orphan_places.py --delete --quiet # 치울 것이 없으면 조용히 (부팅)

## 왜 이 스크립트가 있는가

장소는 파생 노드다. 사진의 EXIF 좌표에서 짐작한 지명이 추억의 장소 칸에 채워지고
(routers/media.py의 place_guess), 그 추억이 가리키는 동안만 존재할 이유가 있다.
스스로 열리는 화면이 없다 — 지도는 사건을 그리고 사진첩은 원본을 그린다.

그런데 추억을 지울 때 장소는 남겨 두고 있었다. 그래서 사건도 사진도 없는 장소가
연결된 기억 화면에 아무것도 걸리지 않은 점으로 떠 있었다 — 배포된 그래프의
"강원 홍천"과 "경기 수원"이 그것이다.

앞으로 생기는 것은 추억을 지우는 자리에서 그때 거둔다
(services/event_resolver.prune_orphan_places). 이 스크립트는 그 고침 이전에
이미 남아 있는 것을 치운다.

이미 돌고 있는 배포에는 그 고침이 소급되지 않으므로 scripts/boot.py가 부팅마다
이것을 부른다 — 영상 썸네일 채우기와 같은 이유다. 치울 것이 없으면 아무것도
하지 않으므로 매 부팅에 돌려도 된다.

## 장소만 거두는 이유

연결이 없는 노드가 곧 쓰레기인 것은 아니다.

    인물   가족 공간과 인물 화면이 노드를 그대로 나열한다. 사건에 한 번도
           나오지 않은 사람도 가족이다
    원본   사진첩이 노드를 그대로 나열한다. 추억에 붙지 않은 사진도 사진첩에
           있어야 한다 (붙이는 것은 사람이 고르는 일이다)
    기억   사건 없는 기억 문장은 닿을 수 없지만, 지우는 자리가 이미 있다
           (memories.delete_memory). 여기서 함께 손대면 판정이 두 벌이 된다

장소만이 "가리킬 것이 없으면 존재할 이유가 없는" 노드다.
"""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import event_resolver  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--delete",
        action="store_true",
        help="실제로 지운다 (없으면 목록만 보여준다)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "부팅에서 부를 때. 치울 것이 없으면 아무것도 찍지 않고, 실패해도 0으로 "
            "끝난다 (청소가 컨테이너 시작을 막지 않게)"
        ),
    )
    args = parser.parse_args()

    try:
        return _prune(args)
    except Exception as e:  # noqa: BLE001
        # 부팅에서는 여기서 멈추지 않는다. boot.py의 _run은 0이 아닌 종료를 다시
        # 올리고, docker_start.sh가 그걸 받아 컨테이너를 세우지 못한다 — 장소
        # 하나를 못 치운 것으로 앱 전체가 뜨지 않는 것은 바꿔치기가 나쁘다.
        # 대신 이유를 로그에 그대로 남긴다.
        print(f"[prune] 실패: {type(e).__name__}: {e}")
        if args.quiet:
            return 0
        raise


def _prune(args) -> int:
    orphans = event_resolver.orphan_places()

    if not orphans:
        if not args.quiet:
            print(f"장소 {len(graph_manager.get_places())}개 · 치울 것이 없습니다.")
        return 0

    print(f"아무것도 걸리지 않은 장소 {len(orphans)}개")
    for place in orphans:
        name = place.get("name") or "(이름 없음)"
        lat, lng = place.get("lat"), place.get("lng")
        where = f"{lat}, {lng}" if lat is not None and lng is not None else "좌표 없음"
        print(f"  {place['id']:>20}  {name}  ({where})")

    if not args.delete:
        print()
        print("지우지 않았습니다. 위 목록이 맞으면 --delete 를 붙여 다시 실행하세요.")
        return 0

    # 판정은 event_resolver 한 곳에만 둔다. 여기서 delete_node를 직접 부르면
    # 추억을 지울 때와 규칙이 두 벌이 된다.
    with graph_manager.batch():
        deleted = event_resolver.prune_orphan_places([p["id"] for p in orphans])

    print()
    print(f"{len(deleted)}개를 지웠습니다.")

    # 지운 뒤 다시 세어 대조한다 — "지웠습니다"만 찍고 남아 있으면 어디를 봐야
    # 할지 알 수 없다
    left = event_resolver.orphan_places()
    if left:
        print(f"아직 {len(left)}개가 남아 있습니다: {[p['id'] for p in left]}")
        return 0 if args.quiet else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
