"""Memory Film을 하나의 mp4로 굽는다 (사람이 직접 돌리는 스크립트)

    python scripts/render_film.py E01                    # 45초 · 성인
    python scripts/render_film.py E01 --length 30 --audience elder
    python scripts/render_film.py E01 --dry-run          # 계획만 본다 (인코딩 없음)
    python scripts/render_film.py --all                  # 추억 전부

화면의 Memory Film은 장면을 넘겨 보여 주는 미리보기였다. 내려받을 파일이 없어서
가족에게 보낼 수도, TV에 넣을 수도 없었다.

── 왜 브라우저 녹화가 아니라 ffmpeg인가

canvas + MediaRecorder로 하면 45초 영상을 만드는 데 45초가 걸리고(실시간), 결과가
webm이라 아이폰 사파리에서 재생되지 않는다. ffmpeg는 실시간보다 빠르고 h264 mp4를
낸다. 이 저장소는 이미 ffmpeg를 전제로 쓰고 있다 (scripts/build_motion_covers.py).

── 소리에 대해 (정직하게)

이 파일의 소리는 **가족이 실제로 남긴 목소리**뿐이다.

내레이션은 넣지 못한다. 화면의 낭독은 브라우저 speechSynthesis가 재생 시점에
만드는 것이라 파일이 없고, 서버 TTS(Amazon Polly)는 이 망의 프록시가 막는다
(403). 그래서 내레이션은 **첫 화면에 글로** 넣는다 — 소리로 못 들려주는 것을
없는 것처럼 두지 않는다.

배경 음악도 넣지 못한다. 화면의 음악은 Web Audio가 그때 합성하는 것이고
(frontend/src/lib/filmMusic.ts) 음원 파일이 없다. 서버에서 다시 만들면 화면에서
들리는 것과 다른 소리가 되므로, 없는 편이 낫다.

목소리가 없는 추억은 소리 없는 영상이 된다. 자막으로 읽힌다.

── 진정성 원칙은 파일 안에서도 지킨다

장면마다 원본 출처와 적용된 효과를 자막으로 굽는다. 화면에서만 밝히고 파일에서
빼면, 파일이 가족 밖으로 나갈 때 그 구분이 사라진다.

  원본 그대로 / AI 효과 · 느린 줌 인 / AI 생성 미세 움직임

카메라 움직임은 ffmpeg zoompan으로 만든다. 서버가 정한 motion 값(zoom-in ·
pan-left · zoom-out · pan-right)을 그대로 옮긴다 — CSS와 다른 것을 걸면 화면과
파일이 갈린다.

필요한 것: ffmpeg(PATH). LLM 키가 있으면 내레이션이 모델 문장이 된다.
"""

import argparse
import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import MEDIA_DIR, STATE_DIR  # noqa: E402
from backend.services import film_composer  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402
from backend.models.graph_models import NodeType  # noqa: E402

OUT_DIR = STATE_DIR / "films"

# 1280x720. 가족에게 보내는 파일이라 용량과 화질의 균형을 여기서 잡는다.
W, H = 1280, 720
FPS = 30

# 카메라 움직임의 폭. index.css의 kenburns와 같은 값을 쓴다 (scale 1 -> 1.12).
ZOOM_MAX = 1.12
PAN_SHIFT = 0.025  # 화면 폭의 2.5%

# 자막 폰트. drawtext는 폰트를 스스로 찾지 못한다 (윈도우에는 fontconfig가 없어
# "Cannot load default config file"로 장면이 통째로 실패했다). 한글이 나오는
# 폰트를 직접 지정한다.
FONT_CANDIDATES = (
    "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕 (윈도우 기본 한글)
    "C:/Windows/Fonts/gulim.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
)


def find_font() -> str | None:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


FONT = find_font()


def media_path(serve_path: str) -> Path | None:
    """/media-files/... 를 디스크 경로로"""
    name = Path(serve_path or "").name
    if not name:
        return None
    # 모션 클립은 MEDIA_DIR/motion 아래에 있다
    for candidate in (MEDIA_DIR / name, MEDIA_DIR / "motion" / name):
        if candidate.exists():
            return candidate
    return None


def effect_label(scene: dict) -> str:
    effects = scene.get("ai_effects") or []
    return " · ".join(effects) if effects else "원본 그대로"


