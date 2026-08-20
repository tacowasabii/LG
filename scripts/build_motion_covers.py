"""앨범 대표 사진을 미세 모션 클립으로 만든다 (사람이 직접 돌리는 스크립트)

파도가 치고 머리카락이 흔들리는 정도의 움직임만 만든다. 인물의 행동이나 표정은
만들지 않는다 — 없던 몸짓을 붙이는 것은 이 저장소의 진정성 원칙 밖이다.

돈이 드는 호출이라 자동으로 돌지 않는다. 배포에도 들어가지 않는다. 여기서 만든
mp4를 data/motion에 커밋하면, 시드가 그것을 MEDIA_DIR로 옮기고 화면이 재생한다.
클립이 없는 사진은 지금까지처럼 CSS 카메라 움직임만 걸린다.

    # 무엇을 어떤 프롬프트로 만들지 먼저 본다 (호출 없음, 0원)
    python scripts/build_motion_covers.py E01 --dry-run

    # 한 장으로 룩을 확인한 뒤 (480p 한 건 약 $0.2)
    python scripts/build_motion_covers.py E01 --resolution 480p

    # 마음에 들면 프롬프트를 그대로 쓰면서 늘린다
    python scripts/build_motion_covers.py E02 E05 E07 --resolution 720p

인물 왜곡을 확실히 막으려면 마스크를 쓴다. data/motion/masks/<media_id>.png에
흰색=원본을 유지할 영역으로 칠해 두면, 생성 결과 위에 원본 픽셀을 다시 덮는다.
그 장면의 라벨에는 "인물은 원본"이 붙는다.

필요한 것: pip install fal-client · ffmpeg(PATH) · .env의 FAL_KEY
TLS를 검사하는 사내망에서는 pip install truststore 도 함께 (trust_os_certificates 참고).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import METADATA_DIR, MOTION_DIR, MOTION_MANIFEST_FILE, PHOTOS_DIR

MODEL = "fal-ai/wan/v2.2-a14b/image-to-video"

# fal이 초를 16fps 기준으로 센다
SOURCE_FPS = 16

# 클립 한 건 가격 (USD). 공급자가 바꿀 수 있으니 대시보드에서 확인하고 맞춘다.
PRICE = {"480p": 0.20, "580p": 0.30, "720p": 0.40}

# 화면에서 서빙되는 자리. mediaUrl()이 STATIC_MODE에서 /media-files/를
# /mock/photos/로 바꾸므로, 아래 MOCK_DIR에 같은 파일을 두면 정적 데모도 돈다.
SERVE_PREFIX = "/media-files/motion"
MOCK_DIR = ROOT_DIR / "frontend" / "public" / "mock" / "photos" / "motion"

MASKS_DIR = MOTION_DIR / "masks"

# 태그에서 고르는 환경 모션. 사람의 행동은 넣지 않는다.
MOTION_BY_TAG = {
    "바다": "gentle ocean waves lapping the shore, soft sea breeze",
    "해수욕장": "gentle ocean waves rolling in, sea breeze moving hair slightly",
    "산": "leaves rustling in a light breeze, clouds drifting slowly",
    "계곡": "clear water flowing over stones",
    "눈": "soft snow falling gently",
    "벚꽃": "cherry blossom petals drifting down slowly",
    "생일": "candle flames flickering softly",
    "케이크": "candle flames flickering softly",
    "모닥불": "campfire flames flickering, embers drifting upward slowly",
    "바람": "light wind moving hair and fabric",
}
FALLBACK_MOTION = "very subtle ambient air movement, hair and fabric shifting slightly"

NEGATIVE_PROMPT = (
    "camera movement, zoom, pan, morphing face, distorted face, "
    "changing facial features, warping, extra limbs, text, watermark"
)


def load_metadata() -> tuple[dict, list]:
    events = {
        e["event_id"]: e
        for e in json.loads((METADATA_DIR / "events.json").read_text(encoding="utf-8"))
    }
    media = json.loads((METADATA_DIR / "media.json").read_text(encoding="utf-8"))
    return events, media


def resolve_targets(tokens: list[str], events: dict, media: list) -> list[dict]:
    """E01(사건) 또는 E01_001(사진) 을 모두 받는다

    사건을 주면 그 사건의 대표 사진 한 장만 고른다 — 앨범 표지가 움직이면
    되는 것이고, 모든 사진을 움직이게 만들 이유도 예산도 없다.
    """
    photos_by_event: dict[str, list[dict]] = {}
    by_id: dict[str, dict] = {}
    for m in media:
        if m.get("type") != "photo":
            continue
        by_id[m["media_id"]] = m
        photos_by_event.setdefault(m["event_id"], []).append(m)

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
            raise SystemExit(f"알 수 없는 id: {token} (사건 E01 또는 사진 E01_001)")
    return targets


def build_prompt(item: dict, event: dict) -> str:
    """사진·사건의 태그에서 환경 모션을 고른다

    LLM에 맡기지 않는다. 대상이 열 건 남짓이고, 무엇이 움직이는지는 만드는
    사람이 알고 정해야 하는 것이다 — 여기서 지어내면 확인할 수가 없다.
    """
    tags = list(item.get("tags", [])) + list(event.get("tags", []))
    for tag in tags:
        if tag in MOTION_BY_TAG:
            return f"{MOTION_BY_TAG[tag]}, static camera, everything else perfectly still"
    return f"{FALLBACK_MOTION}, static camera, everything else perfectly still"


def video_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    width, height = out.split("x")[:2]
    return int(width), int(height)


def restore_subject(clip: Path, photo: Path, mask: Path, dest: Path) -> None:
    """마스크가 흰 영역을 원본 픽셀로 되돌린다

    얼굴이 미묘하게 다른 사람이 되는 것을 확률이 아니라 구조로 막는다. 원본을
    그대로 덮으므로 그 영역은 변할 수가 없다. 경계는 살짝 흐려서 이어 붙인
    자리가 드러나지 않게 한다.
    """
    width, height = video_size(clip)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(clip), "-i", str(photo), "-i", str(mask),
        "-filter_complex",
        f"[1:v]scale={width}:{height}[orig];"
        f"[2:v]scale={width}:{height},boxblur=4:1[msk];"
        f"[orig][msk]alphamerge[fg];[0:v][fg]overlay[out]",
        "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest),
    ], check=True, capture_output=True)


def pingpong(src: Path, dest: Path, seconds: float = 0.0) -> None:
    """앞으로 한 번, 뒤로 한 번 이어 붙여 끊기지 않는 루프를 만든다

    모델에 같은 시작·끝 프레임을 줘서 루프를 만드는 방법은 쓰지 않는다. 대부분의
    모델이 그 입력에는 움직임을 거의 만들지 않아서, 루프를 얻으려다 정지 화면을
    받는다. 미세한 환경 움직임은 거꾸로 재생해도 티가 나지 않는다 — 파도는
    역재생해도 파도다. trim은 이음새에서 같은 프레임이 두 번 나오는 것을 막는다.

    seconds를 주면 앞부분만 쓴다. 생성 모델은 시간이 갈수록 원본에서 멀어져서,
    5초를 그대로 쓰면 끝에서 얼굴이 다른 사람이 되고 배경 인물이 사라진다.
    앞 2초는 원본과 거의 같다. 가격은 생성 건당이라 5초를 뽑아 앞부분만 써도
    더 들지 않는다.
    """
    head = f"trim=duration={seconds},setpts=PTS-STARTPTS," if seconds else ""
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src), "-filter_complex",
        f"[0:v]{head}split[a][b];[b]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[r];"
        "[a][r]concat=n=2:v=1[out]",
        "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        # 메타데이터를 파일 앞으로. 없으면 브라우저가 전체를 받아야 재생을 시작한다.
        "-movflags", "+faststart", str(dest),
    ], check=True, capture_output=True)


def crossfade_loop(src: Path, dest: Path, seconds: float, fade: float) -> None:
    """끝을 처음에 겹쳐 넘겨 이음새 없는 루프를 만든다 (역재생 없음)

    핑퐁은 역재생 구간이 눈에 띈다. 파도가 밀려 나가는 것도 그렇지만 결정적인
    것은 줌이다 — 모델이 프롬프트를 무시하고 넣는 줌 인이 역방향에서 줌 아웃이
    되어, 화면이 숨쉬듯 커졌다 작아진다.

    대신 클립의 꼬리를 머리에 디졸브로 겹친다. 결과의 처음과 끝이 같은 프레임
    (원본 fade 지점)이라 다시 시작할 때 튀지 않고, 방향이 한쪽뿐이라 파도가
    거꾸로 가지 않는다. 대가는 길이다 — 결과는 seconds - fade 가 된다.
    """
    body = seconds - fade
    if body <= fade:
        raise SystemExit(
            f"--use-seconds({seconds})가 --crossfade({fade})의 두 배보다 커야 한다"
        )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src), "-filter_complex",
        # 머리(0~fade)와 그 뒤(fade~seconds)로 나눈 다음,
        # 뒤쪽을 끝까지 보여주다가 마지막 fade 구간에서 머리로 넘긴다.
        f"[0:v]trim=start={fade}:duration={body},setpts=PTS-STARTPTS[main];"
        f"[0:v]trim=duration={fade},setpts=PTS-STARTPTS[head];"
        f"[main][head]xfade=transition=fade:duration={fade}:offset={body - fade}[out]",
        "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(dest),
    ], check=True, capture_output=True)


def trim_only(src: Path, dest: Path, seconds: float) -> None:
    """루프 처리 없이 앞부분만 잘라 낸다 (--loop-mode none)"""
    args = ["ffmpeg", "-y", "-i", str(src)]
    if seconds:
        args += ["-t", str(seconds)]
    args += ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(dest)]
    subprocess.run(args, check=True, capture_output=True)


def make_loop(src: Path, dest: Path, options) -> None:
    """고른 방식으로 루프를 만든다"""
    if options.loop_mode == "crossfade":
        crossfade_loop(src, dest, seconds=options.use_seconds, fade=options.crossfade)
    elif options.loop_mode == "pingpong":
        pingpong(src, dest, seconds=options.use_seconds)
    else:
        trim_only(src, dest, seconds=options.use_seconds)


def first_frame(src: Path, dest: Path) -> None:
    """poster용 첫 프레임. 자동재생이 막힌 환경에서 이것이 보인다."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dest)],
        check=True, capture_output=True,
    )


