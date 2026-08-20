"""영상 첫 장면을 뽑아 저장소에 커밋한다 (사진첩 썸네일)

왜 필요한가: 사진첩·추억 카드·홈은 `thumbnail_path || file_path`를 <img>에
넣는다. 영상에 썸네일이 없으면 그 자리에 mp4 주소가 들어가고, 브라우저는
수십 MB를 받아 온 다음 "그림이 아니다"로 실패한다 — 화면에는 깨진 사진
아이콘만 남는다.

업로드된 영상은 브라우저가 첫 장면을 뽑아 함께 보낸다
(frontend/src/lib/videoMeta.ts). 그 길이 없는 것이 하나 있다: data/video/에
커밋된 시드 영상이다. 업로드를 지나지 않으므로 뽑아 줄 브라우저가 없다.

그래서 사진과 같은 규약으로 만든다 — 저장소에 커밋되는 읽기 전용 자산이고
(data/video/thumb_*.jpg), 시드가 서빙 자리로 복사한다. 서버에 ffmpeg를 두지
않는다는 선택은 그대로다. 이 스크립트는 손으로 한 번 돌리는 빌드 도구다
(scripts/build_motion_covers.py와 같은 자리).

    필요한 것: ffmpeg · ffprobe (PATH)
    쓰는 법:   python scripts/build_video_posters.py
               python scripts/build_video_posters.py --assets-only

기본값은 자산을 만들고, 이미 시드된 그래프의 영상 노드에도 그 값을 채운다.
채우는 것은 비어 있는 thumbnail_path·duration_sec 뿐이다 — 다시 시드하면
사용자가 올린 기록까지 함께 지워지므로, 시드 없이 고칠 길을 둔다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.config import MEDIA_DIR, VIDEO_DIR

VIDEO_SUFFIXES = (".mp4", ".mov", ".avi")

# 사진 썸네일과 같은 크기 (backend/services/media_analyzer.generate_thumbnail)
POSTER_MAX = 300

# 만든 것을 적어 두는 자리. 시드가 이것을 읽는다.
MANIFEST_NAME = "posters.json"


def require_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool}이 PATH에 없다 — winget install Gyan.FFmpeg")


def probe_duration(src: Path) -> float | None:
    """초. 못 재면 None (webm 등 일부는 duration이 비어 온다)"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(src)],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        seconds = float(out)
    except (subprocess.CalledProcessError, ValueError):
        return None
    return round(seconds, 1) if seconds > 0 else None


def poster_time(duration: float | None) -> float:
    """첫 프레임이 검은 화면인 영상이 많아서 조금 뒤로 간다

    브라우저 쪽과 같은 규칙이다 (frontend/src/lib/videoMeta.ts posterTime).
    """
    if not duration or duration <= 0:
        return 0.0
    return min(1.0, duration * 0.1)


def extract_poster(src: Path, dest: Path, at: float) -> bool:
    """그 시각의 한 프레임을 긴 변 300px JPEG으로 저장한다"""
    args = [
        "ffmpeg", "-y",
        # -i 앞의 -ss는 그 지점까지 디코드하지 않고 건너뛴다 (긴 영상에서 빠르다)
        "-ss", f"{at:.2f}",
        "-i", str(src),
        "-frames:v", "1",
        # 긴 변만 300으로 맞추고 짧은 변은 비율대로. -1은 짝수 보정이 없어
        # 홀수 높이에서 인코딩이 막히므로 -2를 쓴다.
        "-vf", f"scale='if(gt(iw,ih),{POSTER_MAX},-2)':'if(gt(iw,ih),-2,{POSTER_MAX})'",
        "-q:v", "3",
        str(dest),
    ]
    try:
        subprocess.run(args, check=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.decode("utf-8", "replace").strip().splitlines()
        print(f"  ✗ {src.name}: 프레임을 뽑지 못했다 — {stderr[-1] if stderr else error}")
        return False
    return dest.exists() and dest.stat().st_size > 0


def build(video_dir: Path) -> dict:
    """data/video의 영상마다 thumb_*.jpg를 만들고 목록을 돌려준다"""
    if not video_dir.exists():
        raise SystemExit(f"영상 디렉터리가 없다: {video_dir}")

    manifest: dict[str, dict] = {}

    for src in sorted(video_dir.iterdir()):
        if not src.is_file() or src.suffix.lower() not in VIDEO_SUFFIXES:
            continue

        duration = probe_duration(src)
        thumb_name = f"thumb_{src.stem}.jpg"
        dest = video_dir / thumb_name

        if not extract_poster(src, dest, poster_time(duration)):
            continue

        manifest[src.stem] = {"thumb": thumb_name, "duration_sec": duration}
        length = f"{duration}s" if duration else "길이 미상"
        print(f"  ✓ {src.name} → {thumb_name} ({length})")

    return manifest


def apply_to_graph(manifest: dict) -> int:
    """이미 시드된 영상 노드의 빈 칸을 채운다

    시드 스크립트는 그래프를 지우고 다시 만든다. 그 사이에 가족이 올린 기록이
    있으면 함께 사라지므로, 이미 도는 저장소는 여기서 자리만 채운다.
    """
    # 저장소를 고르는 곳은 한 군데다 (JSON이냐 Postgres냐를 여기서 알 필요 없다)
    from backend.services.graph_manager import graph_manager

    patched = 0
    for stem, info in manifest.items():
        node_id = f"video_{stem}"
        node = graph_manager.get_node(node_id)
        if not node:
            continue

        updates = {}
        if not node.get("thumbnail_path"):
            updates["thumbnail_path"] = f"/media-files/{info['thumb']}"
        if not node.get("duration_sec") and info.get("duration_sec"):
            updates["duration_sec"] = info["duration_sec"]

        if not updates:
            continue

        graph_manager.update_node(node_id, updates)
        patched += 1
        print(f"  ✓ {node_id} ← {', '.join(updates)}")

    return patched


def copy_to_media(manifest: dict) -> int:
    """서빙되는 자리로 옮긴다. 사진·모션 클립과 같은 규약이다"""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for info in manifest.values():
        src = VIDEO_DIR / info["thumb"]
        dest = MEDIA_DIR / info["thumb"]
        if not dest.exists() or src.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(str(src), str(dest))
            copied += 1
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="시드 영상의 첫 장면을 썸네일로 뽑는다")
    parser.add_argument(
        "--assets-only",
        action="store_true",
        help="자산만 만들고 도는 그래프는 건드리지 않는다 (시드를 새로 돌릴 때)",
    )
    args = parser.parse_args()

    require_tools()

    print(f"🎬 영상 썸네일 만드는 중... ({VIDEO_DIR})")
    manifest = build(VIDEO_DIR)

    if not manifest:
        print("만든 것이 없다 — data/video에 영상이 있는지 본다.")
        return

    manifest_path = VIDEO_DIR / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  ✓ 목록 {manifest_path.relative_to(ROOT_DIR)}")

    copied = copy_to_media(manifest)
    if copied:
        print(f"  ✓ 서빙 자리로 {copied}개 복사 ({MEDIA_DIR})")

    if args.assets_only:
        print("\n✅ 자산 {0}개. 그래프는 시드가 채운다.".format(len(manifest)))
        return

    print("\n도는 그래프에 반영 중...")
    patched = apply_to_graph(manifest)
    print(f"\n✅ 자산 {len(manifest)}개 · 노드 {patched}개 반영")


if __name__ == "__main__":
    main()
