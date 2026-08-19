"""Export Router — 가족 아카이브

지어낸 진행률을 만들지 않는다. zip을 실제로 만들어 파일로 돌려준다.
시드 규모(사진 28장 · 26MB)에서는 곧바로 끝난다. 규모가 커지면 작업 큐로
옮길 자리이고, 그 전까지는 없는 비동기를 흉내 내지 않는다.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.services import exporter

router = APIRouter()


@router.get("/manifest")
async def get_manifest(viewer_id: str = Query(None, description="내보내는 사람")):
    """무엇을 얼마나 내보낼 수 있는지 (크기는 디스크에서 잰 실제 값)"""
    return exporter.manifest(viewer_id)


@router.post("")
async def build_archive(
    viewer_id: str = Query(None, description="내보내는 사람"),
    items: str = Query(None, description="쉼표로 구분한 항목 id"),
):
    """아카이브를 만든다. 열람 범위 밖의 기록은 담지 않는다."""
    selected = [item.strip() for item in items.split(",")] if items else None
    result = exporter.build(viewer_id, selected)
    return result


@router.get("/download/{file_name}")
async def download(file_name: str):
    """만들어 둔 아카이브 내려받기"""
    path = exporter.resolve_download(file_name)
    if not path:
        raise HTTPException(status_code=404, detail="아카이브를 찾을 수 없습니다.")

    return FileResponse(path, media_type="application/zip", filename=file_name)
