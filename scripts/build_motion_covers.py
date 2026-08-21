"""앨범 대표 사진을 미세 모션 클립으로 미리 만든다 (손으로 돌리는 스크립트)

만드는 방법은 backend/services/motion_clips.py 한 곳에 있다. 여기는 무엇을
만들지 고르고, 결과를 저장소에 커밋될 자리(data/motion)에 놓는 껍데기다.
사용자가 Film을 만들 때 서버가 채우는 것도 같은 모듈을 쓴다 — 미리 만든 것과
그때 만든 것이 다르게 생기면 어느 쪽을 보고 있는지 화면에서 구분되지 않는다.

돈이 드는 호출이라 자동으로 돌지 않는다.

    # 무엇을 어떤 프롬프트로 만들지만 본다 (호출 없음, 0원)
    python scripts/build_motion_covers.py E01 --dry-run

    # 한 장으로 룩을 확인한 뒤 (480p 한 건 약 $0.2)
    python scripts/build_motion_covers.py E01 --resolution 480p --keep-source

    # 루프 길이·방식만 바꿔 본다 (호출 없음, 0원)
    python scripts/build_motion_covers.py E01 --from-source --use-seconds 2.5

인물 왜곡을 확실히 막으려면 마스크를 쓴다. data/motion/masks/<media_id>.png에
흰색=원본을 유지할 영역으로 칠해 두면, 생성 결과 위에 원본 픽셀을 다시 덮는다.
그 장면의 라벨에는 "인물은 원본"이 붙는다.

필요한 것: pip install fal-client · ffmpeg(PATH) · .env의 FAL_KEY
TLS를 검사하는 사내망에서는 pip install truststore 도 함께.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import METADATA_DIR, MOTION_DIR, PHOTOS_DIR
from backend.services import motion_clips
from backend.services.motion_clips import LoopOptions

# 정적 데모(VITE_STATIC_MODE)가 보는 자리. mediaUrl()이 /media-files/를
# /mock/photos/로 바꾸므로 같은 파일을 여기에도 둔다.
MOCK_DIR = ROOT_DIR / "frontend" / "public" / "mock" / "photos" / "motion"


def load_metadata() -> tuple[dict, list]:
    events = {
        e["event_id"]: e
        for e in json.loads((METADATA_DIR / "events.json").read_text(encoding="utf-8"))
    }
    media = json.loads((METADATA_DIR / "media.json").read_text(encoding="utf-8"))
    return events, media


def resolve_targets(tokens: list[str], events: dict, media: list) -> list[dict]:
    """E01(추억) 또는 E01_001(사진) 을 모두 받는다

    추억을 주면 그 추억의 대표 사진 한 장만 고른다 — 앨범 표지가 움직이면
    되는 것이고, 모든 사진을 미리 만들 이유도 예산도 없다. 사용자가 Film을
    만들 때는 서버가 나머지를 채운다.
    """
    photos_by_event: dict[str, list[dict]] = {}
    by_id: dict[str, dict] = {}
    for item in media:
        if item.get("type") != "photo":
            continue
        by_id[item["media_id"]] = item
        photos_by_event.setdefault(item["event_id"], []).append(item)

    targets = []
    for token in tokens:
        if token in by_id:
            targets.append(by_id[token])
        elif token in events:
            candidates = photos_by_event.get(token, [])
            if not candidates:
                raise SystemExit(f"{token}: 사진이 없어 표지를 만들 수 없다")
            targets.append(candidates[0])
        else:
            raise SystemExit(f"알 수 없는 id: {token} (추억 E01 또는 사진 E01_001)")
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("ids", nargs="+", help="추억 id(E01) 또는 사진 id(E01_001)")
    parser.add_argument("--resolution", default="480p", choices=list(motion_clips.PRICE))
    parser.add_argument("--seconds", type=int, default=5,
                        help="모델에 요청하는 생성 길이")
    parser.add_argument("--use-seconds", type=float, default=2.0,
                        help="생성 결과에서 앞 몇 초만 쓸지. 뒤로 갈수록 원본에서 "
                             "멀어지므로 기본 2초. 0을 주면 전부 쓴다")
    parser.add_argument("--loop-mode", default="none",
                        choices=("crossfade", "pingpong", "none"),
                        help="none=자르기만(기본) · crossfade=끝을 처음에 겹친다 "
                             "· pingpong=앞뒤로 이어 붙인다")
    parser.add_argument("--crossfade", type=float, default=0.5,
                        help="겹쳐 넘기는 길이(초). 결과는 use-seconds 에서 이만큼 짧아진다")
    parser.add_argument("--keep-source", action="store_true",
                        help="자르기 전 생성 결과를 남긴다 (--from-source 로 다시 쓰려면 필요)")
    parser.add_argument("--from-source", action="store_true",
                        help="남겨 둔 생성 결과로 루프만 다시 만든다. 호출이 없어 0원이다")
    parser.add_argument("--dry-run", action="store_true",
                        help="무엇을 어떤 프롬프트로 만들지만 출력하고 끝낸다")
    parser.add_argument("--yes", action="store_true", help="확인 없이 진행")
    args = parser.parse_args()

    options = LoopOptions(
        resolution=args.resolution,
        seconds=args.seconds,
        use_seconds=args.use_seconds,
        loop_mode=args.loop_mode,
        crossfade=args.crossfade,
        keep_source=args.keep_source or args.from_source,
    )

    events, media = load_metadata()
    plan = []
    for item in resolve_targets(args.ids, events, media):
        event = events[item["event_id"]]
        plan.append({
            "media_id": item["media_id"],
            "photo": PHOTOS_DIR / item["file_name"],
            # 스크립트는 태그를, 서버는 사진 설명·추억 제목을 넘긴다. 고르는
            # 방법은 같다 (motion_clips.motion_prompt).
            "prompt": motion_clips.motion_prompt(
                list(item.get("tags", [])) + list(event.get("tags", []))
            ),
            "mask": (motion_clips.MASKS_DIR / f"{item['media_id']}.png").exists(),
        })

    if options.loop_mode == "crossfade":
        loop_note = f"crossfade {options.crossfade}초 → 루프 {options.use_seconds - options.crossfade:g}초"
    elif options.loop_mode == "pingpong":
        loop_note = f"pingpong → 루프 {options.use_seconds * 2:g}초"
    else:
        loop_note = f"루프 없음 → {options.use_seconds:g}초"

    source_note = "남겨 둔 생성 결과 재사용" if args.from_source else f"{options.seconds}초 생성"
    print(f"\n{options.resolution} · {source_note} · 앞 {options.use_seconds:g}초 사용 · {loop_note}\n")
    for entry in plan:
        missing = "" if entry["photo"].exists() else "  ⚠ 사진 파일 없음"
        masked = "  [마스크 적용]" if entry["mask"] else ""
        generic = "  (움직일 대상을 문구에서 못 찾음)" \
            if entry["prompt"].startswith(motion_clips.FALLBACK_MOTION) else ""
        print(f"  {entry['media_id']}{masked}{missing}{generic}")
        print(f"      {entry['prompt']}")

    if args.from_source:
        print(f"\n{len(plan)}건 · $0.00  (호출 없이 다시 만든다)")
    else:
        # 호출이 실패한 건은 과금되지 않지만, 결과가 마음에 안 들어 다시 뽑는 것은
        # 매번 과금된다 — 실제 비용은 이 금액에 시행착오 횟수를 곱한 값이다.
        cost = len(plan) * motion_clips.PRICE[options.resolution]
        print(f"\n{len(plan)}건 · 예상 ${cost:.2f}  (다시 뽑을 때마다 다시 과금된다)")

    if args.dry_run:
        print("\n--dry-run 이므로 호출하지 않았다.")
        return

    missing = [e["media_id"] for e in plan if not e["photo"].exists()]
    if missing:
        raise SystemExit(f"사진 파일이 없다: {', '.join(missing)}")

    try:
        motion_clips.require_tools()
    except RuntimeError as error:
        raise SystemExit(str(error))

    if not args.from_source:
        try:
            import fal_client  # noqa: F401
        except ImportError:
            raise SystemExit("fal-client가 없다 — pip install fal-client")
        if not os.getenv("FAL_KEY"):
            raise SystemExit("FAL_KEY가 없다 — .env에 FAL_KEY=... 를 넣는다")
        if not args.yes and input("\n진행할까? [y/N] ").strip().lower() != "y":
            print("취소했다.")
            return

    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    manifest = motion_clips.baked_manifest()

    for entry in plan:
        media_id = entry["media_id"]
        source = MOTION_DIR / f"{media_id}.source.mp4"

        if args.from_source:
            if not source.exists():
                print(f"\n[{media_id}] 남겨 둔 원본이 없다: {source.name} — 건너뛴다")
                continue
            print(f"\n[{media_id}] 남겨 둔 원본으로 다시 만든다 (호출 없음)")
        else:
            print(f"\n[{media_id}] 생성 중… (480p 약 40초, 720p 약 2분 30초)")

        try:
            record = motion_clips.build_clip(
                media_id, entry["photo"], entry["prompt"], options, MOTION_DIR,
                source=source if args.from_source else None,
            )
        except Exception as error:  # 공급자·ffmpeg 예외 종류가 제각각이라 넓게 받는다
            print(f"[{media_id}] 실패: {error}")
            if "balance" in str(error).lower() or "locked" in str(error).lower():
                print("        계정 잔액이 비어 있다 — fal.ai/dashboard/billing 에서 충전한다.")
                break
            continue

        clip = MOTION_DIR / f"{media_id}.mp4"
        poster = MOTION_DIR / f"{media_id}.poster.jpg"
        shutil.copy2(str(clip), str(MOCK_DIR / clip.name))
        shutil.copy2(str(poster), str(MOCK_DIR / poster.name))

        manifest[media_id] = record
        motion_clips.write_baked_manifest(manifest)
        print(f"[{media_id}] 완료 → data/motion/{clip.name} "
              f"({clip.stat().st_size // 1024}KB)")

    print("\n확인할 것: 얼굴이 뒤틀린 클립은 지우고 manifest에서 항목을 뺀다.")
    print("항목이 없으면 그 사진은 자동으로 CSS 카메라 움직임으로 돌아간다.")
    if options.keep_source:
        print("루프 길이만 바꿔 보려면 --from-source 로 다시 만든다 (호출 없음, 0원).")


if __name__ == "__main__":
    main()
