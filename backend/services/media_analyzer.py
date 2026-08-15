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


def detect_media_type(filename: str) -> str:
    """파일 확장자로 미디어 타입 판별"""
    ext = Path(filename).suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".tiff"):
        return MediaType.PHOTO
    elif ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        return MediaType.VIDEO
    elif ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"):
        return MediaType.AUDIO
    return MediaType.PHOTO  # default


def analyze_media(file_path: str, original_filename: str) -> MediaNode:
    """미디어 파일 분석 → MediaNode 생성

    MVP에서는:
    - 사진: EXIF 추출 (실제)
    - 얼굴 인식 / 장면 분류: 시뮬레이션 (향후 AI Vision 연동)
    - 음성/영상: 파일 정보만 (향후 STT 연동)
    """
    media_type = detect_media_type(original_filename)

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

    # TODO: AI Vision 연동 시 얼굴 인식, 장면 분류 결과 추가
    # node.detected_faces = ai_vision.detect_faces(file_path)
    # node.scene_description = ai_vision.describe_scene(file_path)

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