def zoompan(motion: str | None, seconds: float) -> str:
    """서버가 정한 카메라 움직임을 ffmpeg zoompan 식으로

    화면(index.css)과 같은 값을 쓴다. 다른 것을 걸면 "적용된 효과를 드러낸다"는
    원칙이 파일에서 깨진다 — 자막은 줌 인이라 적고 화면은 패닝하는 일이 된다.
    """
    frames = max(1, int(seconds * FPS))
    if motion == "zoom-in":
        z = f"1+{ZOOM_MAX - 1:.3f}*on/{frames}"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "zoom-out":
        z = f"{ZOOM_MAX:.3f}-{ZOOM_MAX - 1:.3f}*on/{frames}"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion in ("pan-left", "pan-right"):
        z = "1.10"
        sign = "-" if motion == "pan-left" else "+"
        x = f"iw/2-(iw/zoom/2){sign}{PAN_SHIFT}*iw*(on/{frames}-0.5)*2"
        y = "ih/2-(ih/zoom/2)"
    else:
        # 움직임 없음 — 그래도 zoompan을 태워 프레임 수를 맞춘다
        z, x, y = "1", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"

    return (
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS}"
    )


def escape_text(text: str) -> str:
    """drawtext에 넣을 문자열 이스케이프"""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "’")
        .replace("%", "\\%")
    )


def drawtext(text: str, y: str, size: int, alpha: float = 1.0) -> str:
    # 필터 문법에서 드라이브 문자의 콜론을 이스케이프해야 한다 (C\:/...)
    font = f":fontfile='{FONT.replace(':', chr(92) + ':')}'" if FONT else ""
    return (
        f"drawtext=text='{escape_text(text)}'{font}:fontcolor=white@{alpha}"
        f":fontsize={size}:x=(w-text_w)/2:y={y}"
        f":box=1:boxcolor=black@0.45:boxborderw=14"
    )


def build_scene(scene: dict, index: int, work: Path) -> Path | None:
    """장면 하나를 mp4 조각으로 만든다"""
    seconds = float(scene.get("duration_sec") or 8)
    out = work / f"scene{index:02d}.mp4"

    clip = media_path(scene.get("motion_url") or "")
    original = media_path(scene.get("file_path") or "")
    still = clip is None and (original is None or original.suffix.lower() != ".mp4")
    source = original if clip is None else clip

    if source is None:
        print(f"  장면 {index}: 파일이 없어 건너뜁니다 ({scene.get('media_id')})")
        return None

    subtitle = scene.get("subtitle") or ""
    footer = f"{scene.get('source_label') or ''}   ·   {effect_label(scene)}"

    overlays = ",".join([
        drawtext(subtitle, "h-th-120", 40),
        drawtext(footer, "h-th-60", 24, 0.85),
    ])

    if still:
        # 사진 — zoompan으로 카메라 움직임을 만든다
        chain = (
            f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,"
            f"crop={W * 2}:{H * 2},"
            f"{zoompan(scene.get('motion'), seconds)},"
            f"{overlays}"
        )
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(source),
            "-t", f"{seconds}", "-vf", chain,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            str(out),
        ]
    else:
        # 영상·생성 클립 — 손대지 않고 길이만 맞춘다 (짧으면 이어 붙인다)
        chain = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,{overlays}"
        )
        cmd = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(source),
            "-t", f"{seconds}", "-vf", chain,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-an", str(out),
        ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"  장면 {index} 실패:\n{result.stderr.decode(errors='replace')[-500:]}")
        return None
    return out


def build_title(board: dict, work: Path) -> Path | None:
    """첫 화면 — 제목과 내레이션을 글로 넣는다

    내레이션을 소리로 넣을 수 없으므로(위 머리말) 여기서 읽히게 한다.
    """
    seconds = 6.0
    out = work / "scene_title.mp4"
    narration = (board.get("narration") or "").strip()
    # 한 줄이 길면 읽히지 않는다. 대충 30자에서 끊는다.
    lines, current = [], ""
    for word in narration.split():
        if len(current) + len(word) > 30:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    lines = lines[:5]

    overlays = [drawtext(board.get("title") or "우리 가족의 기억", "h/2-200", 56)]
    if board.get("subtitle"):
        overlays.append(drawtext(board["subtitle"], "h/2-120", 30, 0.8))
    for i, line in enumerate(lines):
        overlays.append(drawtext(line, f"h/2-20+{i * 52}", 30, 0.9))

    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x0E0D0B:s={W}x{H}:d={seconds}:r={FPS}",
        "-vf", ",".join(overlays),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"  첫 화면 실패:\n{result.stderr.decode(errors='replace')[-400:]}")
        return None
    return out