def read_manifest() -> dict:
    try:
        return json.loads(MOTION_MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_manifest(manifest: dict) -> None:
    MOTION_MANIFEST_FILE.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def finish(entry: dict, raw: Path, options, manifest: dict) -> None:
    """생성 결과 하나를 클립·poster·manifest 항목으로 마무리한다

    생성과 분리해 둔다. 자르는 길이나 루프 방식만 바꿔 보는 일이 잦고, 그때마다
    돈을 다시 쓸 이유가 없다 (--keep-source 로 남긴 원본 + --from-source).
    """
    media_id = entry["media_id"]

    source = raw
    if entry["mask"]:
        print(f"[{media_id}] 인물 영역을 원본으로 되돌린다")
        masked = MOTION_DIR / f"{media_id}.masked.mp4"
        restore_subject(raw, entry["photo"], entry["mask"], masked)
        source = masked

    clip = MOTION_DIR / f"{media_id}.mp4"
    poster = MOTION_DIR / f"{media_id}.poster.jpg"
    make_loop(source, clip, options)
    first_frame(source, poster)

    if source is not raw:
        source.unlink(missing_ok=True)
    if not (options.keep_source or options.from_source):
        raw.unlink(missing_ok=True)

    # 정적 데모(VITE_STATIC_MODE)도 같은 파일을 보게 복사해 둔다
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(clip), str(MOCK_DIR / clip.name))
    shutil.copy2(str(poster), str(MOCK_DIR / poster.name))

    manifest[media_id] = {
        "file": f"{SERVE_PREFIX}/{clip.name}",
        "poster": f"{SERVE_PREFIX}/{poster.name}",
        "model": MODEL,
        "prompt": entry["prompt"],
        "resolution": options.resolution,
        "source_seconds": options.seconds,
        # 생성 결과에서 실제로 쓴 앞부분 길이 (0이면 전부)
        "used_seconds": options.use_seconds,
        # 루프를 어떻게 만들었는지. crossfade면 결과가 그만큼 짧아진다.
        "loop": options.loop_mode,
        "crossfade": options.crossfade if options.loop_mode == "crossfade" else None,
        # 화면의 AI 라벨이 이 값을 보고 "인물은 원본"을 붙인다
        "subject_preserved": bool(entry["mask"]),
    }
    write_manifest(manifest)
    print(f"[{media_id}] 완료 → data/motion/{clip.name} "
          f"({clip.stat().st_size // 1024}KB)")


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool}이 PATH에 없다 — winget install Gyan.FFmpeg")


