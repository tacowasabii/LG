"""지운 추억이 그래프 밖에 남긴 것을 거둔다

    python scripts/prune_deleted_remnants.py                 # 무엇이 지워질지만 보여준다
    python scripts/prune_deleted_remnants.py --delete         # 실제로 지운다
    python scripts/prune_deleted_remnants.py --delete --quiet # 치울 것이 없으면 조용히 (부팅)

## 왜 이 스크립트가 있는가

추억을 지우는 자리(services/memories.delete_event)는 그래프와 원본 파일을 함께
거둔다. 실제로 배포에서 확인했다 — 추억 하나를 지운 뒤 고아 기억·고아 원본·고아
장소·끊긴 엣지가 하나도 없었다.

그런데 원본에서 파생된 것들은 그 자리에서 거두지 않는다. 지우는 코드가 가진
파일 삭제는 media_analyzer.erase_files 하나뿐이고, 그 함수는 노드에 적힌
file_path와 thumbnail_path만 본다. 미세 모션 클립은 그 두 칸에 없다 —
MEDIA_DIR/motion/<media_id>.mp4 라는 별도 규칙으로 붙어 있어서 아무도 지우지
않았다. 배포에서 클립 12개(mp4 + poster.jpg, 약 4.7MB)가 그렇게 남아 있었다.

남은 클립이 화면에 섞여 보이지는 않는다. 화면은 사진 id를 주고 그 id의 클립만
받아 간다 (routers/film.motion_status의 media_ids). 문제는 다른 데 있다.

  - poster.jpg는 **지운 사진의 첫 프레임**이다. 주소를 아는 사람에게 그 사진은
    지워지지 않았다. erase_files의 주석이 "파일이 남으면 주소를 아는 사람에게는
    지워지지 않은 것이다"라고 적은 바로 그 상태다
  - 매니페스트에 없는 사진의 항목이 쌓인다. /api/health의 clips 수가 실제보다
    많게 나오고, 볼륨(500MB)이 조용히 찬다

## 무엇을 지우고 무엇을 남기는가

지운다 — 그래프에 그 사진이 없는 런타임 클립(파일 + 매니페스트 항목),
없는 추억의 대표 사진 선택, 기준선에 남은 없는 추억 id.

남긴다 — **저장소에 커밋된 클립**(data/motion/manifest.json). 그 파일은 이미지에
함께 들어오므로 컨테이너에서 지워도 다음 배포에 돌아온다. 게다가 id가 그래프에
없다는 것이 곧 쓸모없다는 뜻이 아니다: 배포에서 E06 사진을 지우고 같은 파일을
다시 올려 id가 E06_001 -> media_deb40ef6 로 바뀐 상태다
(scripts/restore_seed_media.py의 사정). 그 클립은 살아 있는 사진의 것이다.
그래서 여기서는 알리기만 하고, 손보려면 저장소 파일을 고친다.

남긴다 — 쓴 예산(motion_spend.json). 지운 사진에 이미 나간 돈은 돌아오지 않는다.
세는 값을 되돌리면 상한이 지키는 것이 무엇인지 흐려진다.

남긴다 — 채점 리포트(trust_report.json). 그 파일도 지운 추억을 아직 근거로 들고
있지만, Trust 화면은 저장된 리포트만 읽고 (routers/trust.get_report) 다시 채점은
LLM 호출 20번에 몇 분이 걸린다. 시연 중에 그 화면이 비는 쪽이 더 나쁘다.
고칠 자리는 여기가 아니라 POST /api/trust/run 이다.

## 부팅에서 부르는 이유

이미 돌고 있는 배포에는 고침이 소급되지 않는다. scripts/boot.py가 부팅마다
부른다 — 장소 청소(prune_orphan_places)와 같은 이유다. 치울 것이 없으면
아무것도 하지 않으므로 매 부팅에 돌려도 된다.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# 로그가 청소를 막지 않게 한다. Windows 콘솔은 기본이 cp949라서 em-dash 같은
# 글자에서 print가 UnicodeEncodeError로 죽고, --quiet은 그 예외를 삼켜 조용히
# 아무것도 지우지 않는다 (여기서 실제로 그렇게 한 번 넘어갔다).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

from backend.config import MOTION_BASELINE_FILE, MOTION_COVERS_FILE  # noqa: E402
from backend.services import motion_clips  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

# 클립 하나가 남기는 파일. source는 --keep-source로 만들 때만 생긴다.
CLIP_SUFFIXES = (".mp4", ".poster.jpg", ".source.mp4")


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clip_files(media_id: str) -> list[Path]:
    """이 사진의 클립이 남긴 파일 중 실제로 있는 것"""
    return [
        path
        for path in (motion_clips.SERVE_DIR / f"{media_id}{s}" for s in CLIP_SUFFIXES)
        if path.exists()
    ]


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
        # prune_orphan_places와 같은 판단이다. 청소 하나가 실패한 것으로 앱 전체가
        # 뜨지 않는 것은 바꿔치기가 나쁘다. 이유는 로그에 그대로 남긴다.
        print(f"[remnants] 실패: {type(e).__name__}: {e}")
        if args.quiet:
            return 0
        raise


def _prune(args) -> int:
    live_media = {node["id"] for node in graph_manager.get_media_nodes()}
    live_events = {node["id"] for node in graph_manager.get_events()}

    lines: list[str] = []
    # (무엇을 지울지)를 먼저 다 모은다. --delete 없이 부를 때 보여줄 목록이
    # 실제로 지우는 것과 같아야 한다.
    todo: list[tuple[str, object]] = []

    # --- 1. 그래프에 없는 사진의 런타임 클립 ---
    runtime = motion_clips.runtime_manifest()
    orphan_clips = sorted(k for k in runtime if k not in live_media)
    orphan_files = {media_id: _clip_files(media_id) for media_id in orphan_clips}
    if orphan_clips:
        total = sum(path.stat().st_size for paths in orphan_files.values() for path in paths)
        lines.append(f"없는 사진의 모션 클립 {len(orphan_clips)}개 ({total / 1024:.0f}KB)")
        for media_id in orphan_clips:
            names = ", ".join(p.name for p in orphan_files[media_id]) or "파일 없음"
            lines.append(f"  {media_id:>18}  {names}")
        todo.append(("clips", (runtime, orphan_clips, orphan_files)))

    # 저장소에 커밋된 클립은 지우지 않는다 (모듈 docstring 참고). 알리기만 한다.
    baked_orphans = sorted(k for k in motion_clips.baked_manifest() if k not in live_media)
    if baked_orphans and not args.quiet:
        lines.append(
            f"저장소에 커밋된 클립 {len(baked_orphans)}개도 그래프에 없다: "
            f"{', '.join(baked_orphans)}"
        )
        lines.append("  (이미지에 함께 들어오므로 여기서 지우지 않는다: data/motion/manifest.json)")

    # --- 2. 없는 추억의 대표 사진 선택 ---
    covers = _read_json(MOTION_COVERS_FILE)
    dead_covers = sorted(k for k in covers if k not in live_events)
    if dead_covers:
        lines.append(f"없는 추억의 대표 사진 선택 {len(dead_covers)}개: {', '.join(dead_covers)}")
        todo.append(("covers", (covers, dead_covers)))

    # --- 3. 기준선에 남은 없는 추억 ---
    baseline = _read_json(MOTION_BASELINE_FILE)
    recorded = baseline.get("event_ids")
    dead_baseline = (
        sorted(x for x in recorded if x not in live_events)
        if isinstance(recorded, list)
        else []
    )
    if dead_baseline:
        lines.append(
            f"자동 생성 기준선에 남은 없는 추억 {len(dead_baseline)}개: "
            f"{', '.join(dead_baseline)}"
        )
        todo.append(("baseline", (baseline, recorded, dead_baseline)))

    if not todo:
        if not args.quiet:
            print("그래프 밖에 남은 것이 없습니다.")
        return 0

    for line in lines:
        print(line)

    if not args.delete:
        print()
        print("지우지 않았습니다. 위 목록이 맞으면 --delete 를 붙여 다시 실행하세요.")
        return 0

    print()
    for kind, payload in todo:
        if kind == "clips":
            runtime, orphan_clips, orphan_files = payload
            removed = 0
            for media_id in orphan_clips:
                for path in orphan_files[media_id]:
                    path.unlink()
                    removed += 1
                runtime.pop(media_id, None)
            # 파일을 먼저, 매니페스트를 나중에. 반대로 하면 항목만 사라지고 파일이
            # 남아 다음 실행에서 찾을 길이 없다 (id를 매니페스트에서만 안다).
            _write_json(motion_clips.MOTION_RUNTIME_MANIFEST_FILE, runtime)
            print(f"모션 클립 {len(orphan_clips)}개 · 파일 {removed}개를 지웠습니다.")

        elif kind == "covers":
            covers, dead_covers = payload
            for event_id in dead_covers:
                covers.pop(event_id, None)
            _write_json(MOTION_COVERS_FILE, covers)
            print(f"대표 사진 선택 {len(dead_covers)}개를 지웠습니다.")

        elif kind == "baseline":
            baseline, recorded, dead_baseline = payload
            baseline["event_ids"] = [x for x in recorded if x in live_events]
            _write_json(MOTION_BASELINE_FILE, baseline)
            print(f"기준선에서 {len(dead_baseline)}개를 뺐습니다.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
