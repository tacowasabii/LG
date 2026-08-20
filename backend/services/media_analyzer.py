"""미디어 파일 분석 - EXIF 추출 + AI 분석 (MVP 시뮬레이션)"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional
from datetime import datetime

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from backend.models.graph_models import MediaNode, MediaType, Confidence, SourceType


def extract_exif(file_path: str) -> dict:
    """사진에서 EXIF 메타데이터 추출"""
    result = {
        "exif_date": None,
        "exif_lat": None,
        "exif_lng": None,
        "exif_camera": None,
    }

    try:
        img = Image.open(file_path)
        exif_data = img._getexif()
        if not exif_data:
            return result

        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)

            if tag_name == "DateTimeOriginal":
                try:
                    dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                    result["exif_date"] = dt.isoformat()
                except (ValueError, TypeError):
                    pass

            elif tag_name == "Make" or tag_name == "Model":
                camera = result.get("exif_camera") or ""
                result["exif_camera"] = f"{camera} {value}".strip()

            elif tag_name == "GPSInfo":
                gps = _parse_gps(value)
                if gps:
                    result["exif_lat"] = gps[0]
                    result["exif_lng"] = gps[1]

    except Exception:
        pass

    return result


def _parse_gps(gps_info: dict) -> Optional[tuple[float, float]]:
    """GPS EXIF 데이터를 위도/경도로 변환"""
    try:
        gps_tags = {}
        for key, val in gps_info.items():
            tag = GPSTAGS.get(key, key)
            gps_tags[tag] = val

        lat = _convert_to_degrees(gps_tags.get("GPSLatitude"))
        lng = _convert_to_degrees(gps_tags.get("GPSLongitude"))

        if lat is None or lng is None:
            return None

        if gps_tags.get("GPSLatitudeRef") == "S":
            lat = -lat
        if gps_tags.get("GPSLongitudeRef") == "W":
            lng = -lng

        return (lat, lng)
    except Exception:
        return None


def _convert_to_degrees(value) -> Optional[float]:
    """GPS 좌표를 도(degree)로 변환"""
    if value is None:
        return None
    try:
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, IndexError, ZeroDivisionError):
        return None


def detect_media_type(filename: str, content_type: Optional[str] = None) -> str:
    """미디어 타입 판별 — 브라우저가 알려준 형식을 먼저 믿는다

    확장자만으로는 갈리지 않는 경우가 있다. 브라우저 녹음은 audio/webm으로
    나오는데 .webm은 영상 확장자와 같아서, 확장자만 보면 목소리가 영상으로
    저장된다 — 음성 목록에서 빠지고 파형도 쓰이지 않는다.

    Content-Type은 남이 보낸 값이지만 여기서 틀려도 손해는 분류 하나이고,
    확장자보다 정확하다. 형식이 이상하면 확장자로 떨어진다.
    """
    prefix = (content_type or "").split(";")[0].strip().lower()
    if prefix.startswith("audio/"):
        return MediaType.AUDIO
    if prefix.startswith("video/"):
        return MediaType.VIDEO
    if prefix.startswith("image/"):
        return MediaType.PHOTO

    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".tiff"):
        return MediaType.PHOTO
    elif ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        return MediaType.VIDEO
    elif ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"):
        return MediaType.AUDIO
    return MediaType.PHOTO  # default


def analyze_media(
    file_path: str,
    original_filename: str,
    content_type: Optional[str] = None,
) -> MediaNode:
    """미디어 파일 분석 → MediaNode 생성

    MVP에서는:
    - 사진: EXIF 추출 (실제)
    - 얼굴 인식: 없다. 사람이 직접 지목한다 (event_resolver.set_media_persons)
    - 장면 설명: 추억 초안을 만들 때 모델이 채운다 (services/vision.py)
    - 음성: 전사는 브라우저가 한다 (frontend/src/lib/transcriber.ts)
    - 영상: 파일 정보만
    """
    media_type = detect_media_type(original_filename, content_type)

    node = MediaNode(
        media_type=media_type,
        file_path=file_path,
        original_filename=original_filename,
        source=SourceType.EXIF,
    )

    # 사진인 경우 EXIF 추출
    if media_type == MediaType.PHOTO:
        exif = extract_exif(file_path)
        node.exif_date = exif["exif_date"]
        node.exif_lat = exif["exif_lat"]
        node.exif_lng = exif["exif_lng"]
        node.exif_camera = exif["exif_camera"]

        if node.exif_date:
            node.confidence = Confidence.CONFIRMED
            node.created_at = node.exif_date

    # 여기서 사진을 모델에 보내지 않는다. 장면 설명은 추억 초안을 만들 때
    # 채운다 (services/vision.py) — 업로드는 파일을 받는 일이고, 그 응답을
    # 모델 호출만큼 늦추면 사진 여러 장을 올릴 때 그만큼 밀린다.
    #
    # 누가 찍혔는지(detected_faces)는 모델이 정하지 않는다. 사람이 지목한다
    # (event_resolver.set_media_persons). 가족 구성원 식별은 생체정보이고,
    # 범용 모델이 틀리면 남의 사진에 엉뚱한 사람이 붙는다.

    return node


def generate_thumbnail(file_path: str, output_path: str, size: tuple = (300, 300)) -> Optional[str]:
    """사진 썸네일 생성"""
    try:
        img = Image.open(file_path)
        img.thumbnail(size, Image.Resampling.LANCZOS)
        img.save(output_path, "JPEG", quality=85)
        return output_path
    except Exception:
        return None