def trust_os_certificates() -> None:
    """OS 인증서 저장소를 쓰게 한다

    TLS를 검사하는 사내망에서는 그 루트 CA가 Python의 certifi 번들에 없어서
    호출이 CERTIFICATE_VERIFY_FAILED로 끊긴다. 관리되는 PC의 Windows 저장소에는
    그 CA가 이미 있으므로 저장소를 바꿔 끼우면 통한다. 검증을 끄는 것이 아니다.

    truststore가 없으면 그냥 넘어간다 — 검사가 없는 망에서는 필요하지 않다.
    """
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("ids", nargs="+", help="사건 id(E01) 또는 사진 id(E01_001)")
    parser.add_argument("--resolution", default="480p", choices=list(PRICE))
    parser.add_argument("--seconds", type=int, default=5,
                        help="모델에 요청하는 생성 길이")
    parser.add_argument("--use-seconds", type=float, default=2.0,
                        help="생성 결과에서 앞 몇 초만 쓸지. 뒤로 갈수록 원본에서 "
                             "멀어지므로 기본 2초. 0을 주면 전부 쓴다. "
                             "최종 루프는 이 값의 두 배가 된다")
    parser.add_argument("--keep-source", action="store_true",
                        help="자르기 전 생성 결과를 남긴다 (--from-source 로 다시 쓰려면 필요)")
    parser.add_argument("--from-source", action="store_true",
                        help="남겨 둔 생성 결과로 루프만 다시 만든다. 호출이 없어 0원이다")
    parser.add_argument("--loop-mode", default="crossfade",
                        choices=("crossfade", "pingpong", "none"),
                        help="crossfade=끝을 처음에 겹쳐 넘긴다(기본, 역재생 없음) · "
                             "pingpong=앞뒤로 이어 붙인다(역재생이 보인다) · none=자르기만")
    parser.add_argument("--crossfade", type=float, default=0.5,
                        help="겹쳐 넘기는 길이(초). 결과는 use-seconds 에서 이만큼 짧아진다")
    parser.add_argument("--dry-run", action="store_true",
                        help="무엇을 어떤 프롬프트로 만들지만 출력하고 끝낸다")
    parser.add_argument("--yes", action="store_true", help="확인 없이 진행")
    parser.add_argument("--no-negative-prompt", action="store_true",
                        help="모델이 negative_prompt를 받지 않을 때 쓴다")
    parser.add_argument("--upload-cdn", action="store_true",
                        help="사진을 fal CDN에 올려 URL로 넘긴다 (기본은 data URI)")
    args = parser.parse_args()

    events, media = load_metadata()
    targets = resolve_targets(args.ids, events, media)

    plan = []
    for item in targets:
        event = events[item["event_id"]]
        mask = MASKS_DIR / f"{item['media_id']}.png"
        plan.append({
            "media_id": item["media_id"],
            "photo": PHOTOS_DIR / item["file_name"],
            "prompt": build_prompt(item, event),
            "mask": mask if mask.exists() else None,
        })

    if args.loop_mode == "crossfade":
        loop_note = f"crossfade {args.crossfade}초 → 루프 {args.use_seconds - args.crossfade:g}초"
    elif args.loop_mode == "pingpong":
        loop_note = f"pingpong → 루프 {args.use_seconds * 2:g}초"
    else:
        loop_note = "루프 없음"

    source_note = "남겨 둔 생성 결과 재사용" if args.from_source else f"{args.seconds}초 생성"
    print(f"\n{args.resolution} · {source_note} · 앞 {args.use_seconds:g}초 사용 · {loop_note}\n")
    for entry in plan:
        missing = "" if entry["photo"].exists() else "  ⚠ 사진 파일 없음"
        masked = "  [마스크 적용]" if entry["mask"] else ""
        print(f"  {entry['media_id']}{masked}{missing}")
        print(f"      {entry['prompt']}")

    if args.from_source:
        print(f"\n{len(plan)}건 · $0.00  (호출 없이 다시 만든다)")
    else:
        # 호출이 실패한 건은 과금되지 않지만, 결과가 마음에 안 들어 다시 뽑는 것은
        # 매번 과금된다 — 실제 비용은 이 금액에 시행착오 횟수를 곱한 값이다.
        print(f"\n{len(plan)}건 · 예상 ${len(plan) * PRICE[args.resolution]:.2f}"
              "  (다시 뽑을 때마다 다시 과금된다)")

    if args.dry_run:
        print("\n--dry-run 이므로 호출하지 않았다.")
        return

    missing = [e["media_id"] for e in plan if not e["photo"].exists()]
    if missing:
        raise SystemExit(f"사진 파일이 없다: {', '.join(missing)}")

    require_tools()

    # 다시 만들기만 할 때는 네트워크도 키도 필요하지 않다.
    fal_client = None
    if not args.from_source:
        trust_os_certificates()
        try:
            import fal_client
        except ImportError:
            raise SystemExit("fal-client가 없다 — pip install fal-client")

        # backend.config가 load_dotenv로 .env를 이미 읽었다. 그래도 없으면 키가 없는 것이다.
        if not os.getenv("FAL_KEY"):
            raise SystemExit("FAL_KEY가 없다 — .env에 FAL_KEY=... 를 넣는다")

        if not args.yes:
            answer = input("\n진행할까? [y/N] ").strip().lower()
            if answer != "y":
                print("취소했다.")
                return

    MOTION_DIR.mkdir(parents=True, exist_ok=True)
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest()

    for entry in plan:
        media_id = entry["media_id"]
        raw = MOTION_DIR / f"{media_id}.source.mp4"

        if args.from_source:
            # 이미 받아 둔 생성 결과로 루프만 다시 만든다. 호출이 없으니 0원이다.
            if not raw.exists():
                print(f"\n[{media_id}] 남겨 둔 원본이 없다: {raw.name} — 건너뛴다")
                continue
            print(f"\n[{media_id}] 남겨 둔 원본으로 다시 만든다 (호출 없음)")
            finish(entry, raw, args, manifest)
            continue

        if args.upload_cdn:
            print(f"\n[{media_id}] 사진을 fal CDN에 업로드…")
            image_url = fal_client.upload_file(str(entry["photo"]))
        else:
            # 사진을 data URI로 요청에 실어 보낸다. CDN 업로드(rest.fal.ai/storage)를
            # 거치지 않는 편이 두 가지로 낫다.
            #   - 사내 웹 필터가 그 주소를 막는 환경에서도 호출이 성립한다
            #   - 가족 사진이 별도 주소로 CDN에 남지 않는다 (추론에는 여전히 올라간다)
            # 이 데이터셋은 한 장이 1MB 미만이라 요청에 실어도 문제가 없다.
            print(f"\n[{media_id}] 사진을 요청에 실어 보낸다 (data URI)")
            image_url = fal_client.encode_file(str(entry["photo"]))

        arguments = {
            "image_url": image_url,
            "prompt": entry["prompt"],
            "resolution": args.resolution,
            "num_frames": args.seconds * SOURCE_FPS,
            "frames_per_second": SOURCE_FPS,
        }
        if not args.no_negative_prompt:
            arguments["negative_prompt"] = NEGATIVE_PROMPT

        print(f"[{media_id}] 생성 중… (480p 약 40초, 720p 약 2분 30초)")
        try:
            result = fal_client.subscribe(MODEL, arguments=arguments)
        except Exception as error:  # 공급자 예외 종류가 버전마다 달라 넓게 받는다
            print(f"[{media_id}] 실패: {error}")
            message = str(error).lower()
            if "balance" in message or "locked" in message:
                # 잔액이 0이면 계정이 잠긴다. 여기서 재시도해도 같은 답이 온다.
                print("        계정 잔액이 비어 있다 — fal.ai/dashboard/billing 에서 충전한다.")
                break
            print("        입력 파라미터를 거부했다면 --no-negative-prompt 로 다시 시도한다.")
            continue

        urllib.request.urlretrieve(result["video"]["url"], raw)
        finish(entry, raw, args, manifest)

    print("\n확인할 것: 얼굴이 뒤틀린 클립은 지우고 manifest에서 항목을 뺀다.")
    print("항목이 없으면 그 사진은 자동으로 CSS 카메라 움직임으로 돌아간다.")
    if args.keep_source:
        print("루프 길이만 바꿔 보려면 --from-source 로 다시 만든다 (호출 없음, 0원).")


if __name__ == "__main__":
    main()
