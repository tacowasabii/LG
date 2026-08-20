"""영상 업로드 회귀 테스트 (길이 · 첫 장면 썸네일)

    python tests/test_video_upload.py

서버에 ffmpeg를 두지 않으므로 영상의 길이와 첫 장면은 브라우저가 재서 보낸다
(frontend/src/lib/videoMeta.ts). 여기서 재는 것은 서버가 그 값을 제대로 받아
쓰는지, 그리고 남이 보낸 그림을 믿지 않는지다.

  - 첫 장면을 보내면 썸네일이 만들어지고 목록·응답에 실려 나가는가
  - 길이가 영상에도 붙는가 (예전에는 음성 전용이었다)
  - 첫 장면 없이 올려도 업로드가 성공하는가 (썸네일만 없다)
  - 이미지가 아닌 것을 poster로 보내면 버리는가 (업로드는 성공)
  - 삭제할 때 썸네일 파일까지 함께 지우는가

업로드가 실제 파일을 만들므로 끝에서 지운다.

시드된 그래프가 필요하다:
    python scripts/seed_from_metadata.py
"""

import io
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from PIL import Image  # noqa: E402

from backend.config import MEDIA_DIR  # noqa: E402
from backend.models.graph_models import MediaType  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

_created: list[str] = []


def _require_seeded_graph():
    if len(graph_manager.get_persons()) < 5:
        raise AssertionError(
            "시드된 그래프가 필요합니다. python scripts/seed_from_metadata.py 를 먼저 실행하세요."
        )


def _poster_bytes(size=(640, 360)) -> bytes:
    """브라우저 캔버스가 뽑아 보내는 것과 같은 모양의 JPEG"""
    buffer = io.BytesIO()
    Image.new("RGB", size, (90, 120, 160)).save(buffer, "JPEG")
    return buffer.getvalue()


def _upload(client, filename: str, *, poster: bytes = None, duration: float = None) -> dict:
    files = {"file": (filename, b"fake-video-bytes", "video/mp4")}
    if poster is not None:
        files["poster"] = ("poster.jpg", poster, "image/jpeg")

    data = {}
    if duration is not None:
        data["duration_sec"] = str(duration)

    response = client.post("/api/media/upload", files=files, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    _created.append(body["id"])
    return body


def _files_of(media_id: str) -> list[Path]:
    node = graph_manager.get_node(media_id)
    if not node:
        return []
    paths = []
    for key in ("file_path", "thumbnail_path"):
        name = Path(node.get(key) or "").name
        if name:
            paths.append(MEDIA_DIR / name)
    return paths


def _cleanup():
    for media_id in _created:
        for path in _files_of(media_id):
            if path.exists():
                path.unlink()
        if graph_manager.get_node(media_id):
            graph_manager.delete_node(media_id)
    _created.clear()
    # 실패한 정규화가 남긴 임시 파일이 없어야 한다
    for leftover in MEDIA_DIR.glob("poster_raw_*"):
        leftover.unlink()


def test_poster_becomes_thumbnail():
    """첫 장면을 보내면 썸네일이 만들어지고 응답·목록에 실려 나간다"""
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "trip.mp4", poster=_poster_bytes(), duration=12.4)

            assert body["media_type"] == MediaType.VIDEO, body
            assert body["thumbnail_path"], body
            assert body["duration_sec"] == 12.4, body

            listed = client.get("/api/media", params={"media_type": "video"})
            found = next(i for i in listed.json() if i["id"] == body["id"])

        assert found["thumbnail_path"] == body["thumbnail_path"], found
        assert found["duration_sec"] == 12.4, found

        thumb = MEDIA_DIR / Path(body["thumbnail_path"]).name
        assert thumb.exists(), thumb
        # Pillow로 다시 저장하므로 한 변이 300 이하로 줄어 있어야 한다
        with Image.open(thumb) as img:
            assert max(img.size) <= 300, img.size
        print("  첫 장면 → 썸네일 OK:", body["thumbnail_path"])
    finally:
        _cleanup()


def test_video_without_poster_still_uploads():
    """첫 장면을 못 뽑아도 업로드는 성공한다 (썸네일만 없다)

    브라우저가 코덱을 못 열거나 시간이 초과되는 영상이 있다. 그때 업로드가
    막히면 기록을 잃는다 — 썸네일이 없는 것은 불편일 뿐이다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "no-poster.mp4")

        assert body["media_type"] == MediaType.VIDEO, body
        assert not body["thumbnail_path"], body
        print("  첫 장면 없이도 업로드 OK")
    finally:
        _cleanup()


def test_non_image_poster_is_rejected_without_failing_upload():
    """이미지가 아닌 poster는 버린다. 업로드 자체는 성공한다

    화면이 보낸 파일이므로 정말 이미지인지 서버가 가른다. Pillow가 열지
    못하면 썸네일을 붙이지 않고 넘어간다.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/media/upload",
                files={
                    "file": ("bad-poster.mp4", b"fake-video-bytes", "video/mp4"),
                    "poster": ("poster.jpg", b"this-is-not-an-image", "image/jpeg"),
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            _created.append(body["id"])

        assert not body["thumbnail_path"], body
        # 정규화 실패가 임시 파일을 남기지 않아야 한다
        assert not list(MEDIA_DIR.glob("poster_raw_*")), "임시 파일이 남았다"
        print("  이미지 아닌 poster 버림 OK")
    finally:
        _cleanup()


def test_delete_removes_generated_thumbnail():
    """삭제할 때 만들어 둔 썸네일 파일까지 함께 지운다"""
    from fastapi.testclient import TestClient

    from backend.main import app

    try:
        with TestClient(app) as client:
            body = _upload(client, "delete-me.mp4", poster=_poster_bytes())
            thumb = MEDIA_DIR / Path(body["thumbnail_path"]).name
            original = MEDIA_DIR / Path(body["file_path"]).name
            assert thumb.exists() and original.exists()

            deleted = client.delete(f"/api/media/{body['id']}")
            assert deleted.status_code == 200, deleted.text

        assert not thumb.exists(), "썸네일이 남았다"
        assert not original.exists(), "원본이 남았다"
        print("  삭제가 썸네일까지 정리 OK")
    finally:
        _cleanup()


def _main():
    _require_seeded_graph()
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}\n{e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__} {e}")
        finally:
            _cleanup()

    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