def voice_tracks(board: dict) -> list[Path]:
    """장면에 붙은 가족 목소리 파일들 (순서대로)"""
    paths = []
    for scene in board["scenes"]:
        vid = scene.get("voice_id")
        if not vid:
            continue
        node = graph_manager.get_node(vid)
        if not node or node.get("node_type") != NodeType.MEDIA:
            continue
        path = media_path(node.get("file_path", ""))
        if path:
            paths.append(path)
    return paths


def render(event_id: str, length: int, audience: str, dry_run: bool) -> Path | None:
    board = asyncio.run(film_composer.compose(event_id, length, audience))
    if not board:
        print(f"{event_id}: 이야기를 만들 수 없습니다 (사진·영상이 없습니다)")
        return None

    voices = voice_tracks(board)
    print(f"\n{event_id} · {board['title']}")
    print(f"  장면 {len(board['scenes'])}개 · {board['total_sec']}초 · 대상 {audience}")
    for i, scene in enumerate(board["scenes"], 1):
        kind = "생성클립" if scene.get("motion_url") else (
            "영상" if (scene.get("file_path") or "").endswith(".mp4") else "사진"
        )
        print(f"    {i}. [{kind}] {scene['duration_sec']}초 · {effect_label(scene)}")
    print(f"  가족 목소리 {len(voices)}개" + ("" if voices else " — 소리 없는 영상이 됩니다"))

    if dry_run:
        return None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{event_id}-{length}s-{audience}.mp4"

    with tempfile.TemporaryDirectory(prefix="film_") as tmp:
        work = Path(tmp)
        parts = []
        title = build_title(board, work)
        if title:
            parts.append(title)
        for i, scene in enumerate(board["scenes"], 1):
            part = build_scene(scene, i, work)
            if part:
                parts.append(part)

        if not parts:
            print("  만들 장면이 없습니다.")
            return None

        listing = work / "parts.txt"
        listing.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8"
        )

        silent = work / "silent.mp4"
        concat = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", str(silent)],
            capture_output=True,
        )
        if concat.returncode != 0:
            print(f"  이어 붙이기 실패:\n{concat.stderr.decode(errors='replace')[-500:]}")
            return None

        if not voices:
            shutil.copy2(silent, out)
        else:
            # 목소리를 순서대로 이어 하나의 트랙으로 만들고 영상에 얹는다.
            # 영상보다 짧으면 뒤는 조용하다 (없는 소리를 늘리지 않는다).
            vlist = work / "voices.txt"
            vlist.write_text(
                "".join(f"file '{p.as_posix()}'\n" for p in voices), encoding="utf-8"
            )
            track = work / "voice.m4a"
            va = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(vlist),
                 "-c:a", "aac", "-b:a", "128k", str(track)],
                capture_output=True,
            )
            if va.returncode != 0:
                print("  목소리를 이어 붙이지 못해 소리 없이 만듭니다.")
                shutil.copy2(silent, out)
            else:
                mux = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(silent), "-i", str(track),
                     "-c:v", "copy", "-c:a", "aac", "-shortest" if False else "-map",
                     "0:v:0", "-map", "1:a:0", str(out)],
                    capture_output=True,
                )
                if mux.returncode != 0:
                    print(f"  소리 얹기 실패:\n{mux.stderr.decode(errors='replace')[-400:]}")
                    shutil.copy2(silent, out)

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"  -> {out} ({size_mb:.1f}MB)")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Memory Film을 mp4로 굽는다")
    parser.add_argument("events", nargs="*", help="추억 id (예: E01)")
    parser.add_argument("--all", action="store_true", help="추억 전부")
    parser.add_argument("--length", type=int, default=45, choices=(30, 45, 60))
    parser.add_argument("--audience", default="adult", choices=("child", "adult", "elder"))
    parser.add_argument("--dry-run", action="store_true", help="계획만 본다")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg가 없습니다. winget install Gyan.FFmpeg 로 넣으세요.")
        return 1

    if not FONT:
        print("자막에 쓸 한글 폰트를 찾지 못했습니다. FONT_CANDIDATES를 확인하세요.")
        return 1

    targets = [e["id"] for e in graph_manager.get_events()] if args.all else args.events
    if not targets:
        print("추억 id를 주세요 (또는 --all). 예: python scripts/render_film.py E01")
        return 1

    made = 0
    for event_id in targets:
        if render(event_id, args.length, args.audience, args.dry_run):
            made += 1

    if not args.dry_run:
        print(f"\n{made}/{len(targets)}개를 만들었습니다. 위치: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
