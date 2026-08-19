"""각 가족 구성원의 프로필 사진 자동 생성

각 인물이 단독(또는 적은 인원)으로 등장하는 사진에서
얼굴이 있을 가능성이 높은 상단 중앙을 정사각형 크롭합니다.
"""

import sys
import json
from pathlib import Path

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services.graph_manager import graph_manager

DATA_DIR = ROOT_DIR / "data"
PHOTOS_DIR = DATA_DIR / "photos"
METADATA_DIR = DATA_DIR / "metadata"
PROFILES_DIR = DATA_DIR / "profiles"
MEDIA_DIR = DATA_DIR / "media"

PROFILES_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_SIZE = 256


def smart_crop_portrait(img: Image.Image) -> Image.Image:
    """인물 사진에서 상단 중앙을 정사각형 크롭 (얼굴은 보통 상단 1/3에 위치)"""
    w, h = img.size
    size = min(w, h)

    # 가로가 넓으면 중앙, 세로가 긴 사진이면 상단 쪽으로 크롭
    x1 = (w - size) // 2

    if h > w:
        # 세로가 긴 사진 → 상단 30% 지점 중심
        center_y = int(h * 0.3)
        y1 = max(0, center_y - size // 2)
        y1 = min(y1, h - size)
    else:
        # 정사각형에 가깝거나 가로가 넓은 사진 → 상단
        y1 = 0

    cropped = img.crop((x1, y1, x1 + size, y1 + size))
    return cropped.resize((PROFILE_SIZE, PROFILE_SIZE), Image.Resampling.LANCZOS)


def generate_profiles():
    print("👤 가족 프로필 사진 생성 중...")

    # 메타데이터 로드
    media_data = json.loads((METADATA_DIR / "media.json").read_text(encoding="utf-8"))
    persons_data = json.loads((METADATA_DIR / "persons.json").read_text(encoding="utf-8"))

    person_names = {p["person_id"]: p["name"] for p in persons_data}

    # 각 인물별 등장 사진을 인원수 기준으로 정렬 (적은 인원 우선)
    person_photos: dict[str, list[tuple[int, str]]] = {p["person_id"]: [] for p in persons_data}
    for m in media_data:
        people_count = len(m.get("people", []))
        photo_path = str(PHOTOS_DIR / m["file_name"])
        for pid in m.get("people", []):
            if pid in person_photos:
                person_photos[pid].append((people_count, photo_path))

    # 인원수 적은 순으로 정렬
    for pid in person_photos:
        person_photos[pid].sort(key=lambda x: x[0])

    # 각 인물 프로필 생성
    for person in persons_data:
        pid = person["person_id"]
        name = person["name"]
        photos = person_photos.get(pid, [])

        if not photos:
            print(f"  ⚠ {name} ({pid}): 등장 사진 없음")
            continue

        # 가장 적은 인원이 등장하는 사진 사용
        _, best_photo = photos[0]

        try:
            img = Image.open(best_photo)
            img = img.convert("RGB")
            profile = smart_crop_portrait(img)

            # profiles 디렉토리에 저장
            output_path = PROFILES_DIR / f"{pid}.jpg"
            profile.save(str(output_path), "JPEG", quality=90)

            # media 디렉토리에도 저장 (웹 서빙용)
            media_output = MEDIA_DIR / f"profile_{pid}.jpg"
            profile.save(str(media_output), "JPEG", quality=90)

            # 파일만 만들어두면 화면은 이니셜로 폴백한다. Graph에 경로를 연결해야 보인다.
            graph_manager.update_node(pid, {"thumbnail_url": f"/media-files/profile_{pid}.jpg"})

            people_in_photo = photos[0][0]
            print(f"  ✓ {name} ({pid}): 프로필 생성 + Graph 연결 (소스: {people_in_photo}명 등장 사진)")

        except Exception as e:
            print(f"  ⚠ {name} ({pid}): 처리 실패 - {e}")

    print(f"\n✅ 프로필 생성 완료!")
    print(f"   저장 위치: {PROFILES_DIR}")
    print(f"   서빙 위치: {MEDIA_DIR}/profile_*.jpg")


if __name__ == "__main__":
    generate_profiles()
