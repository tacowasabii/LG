"""미세 모션 클립 — 만들기와 찾기 (Memory Film)

파도가 치거나 불꽃이 깜빡이는 정도의 움직임만 만든다. 인물의 행동이나 표정은
만들지 않는다 — 없던 몸짓을 붙이는 것은 이 저장소의 진정성 원칙 밖이다.

부르는 곳이 둘이다.

  scripts/build_motion_covers.py  손으로 미리 만들어 저장소에 커밋한다
  film_composer                   사용자가 Film을 만들 때 없는 것을 채운다

만드는 방법은 여기 한 곳에만 둔다. 두 경로가 각자 만들면 미리 만든 것과 그때
만든 것이 다르게 생기고, 어느 쪽을 보고 있는지 화면에서 구분되지 않는다.

클립은 두 자리에 산다.

  data/motion/          커밋된 읽기 전용 자산. 시드가 서빙 자리로 복사한다
  STATE_DIR/            런타임에 만든 것. 배포에서는 볼륨이라 재배포에도 남는다

찾을 때는 둘을 합쳐 보고, 같은 사진이 양쪽에 있으면 런타임 쪽을 쓴다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from backend.config import (
    MEDIA_DIR,
    MOTION_AUTOGEN,
    MOTION_AUTOGEN_MAX,
    MOTION_CROSSFADE,
    MOTION_DIR,
    MOTION_LEDGER_FILE,
    MOTION_LOOP_MODE,
    MOTION_MANIFEST_FILE,
    MOTION_RESOLUTION,
    MOTION_RUNTIME_MANIFEST_FILE,
    MOTION_SOURCE_SECONDS,
    MOTION_USE_SECONDS,
)

MODEL = "fal-ai/wan/v2.2-a14b/image-to-video"

# fal이 초를 16fps 기준으로 센다
SOURCE_FPS = 16

# 클립 한 건 가격 (USD). 공급자가 바꿀 수 있으니 대시보드에서 확인하고 맞춘다.
PRICE = {"480p": 0.20, "580p": 0.30, "720p": 0.40}

# 화면에서 서빙되는 자리. mediaUrl()이 STATIC_MODE에서 /media-files/를
# /mock/photos/로 바꾸므로, 같은 파일을 그쪽에 두면 정적 데모도 돈다.
SERVE_PREFIX = "/media-files/motion"

# 서빙되는 실제 디렉터리. 미리 만든 것도 시드가 여기로 옮긴다.
SERVE_DIR = MEDIA_DIR / "motion"

# 손으로 그린 마스크. 있으면 그 영역을 원본 픽셀로 되돌린다.
MASKS_DIR = MOTION_DIR / "masks"

# 무엇이 움직이는지 고르는 말. 사람의 행동은 넣지 않는다.
# 열쇠는 한국어다 — 태그·사진 설명·사건 제목·장소 이름에서 그대로 찾는다.
MOTION_BY_WORD = {
    "해수욕장": "gentle ocean waves rolling in, sea breeze moving hair slightly",
    "바다": "gentle ocean waves lapping the shore, soft sea breeze",
    "해변": "gentle ocean waves lapping the shore, soft sea breeze",
    "물놀이": "shallow water rippling gently",
    "계곡": "clear water flowing over stones",
    "모닥불": "campfire flames flickering, embers drifting upward slowly",
    "촛불": "candle flames flickering softly",
    "케이크": "candle flames flickering softly",
    "생일": "candle flames flickering softly",
    "눈": "soft snow falling gently",
    "벚꽃": "cherry blossom petals drifting down slowly",
    "단풍": "leaves rustling in a light breeze",
    "산": "leaves rustling in a light breeze, clouds drifting slowly",
    "바람": "light wind moving hair and fabric",
}
FALLBACK_MOTION = "very subtle ambient air movement, hair and fabric shifting slightly"

NEGATIVE_PROMPT = (
    "camera movement, zoom, pan, morphing face, distorted face, "
    "changing facial features, warping, extra limbs, text, watermark"
)


@dataclass
class LoopOptions:
    """생성 결과를 어떻게 잘라 루프로 만들지

    기본값이 지금 저장소에 들어 있는 클립을 만든 설정이다. 왜 이 값인지는
    README의 "미세 모션 클립" 절에 적어 두었다 — 요약하면 뒤로 갈수록 원본에서
    멀어지므로 앞부분만 쓰고, 루프는 방식마다 다른 대가가 있다.
    """
    resolution: str = MOTION_RESOLUTION
    seconds: int = MOTION_SOURCE_SECONDS
    use_seconds: float = MOTION_USE_SECONDS
    loop_mode: str = MOTION_LOOP_MODE
    crossfade: float = MOTION_CROSSFADE
    keep_source: bool = False


# --- 무엇이 움직일지 고르기 -------------------------------------------------

def motion_prompt(texts: Iterable[Optional[str]]) -> str:
    """주어진 문구들에서 환경 모션을 고른다

    LLM에 맡기지 않는다. 무엇이 움직이는지는 만드는 사람이 알고 정해야 하는
    것이고, 모델이 매번 다르게 지어내면 같은 사진이 다르게 움직인다.

    스크립트는 태그를, 서버는 사진 설명·사건 제목·장소 이름을 넘긴다. 어느
    쪽이든 한국어 낱말을 찾는 같은 방법이다.
    """
    haystack = " ".join(t for t in texts if t)
    for word, motion in MOTION_BY_WORD.items():
        if word in haystack:
            return f"{motion}, static camera, everything else perfectly still"
    return f"{FALLBACK_MOTION}, static camera, everything else perfectly still"


def has_motion_subject(texts: Iterable[Optional[str]]) -> bool:
    """움직일 대상이 문구에 있는가

    없으면 만들어도 정지 사진과 구분되지 않는다 — 입학식·졸업식 같은 실내
    인물 사진이 그렇다. 돈이 드는 호출이므로 그런 사진은 부르지 않는다.
    """
    haystack = " ".join(t for t in texts if t)
    return any(word in haystack for word in MOTION_BY_WORD)


# --- ffmpeg 후처리 -----------------------------------------------------------

def tools_available() -> bool:
    return all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe"))


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool}이 PATH에 없다 — winget install Gyan.FFmpeg")


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


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
    _run([
        "ffmpeg", "-y", "-i", str(clip), "-i", str(photo), "-i", str(mask),
        "-filter_complex",
        f"[1:v]scale={width}:{height}[orig];"
        f"[2:v]scale={width}:{height},boxblur=4:1[msk];"
        f"[orig][msk]alphamerge[fg];[0:v][fg]overlay[out]",
        "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dest),
    ])


def pingpong(src: Path, dest: Path, seconds: float = 0.0) -> None:
    """앞으로 한 번, 뒤로 한 번 이어 붙여 끊기지 않는 루프를 만든다

    모델에 같은 시작·끝 프레임을 줘서 루프를 만드는 방법은 쓰지 않는다. 대부분의
    모델이 그 입력에는 움직임을 거의 만들지 않아서, 루프를 얻으려다 정지 화면을
    받는다. trim은 이음새에서 같은 프레임이 두 번 나오는 것을 막는다.

    대가는 역재생이 보이는 것이다 — 모델이 넣는 줌 인이 역방향에서 줌 아웃이
    되어 화면이 숨쉬듯 커졌다 작아진다.
    """
    head = f"trim=duration={seconds},setpts=PTS-STARTPTS," if seconds else ""
    _run([
        "ffmpeg", "-y", "-i", str(src), "-filter_complex",
        f"[0:v]{head}split[a][b];[b]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[r];"
        "[a][r]concat=n=2:v=1[out]",
        "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        # 메타데이터를 파일 앞으로. 없으면 브라우저가 전체를 받아야 재생을 시작한다.
        "-movflags", "+faststart", str(dest),
    ])


def crossfade_loop(src: Path, dest: Path, seconds: float, fade: float) -> None:
    """끝을 처음에 겹쳐 넘겨 이음새 없는 루프를 만든다 (역재생 없음)

    클립의 꼬리를 머리에 디졸브로 겹친다. 결과의 처음과 끝이 같은 프레임이라
    다시 시작할 때 튀지 않고, 방향이 한쪽뿐이라 파도가 거꾸로 가지 않는다.

    대가는 둘이다 — 길이가 fade만큼 줄고, 겹치는 구간에 잔상이 남는다.
    """
    body = seconds - fade
    if body <= fade:
        raise ValueError(f"use_seconds({seconds})가 crossfade({fade})의 두 배보다 커야 한다")
    _run([
        "ffmpeg", "-y", "-i", str(src), "-filter_complex",
        f"[0:v]trim=start={fade}:duration={body},setpts=PTS-STARTPTS[main];"
        f"[0:v]trim=duration={fade},setpts=PTS-STARTPTS[head];"
        f"[main][head]xfade=transition=fade:duration={fade}:offset={body - fade}[out]",
        "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(dest),
    ])


def trim_only(src: Path, dest: Path, seconds: float) -> None:
    """루프 처리 없이 앞부분만 잘라 낸다

    다시 시작할 때 튄다. 드리프트가 작으면 그게 가장 덜 거슬리는 선택이다.
    """
    args = ["ffmpeg", "-y", "-i", str(src)]
    if seconds:
        args += ["-t", str(seconds)]
    args += ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(dest)]
    _run(args)


def make_loop(src: Path, dest: Path, options: LoopOptions) -> None:
    if options.loop_mode == "crossfade":
        crossfade_loop(src, dest, options.use_seconds, options.crossfade)
    elif options.loop_mode == "pingpong":
        pingpong(src, dest, options.use_seconds)
    else:
        trim_only(src, dest, options.use_seconds)


def first_frame(src: Path, dest: Path) -> None:
    """poster용 첫 프레임. 자동재생이 막힌 환경에서 이것이 보인다."""
    _run(["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dest)])


# --- 목록 (미리 만든 것 + 런타임에 만든 것) ---------------------------------

def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def baked_manifest() -> dict:
    """저장소에 커밋된 클립 목록 (data/motion/manifest.json)"""
    return _read_json(MOTION_MANIFEST_FILE)


def runtime_manifest() -> dict:
    """런타임에 만든 클립 목록 (STATE_DIR — 배포에서는 볼륨)"""
    return _read_json(MOTION_RUNTIME_MANIFEST_FILE)


def manifest() -> dict:
    """둘을 합친 목록. 같은 사진이 양쪽에 있으면 런타임 쪽을 쓴다.

    캐시하지 않는다. 항목이 몇십 개고 파일이 작아서 읽는 값이 싸고, 캐시하면
    새로 만든 클립이 서버를 재시작해야 나타난다 — 런타임에 만드는 지금은
    그 함정이 곧바로 버그가 된다.
    """
    merged = baked_manifest()
    merged.update(runtime_manifest())
    return merged


def write_runtime_entry(media_id: str, entry: dict) -> None:
    current = runtime_manifest()
    current[media_id] = entry
    MOTION_RUNTIME_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MOTION_RUNTIME_MANIFEST_FILE.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_baked_manifest(entries: dict) -> None:
    """스크립트가 저장소 쪽 목록을 갱신할 때만 쓴다"""
    MOTION_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    MOTION_MANIFEST_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# --- 쓴 만큼 세기 (배포에서 잔액을 지키는 유일한 장치) ----------------------
#
# 이 API에는 인증이 없다. 주소를 아는 누구나 Film을 만들 수 있고, 그때마다
# 생성이 일어나면 잔액이 빈다. 상한을 넘으면 더 만들지 않고 지금까지 만든 것만
# 보여준다 — 화면은 클립이 없는 사진을 원래대로 CSS 움직임으로 돈다.
#
# 성공이 아니라 시도를 센다. 실패한 호출은 과금되지 않지만, 실패가 반복될 때
# 멈추는 장치가 없으면 그것도 위험이다.

_ledger_lock = threading.Lock()


def attempts_used() -> int:
    return int(_read_json(MOTION_LEDGER_FILE).get("attempts", 0))


def attempts_left() -> int:
    return max(0, MOTION_AUTOGEN_MAX - attempts_used())


def _record_attempt() -> int:
    with _ledger_lock:
        used = attempts_used() + 1
        MOTION_LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        MOTION_LEDGER_FILE.write_text(
            json.dumps({"attempts": used, "max": MOTION_AUTOGEN_MAX}, indent=2) + "\n",
            encoding="utf-8",
        )
        return used


# --- fal 호출 ----------------------------------------------------------------

def trust_os_certificates() -> None:
    """OS 인증서 저장소를 쓰게 한다

    TLS를 검사하는 사내망에서는 그 루트 CA가 Python의 certifi 번들에 없어서
    호출이 CERTIFICATE_VERIFY_FAILED로 끊긴다. 관리되는 PC의 저장소에는 그 CA가
    이미 있으므로 저장소를 바꿔 끼우면 통한다. 검증을 끄는 것이 아니다.
    """
    try:
        import truststore
    except ImportError:
        return
    truststore.inject_into_ssl()


def generate_source(photo: Path, prompt: str, options: LoopOptions, dest: Path) -> None:
    """fal에 사진 한 장을 보내 생성 결과를 dest에 내려받는다

    사진은 data URI로 요청에 실어 보낸다. CDN 업로드(rest.fal.ai/storage)를
    거치지 않는 편이 두 가지로 낫다 — 사내 웹 필터가 그 주소를 막는 환경에서도
    호출이 성립하고, 가족 사진이 별도 주소로 CDN에 남지 않는다(추론에는 여전히
    올라간다).
    """
    trust_os_certificates()
    import fal_client

    result = fal_client.subscribe(MODEL, arguments={
        "image_url": fal_client.encode_file(str(photo)),
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "resolution": options.resolution,
        "num_frames": options.seconds * SOURCE_FPS,
        "frames_per_second": SOURCE_FPS,
    })
    urllib.request.urlretrieve(result["video"]["url"], dest)


def build_clip(
    media_id: str,
    photo: Path,
    prompt: str,
    options: LoopOptions,
    out_dir: Path,
    source: Optional[Path] = None,
) -> dict:
    """생성 결과 하나를 클립·poster·목록 항목으로 마무리한다

    source를 주면 그것을 쓰고 호출하지 않는다 (이미 받아 둔 결과를 다시 자를 때).
    """
    require_tools()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = source or (out_dir / f"{media_id}.source.mp4")

    if source is None:
        generate_source(photo, prompt, options, raw)

    staged = raw
    mask = MASKS_DIR / f"{media_id}.png"
    if mask.exists():
        staged = out_dir / f"{media_id}.masked.mp4"
        restore_subject(raw, photo, mask, staged)

    clip = out_dir / f"{media_id}.mp4"
    poster = out_dir / f"{media_id}.poster.jpg"
    make_loop(staged, clip, options)
    first_frame(staged, poster)

    if staged is not raw:
        staged.unlink(missing_ok=True)
    if source is None and not options.keep_source:
        raw.unlink(missing_ok=True)

    return {
        "file": f"{SERVE_PREFIX}/{clip.name}",
        "poster": f"{SERVE_PREFIX}/{poster.name}",
        "model": MODEL,
        "prompt": prompt,
        "resolution": options.resolution,
        "source_seconds": options.seconds,
        "used_seconds": options.use_seconds,
        "loop": options.loop_mode,
        "crossfade": options.crossfade if options.loop_mode == "crossfade" else None,
        # 화면의 AI 라벨이 이 값을 보고 "인물은 원본"을 붙인다
        "subject_preserved": mask.exists(),
    }


# --- 런타임 생성 (Film을 만들 때) -------------------------------------------

_state_lock = threading.Lock()
_pending: set[str] = set()
_failed: dict[str, str] = {}
# 한 번에 하나씩만 만든다. 동시에 여러 건을 돌리면 CPU(ffmpeg)와 지출이 함께
# 튀고, 어차피 사람은 한 편을 보는 중이다.
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="motion")


def enabled() -> bool:
    """런타임 생성을 할 수 있는 상태인가

    키가 없으면 조용히 꺼진다 — 설정하지 않은 사람의 화면이 깨지지 않아야 하고,
    이 기능이 없어도 사진은 CSS 카메라 움직임으로 그대로 돈다.
    """
    return bool(
        MOTION_AUTOGEN
        and os.getenv("FAL_KEY")
        and tools_available()
        and attempts_left() > 0
    )


def pending_ids() -> list[str]:
    with _state_lock:
        return sorted(_pending)


def failures() -> dict[str, str]:
    with _state_lock:
        return dict(_failed)


def request(media_id: str, photo_path: Path, prompt: str) -> bool:
    """없는 클립 하나를 만들어 달라고 맡긴다 (즉시 돌려준다)

    이미 있거나 만들고 있거나, 한 번 실패했으면 다시 부르지 않는다. 실패를
    다시 부르지 않는 것이 중요하다 — 화면이 주기적으로 물어보는 구조라서
    실패를 재시도하면 같은 호출이 끝없이 반복된다.
    """
    if not enabled():
        return False

    with _state_lock:
        if media_id in _pending or media_id in _failed:
            return False
        if media_id in manifest():
            return False
        if not photo_path.exists():
            return False
        _pending.add(media_id)

    _worker.submit(_work, media_id, photo_path, prompt)
    return True


def _work(media_id: str, photo_path: Path, prompt: str) -> None:
    try:
        # 상한은 맡길 때가 아니라 실제로 부르기 직전에 다시 본다. 줄에 여러 건이
        # 서 있는 동안 상한에 닿을 수 있다.
        #
        # 이때는 실패로 적지 않는다. 상한은 일시적인 조건이고 — 운영자가 올리면
        # 다시 만들 수 있어야 한다 — 실패로 적으면 그 사진은 영구히 제외된다.
        # 그냥 물러나면 다음 compose에서 다시 맡을 후보가 된다.
        if attempts_used() >= MOTION_AUTOGEN_MAX:
            return
        _record_attempt()

        entry = build_clip(media_id, photo_path, prompt, LoopOptions(), SERVE_DIR)
        write_runtime_entry(media_id, entry)
    except Exception as error:  # 공급자·ffmpeg 예외 종류가 제각각이라 넓게 받는다
        with _state_lock:
            _failed[media_id] = str(error)[:200]
    finally:
        with _state_lock:
            _pending.discard(media_id)
