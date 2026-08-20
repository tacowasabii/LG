"""사진 속 얼굴로 가족을 알아본다 (Amazon Rekognition)

올린 사진에서 얼굴을 찾고, 등록된 가족과 맞춰 누가 있는지 채운다. 사람이 알약을
하나씩 누르지 않아도 되게 하는 것이 목적이고, 누른 결과를 덮지는 않는다.

── 왜 이렇게 만들었는지 (실측으로 정한 것)

범용 비전 모델에게 "이 사람이 누구냐"를 묻지 않는다. 얼굴 임베딩 검색이 맞는
도구다. 실측한 것을 그대로 적는다.

1. `SearchFacesByImage`는 **이미지에서 가장 큰 얼굴 하나만** 검색한다. 단체 사진을
   그대로 넣으면 나머지 사람이 통째로 빠진다. 그래서 얼굴을 각각 잘라 따로 찾는다.

2. 참조 얼굴이 틀리면 전부 틀린다. "가장 큰 얼굴"을 그 사람이라고 가정해 등록했을
   때, 아빠 얼굴이 딸로 등록되어 모든 사진에서 딸이 아빠에게 매칭됐다. 그래서
   등록할 때 **크롭 안에 얼굴이 하나뿐인지 확인**한다.

3. 어른은 정확하고 아이는 흔들린다. 제대로 등록한 참조로 재면 본인은 100.0점에
   2등과 8~12점 차이가 났다. 그런데 아이는 2등과 0.2점 차이까지 붙었다 — 참조는
   10대 딸인데 1998년 사진에서는 2살이기 때문이다. 같은 사람의 얼굴이 나이에 따라
   달라지는 것을 유사도만으로는 넘을 수 없다.

4. 그래서 **나이를 함께 본다.** 그래프에 birth_year가 있고 사진에 촬영 시점이 있어서
   "이 사람은 그때 몇 살이었나"를 계산할 수 있다. Rekognition의 추정 나이와 어긋나면
   후보에서 뺀다. 위 세 오답이 전부 이 규칙으로 걸러졌다.
     - 1998년 사진의 0~2세 얼굴: 2000년생 아들은 **아직 태어나지 않았다**
     - 2015년 사진의 19~25세 얼굴: 그때 42세인 엄마는 아니다

5. **얼굴 하나만 보고 판정하면 안 된다.** 얼굴별로 "1등과 2등이 붙었으면 비운다"를
   적용했더니 딸이 여덟 장 중 일곱 장에서 빠졌다 — 100 대 100 동점이었고, 그 상대는
   이미 다른 얼굴에 확정된 엄마였다. 사진 안에서 이미 정해진 사람은 이 얼굴의
   경쟁자가 아니다. 사진 전체를 보고 한 번에 배정하니 67% -> 79%가 됐다.

── 실측 정확도 (시드 24장 중 연대별 8장, 등록 48장)

    맞춤 26/33 (79%) · 놓침 7 · **오인 0**

오인이 0인 것이 이 구현의 목표다. 놓치는 것은 사람이 알약을 눌러 채우면 되지만,
틀린 이름이 붙으면 그것이 공개 범위 판정까지 타고 들어간다. 남은 놓침은 형제
(같은 나이대) 와 참조가 한 장뿐인 할머니다 — 등록을 더 하면 준다.

── 지키는 선

**덮어쓰지 않는다.** 사람이 지목한 인물은 그대로 두고, 비어 있는 자리만 채운다.
알아본 결과는 추정(ai_inferred)이고 화면에서 끌 수 있다.

**애매하면 비운다.** 1등과 2등이 붙어 있거나 나이가 맞는 후보가 둘 이상이면 아무도
넣지 않는다. 틀린 이름이 붙는 것보다 "모르겠다"가 낫다 — 등장 인물은 공개 범위
판정에도 쓰이므로, 잘못 붙으면 남의 사진에 자기가 들어간다.

**자격증명이 없으면 조용히 지나간다.** 이 기능이 없어도 사람이 지목하는 길은 그대로
동작한다 (event_resolver.set_media_persons).
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

from PIL import Image

from backend.config import (
    AWS_ACCESS_KEY_ID,
    AWS_PROFILE,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
    MEDIA_DIR,
)
from backend.models.graph_models import NodeType
from backend.services.graph_manager import graph_manager

# 가족 얼굴을 담는 Rekognition 컬렉션. 계정 안에서 이 앱의 것만 쓴다.
COLLECTION_ID = "homestory-family"

# 모델에 보내기 전에 줄이는 한 변 최대 길이. 얼굴이 145px쯤 되면 충분히 찾는다.
MAX_SIDE = 1600

# 얼굴 크롭에 주는 여백. 너무 크면 옆 사람 얼굴이 함께 들어온다 (실측으로 0.15).
CROP_PAD = 0.15

# 크롭이 이보다 작으면 검색하지 않는다. 배경에 스친 얼굴이다.
MIN_FACE_PX = 50

# 1등이 이 점수를 넘어야 후보로 본다.
MATCH_THRESHOLD = 90.0

# 1등과 2등의 점수 차이가 이보다 작으면 애매한 것으로 보고 비운다.
# 실측: 본인은 2등과 8~12점 차이, 아이가 헷갈릴 때는 0.2~2.6점 차이였다.
MIN_MARGIN = 4.0

# 추정 나이 구간에서 이만큼까지는 벗어나도 같은 사람으로 본다.
# 실측: 36세 아빠를 41-49로, 28세를 32-45로 추정했다 (어른은 높게 잡는 경향).
AGE_TOLERANCE = 10


def _log(message: str) -> None:
    """콘솔이 못 찍는 글자로 기능이 꺼지지 않게 한다

    윈도우 콘솔은 cp949라서 "—" 같은 글자에서 print가 UnicodeEncodeError를
    던진다. 그 예외가 호출부의 except Exception에 잡혀 **얼굴 인식이 조용히
    꺼졌다** — 로그를 찍다가 기능을 잃는 것은 어느 쪽으로도 남는 장사가 아니다.
    """
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"), flush=True)


def enabled() -> bool:
    """얼굴 인식을 쓸 수 있는가 (AWS 자격증명이 있는가)"""
    return bool(AWS_PROFILE or (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY))


_client = None


def _rekognition():
    """Rekognition 클라이언트 (한 번만 만든다)

    boto3를 여기서 import한다. 자격증명이 없는 로컬에서 이 패키지가 없어도 앱이
    뜨게 하려는 것이다 (llm_client·pg_store와 같은 방식).

    이 망은 새 연결의 첫 요청이 자주 끊긴다. botocore 재시도를 넉넉히 준다.
    """
    global _client
    if _client is not None:
        return _client

    import boto3
    from botocore.config import Config

    kwargs = {"region_name": AWS_REGION}
    if AWS_PROFILE:
        session = boto3.session.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    else:
        creds = {
            "aws_access_key_id": AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        }
        if AWS_SESSION_TOKEN:
            creds["aws_session_token"] = AWS_SESSION_TOKEN
        session = boto3.session.Session(region_name=AWS_REGION, **creds)

    _client = session.client(
        "rekognition",
        config=Config(
            retries={"max_attempts": 6, "mode": "standard"},
            connect_timeout=10,
            read_timeout=30,
        ),
        **{k: v for k, v in kwargs.items() if k != "region_name"},
    )
    return _client


def ensure_collection() -> bool:
    """컬렉션이 없으면 만든다. 못 만들면 False"""
    if not enabled():
        return False
    try:
        _retry(lambda: _rekognition().create_collection(CollectionId=COLLECTION_ID),
               "컬렉션 만들기")
        _log(f"[faces] 컬렉션을 만들었습니다: {COLLECTION_ID}")
        return True
    except Exception as e:
        # 이름으로 잡는다. botocore의 예외 클래스는 클라이언트 인스턴스마다 새로
        # 만들어져서, _retry가 클라이언트를 갈아 끼우면 isinstance가 어긋난다.
        # 그 탓에 "이미 있다"가 실패로 읽혀 identify가 통째로 빈 목록을 냈다.
        if type(e).__name__ == "ResourceAlreadyExistsException":
            return True
        _log(f"[faces] 컬렉션을 준비하지 못했습니다 ({type(e).__name__}: {e})")
        return False


# --- 이미지 다루기 ------------------------------------------------------------


def _retry(call, what: str, attempts: int = 6):
    """이 망은 새 연결의 첫 요청이 자주 끊긴다. botocore 재시도로는 부족했다.

    실측: 24장 등록에서 19장이 ConnectionClosedError로 빠졌다 — 데이터 문제가
    아니라 연결 문제였다. 여기서 다시 걸면 대부분 두 번째에 붙는다.
    """
    import time

    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as e:
            name = type(e).__name__
            # 다시 걸어도 같은 결과인 것은 바로 넘긴다
            if name in ("InvalidParameterException", "ResourceNotFoundException",
                        "ResourceAlreadyExistsException", "AccessDeniedException"):
                raise
            if attempt == attempts:
                _log(f"[faces] {what} 실패 ({name}) — {attempts}번 시도했습니다")
                raise
            # 연결이 끊긴 뒤 같은 클라이언트로 다시 걸면 오염된 연결 풀을 계속
            # 쓴다. 클라이언트를 버리고 새 연결로 붙는다.
            global _client
            _client = None
            time.sleep(0.8 * attempt)


def _to_jpeg(image: Image.Image, quality: int = 92) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def load_media_image(file_path: str) -> Optional[Image.Image]:
    """미디어 노드의 file_path에서 이미지를 읽어 검색용 크기로 줄인다"""
    name = Path(file_path or "").name
    if not name:
        return None
    path = MEDIA_DIR / name
    if not path.exists():
        return None
    try:
        image = Image.open(path).convert("RGB")
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        return image
    except Exception as e:
        _log(f"[faces] {name} 을 읽지 못했습니다 ({type(e).__name__}: {e})")
        return None


def crop_face(image: Image.Image, box: dict, pad: float = CROP_PAD) -> Image.Image:
    """얼굴 하나를 잘라낸다 (비율 좌표 -> 픽셀)"""
    width, height = image.size
    return image.crop((
        max(0, int((box["Left"] - box["Width"] * pad) * width)),
        max(0, int((box["Top"] - box["Height"] * pad) * height)),
        min(width, int((box["Left"] + box["Width"] * (1 + pad)) * width)),
        min(height, int((box["Top"] + box["Height"] * (1 + pad)) * height)),
    ))


def detect_faces(image: Image.Image) -> list[dict]:
    """사진에서 얼굴을 찾는다 (왼쪽부터 정렬)

    나이·성별을 함께 받는다. 나이는 후보를 거르는 데 쓰고(위 4번), 성별은
    지금 쓰지 않는다 — 판정에 넣으면 틀렸을 때 되짚기 어려운 종류의 실수가 된다.
    """
    if not enabled():
        return []
    try:
        detail = _retry(
            lambda: _rekognition().detect_faces(
                Image={"Bytes": _to_jpeg(image)}, Attributes=["ALL"]
            ),
            "얼굴 검출",
        )["FaceDetails"]
    except Exception as e:
        _log(f"[faces] 얼굴을 찾지 못했습니다 ({type(e).__name__}: {e})")
        return []

    faces = []
    for item in detail:
        age = item.get("AgeRange") or {}
        faces.append({
            "box": item["BoundingBox"],
            "confidence": item.get("Confidence", 0.0),
            "age_low": age.get("Low"),
            "age_high": age.get("High"),
            # 등록할 때 짝을 맞추는 데만 쓴다 (scripts/enroll_faces.py).
            # 인식 판정에는 넣지 않는다 — 틀렸을 때 되짚기 어려운 종류의 실수가 된다.
            "gender": (item.get("Gender") or {}).get("Value"),
        })
    return sorted(faces, key=lambda f: f["box"]["Left"])


# --- 등록 --------------------------------------------------------------------


def enroll(person_id: str, image: Image.Image, box: dict) -> Optional[str]:
    """이 얼굴이 이 사람이라고 등록한다

    크롭 안에 얼굴이 하나인지 확인한다. 옆 사람이 함께 들어온 크롭을 등록하면
    그 사람이 이 사람으로 불리기 시작한다 — 실제로 겪은 실패다.

    한 사람에게 여러 장을 등록할 수 있다. 나이대가 다른 사진을 함께 넣으면
    아이의 인식이 좋아진다 (참조가 10대인데 사진이 2살이면 못 맞춘다).

    Returns:
        등록된 FaceId. 실패하면 None.
    """
    if not enabled() or not ensure_collection():
        return None

    person = graph_manager.get_node(person_id)
    if not person or person.get("node_type") != NodeType.PERSON:
        return None

    face = crop_face(image, box)
    if min(face.size) < MIN_FACE_PX:
        _log(f"[faces] {person_id}: 얼굴이 너무 작아 등록하지 않습니다 {face.size}")
        return None

    client = _rekognition()
    payload = _to_jpeg(face, quality=95)

    # 크롭 안에 얼굴이 하나인지 본다
    try:
        found = _retry(
            lambda: client.detect_faces(Image={"Bytes": payload}), "크롭 확인"
        )["FaceDetails"]
    except Exception as e:
        _log(f"[faces] {person_id}: 크롭 확인 실패 ({type(e).__name__})")
        return None
    if len(found) != 1:
        print(
            f"[faces] {person_id}: 크롭에 얼굴이 {len(found)}개라 등록하지 않습니다 "
            "(옆 사람이 함께 들어왔을 수 있습니다)",
            flush=True,
        )
        return None

    try:
        result = _retry(
            lambda: client.index_faces(
                CollectionId=COLLECTION_ID,
                Image={"Bytes": payload},
                ExternalImageId=person_id,
                QualityFilter="AUTO",
                DetectionAttributes=[],
                MaxFaces=1,
            ),
            f"{person_id} 등록",
        )
    except Exception as e:
        _log(f"[faces] {person_id}: 등록 실패 ({type(e).__name__}: {e})")
        return None

    records = result.get("FaceRecords") or []
    if not records:
        skipped = result.get("UnindexedFaces") or []
        reasons = [r.get("Reasons") for r in skipped]
        _log(f"[faces] {person_id}: 등록되지 않았습니다 (이유: {reasons})")
        return None

    return records[0]["Face"]["FaceId"]


def forget(person_id: str) -> int:
    """이 사람의 등록된 얼굴을 모두 지운다

    잘못 등록했을 때, 그리고 사람이 자기 얼굴을 빼 달라고 할 때 쓴다.
    등록을 지울 길이 없으면 한 번의 실수를 되돌릴 수 없다.

    Returns: 지운 얼굴 수
    """
    if not enabled():
        return 0
    client = _rekognition()
    face_ids = []
    token = None
    try:
        while True:
            kwargs = {"CollectionId": COLLECTION_ID, "MaxResults": 500}
            if token:
                kwargs["NextToken"] = token
            page = _retry(lambda: client.list_faces(**kwargs), "등록 목록 읽기")
            face_ids += [
                f["FaceId"] for f in page.get("Faces", [])
                if f.get("ExternalImageId") == person_id
            ]
            token = page.get("NextToken")
            if not token:
                break
        if not face_ids:
            return 0
        for start in range(0, len(face_ids), 100):
            batch = face_ids[start:start + 100]
            _retry(lambda: client.delete_faces(CollectionId=COLLECTION_ID, FaceIds=batch),
                   "등록 삭제")
    except Exception as e:
        _log(f"[faces] {person_id}: 등록 삭제 실패 ({type(e).__name__}: {e})")
        return 0
    return len(face_ids)


def enrolled_counts() -> dict:
    """사람별로 등록된 얼굴 수 (화면이 "등록됨"을 보여줄 수 있게)"""
    if not enabled():
        return {}
    client = _rekognition()
    counts: dict[str, int] = {}
    token = None
    try:
        while True:
            kwargs = {"CollectionId": COLLECTION_ID, "MaxResults": 500}
            if token:
                kwargs["NextToken"] = token
            page = _retry(lambda: client.list_faces(**kwargs), "등록 목록 읽기")
            for face in page.get("Faces", []):
                pid = face.get("ExternalImageId")
                if pid:
                    counts[pid] = counts.get(pid, 0) + 1
            token = page.get("NextToken")
            if not token:
                break
    except Exception as e:
        _log(f"[faces] 등록 목록을 읽지 못했습니다 ({type(e).__name__})")
        return {}
    return counts


# --- 나이로 후보 거르기 --------------------------------------------------------


def _age_at(person: dict, when: Optional[date]) -> Optional[int]:
    """그 사진을 찍을 때 이 사람이 몇 살이었나 (모르면 None)"""
    birth = person.get("birth_year")
    if not birth or not when:
        return None
    return when.year - int(birth)


def age_fits(person: dict, when: Optional[date], low, high) -> bool:
    """추정 나이 구간에 이 사람이 들어갈 수 있는가

    나이나 촬영 시점을 모르면 막지 않는다 (모르는 것으로 후보를 지우지 않는다).
    태어나기 전 사진은 확실하게 막는다 — 이것만으로도 형제 혼동이 많이 준다.
    """
    age = _age_at(person, when)
    if age is None:
        return True
    if age < 0:
        return False  # 아직 태어나지 않았다
    if low is None or high is None:
        return True
    return (age >= low - AGE_TOLERANCE) and (age <= high + AGE_TOLERANCE)


def _capture_date(media: dict) -> Optional[date]:
    raw = (media.get("exif_date") or media.get("created_at") or "")[:10]
    if len(raw) != 10:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


# --- 알아보기 ----------------------------------------------------------------


def _search(face_image: Image.Image) -> list[tuple[str, float]]:
    """얼굴 하나를 컬렉션에서 찾는다 -> [(person_id, 유사도)] 내림차순"""
    try:
        result = _retry(
            lambda: _rekognition().search_faces_by_image(
                CollectionId=COLLECTION_ID,
                Image={"Bytes": _to_jpeg(face_image, quality=95)},
                FaceMatchThreshold=0,
                MaxFaces=8,
            ),
            "얼굴 검색",
        )
    except Exception as e:
        name = type(e).__name__
        if name != "InvalidParameterException":  # 얼굴이 없는 크롭
            _log(f"[faces] 검색 실패 ({name})")
        return []

    # 같은 사람에게 여러 장이 등록돼 있으면 가장 높은 점수만 남긴다
    best: dict[str, float] = {}
    for match in result.get("FaceMatches", []):
        pid = match["Face"].get("ExternalImageId")
        if not pid:
            continue
        best[pid] = max(best.get(pid, 0.0), match["Similarity"])
    return sorted(best.items(), key=lambda kv: -kv[1])


def identify(media: dict) -> list[dict]:
    """사진에서 얼굴을 찾아 각각 누구인지 맞춘다

    Returns:
        얼굴마다 한 항목. person_id가 None이면 못 맞춘 것이다.
        [{box, age_low, age_high, person_id, similarity, reason}]
    """
    if not enabled() or not ensure_collection():
        return []

    image = load_media_image(media.get("file_path", ""))
    if image is None:
        return []

    when = _capture_date(media)
    persons = {p["id"]: p for p in graph_manager.get_persons()}

    faces = detect_faces(image)
    results: list[dict] = []
    # 얼굴마다 (사람, 점수) 후보 목록. 배정은 사진 전체를 보고 한 번에 한다.
    candidates_per_face: list[list[tuple[str, float]]] = []

    for face in faces:
        entry = {
            "box": face["box"],
            "age_low": face["age_low"],
            "age_high": face["age_high"],
            "person_id": None,
            "similarity": 0.0,
            "reason": "",
        }
        results.append(entry)

        crop = crop_face(image, face["box"])
        if min(crop.size) < MIN_FACE_PX:
            entry["reason"] = "얼굴이 너무 작습니다"
            candidates_per_face.append([])
            continue

        found = _search(crop)
        if not found:
            entry["reason"] = "등록된 얼굴 중에 없습니다"
            candidates_per_face.append([])
            continue

        # 나이가 맞지 않는 후보를 뺀다 (태어나기 전 사진 포함)
        fitting = [
            (pid, sim) for pid, sim in found
            if pid in persons
            and sim >= MATCH_THRESHOLD
            and age_fits(persons[pid], when, face["age_low"], face["age_high"])
        ]
        if not fitting:
            entry["reason"] = "나이가 맞는 후보가 없습니다"
        candidates_per_face.append(fitting)

    # 사진 전체를 보고 점수 높은 순으로 배정한다. 한 사람은 한 얼굴에만 붙는다.
    #
    # 얼굴마다 따로 "1등과 2등이 붙었으면 비운다"를 적용했더니, 딸이 여덟 장 중
    # 일곱 장에서 빠졌다 — 100 대 100 동점이었고 그 상대는 **이미 다른 얼굴에
    # 확정된 엄마**였다. 사진 안에서 이미 정해진 사람을 빼고 보면 동점이 아니다.
    order = sorted(
        ((sim, index, pid)
         for index, cands in enumerate(candidates_per_face)
         for pid, sim in cands),
        key=lambda t: -t[0],
    )
    taken_person: dict[str, int] = {}
    for sim, index, pid in order:
        if results[index]["person_id"] or pid in taken_person:
            continue
        results[index]["person_id"] = pid
        results[index]["similarity"] = round(sim, 1)
        taken_person[pid] = index

    # 배정한 뒤에 애매함을 다시 본다. 이번에는 **남은 후보**와만 견준다 —
    # 다른 얼굴이 가져간 사람은 이 얼굴의 경쟁자가 아니다.
    for index, entry in enumerate(results):
        pid = entry["person_id"]
        if not pid:
            continue
        rivals = [
            sim for other, sim in candidates_per_face[index]
            if other != pid and taken_person.get(other) in (None, index)
        ]
        best_rival = max(rivals) if rivals else 0.0
        if entry["similarity"] - best_rival < MIN_MARGIN:
            # 여기서 넣으면 틀린 이름이 붙는다. 비우는 편이 낫다.
            entry["reason"] = (
                f"두 사람이 비슷해 가릴 수 없습니다 "
                f"({entry['similarity']:.0f} · {best_rival:.0f})"
            )
            entry["person_id"] = None
            entry["similarity"] = 0.0
            taken_person.pop(pid, None)

    # 이름을 못 붙인 얼굴에는 반드시 이유가 있어야 한다. 화면이 그것을 그대로
    # 밝히기 때문이다 — 이유 없이 비어 있으면 사용자는 왜 이름이 없는지 알 수
    # 없고, 찾았지만 가리지 못한 것과 아예 못 본 것을 구분할 수 없다.
    #
    # 여기까지 이유가 비어 있는 경우는 하나다: 후보는 있었지만 그 사람을 더 잘
    # 맞는 다른 얼굴이 가져간 경우. 위 두 갈래(후보 없음·격차 부족)에서는 이미
    # 적었다.
    for index, entry in enumerate(results):
        if entry["person_id"] or entry["reason"]:
            continue
        rival_names = [
            (graph_manager.get_node(pid) or {}).get("name") or pid
            for pid, _ in candidates_per_face[index]
        ]
        entry["reason"] = (
            "다른 얼굴이 더 잘 맞아 밀렸습니다"
            + (f" ({' · '.join(rival_names[:2])})" if rival_names else "")
        )

    return results


def recognized_person_ids(media: dict) -> list[dict]:
    """알아본 사람만 골라 준다 -> [{person_id, similarity}]"""
    return [
        {"person_id": r["person_id"], "similarity": r["similarity"]}
        for r in identify(media)
        if r["person_id"]
    ]


def _to_stored(result: dict) -> dict:
    """identify 결과를 저장 모양으로 (Rekognition의 대문자 키를 걷는다)"""
    box = result.get("box") or {}
    return {
        "box": {
            "left": round(float(box.get("Left", 0)), 5),
            "top": round(float(box.get("Top", 0)), 5),
            "width": round(float(box.get("Width", 0)), 5),
            "height": round(float(box.get("Height", 0)), 5),
        },
        "person_id": result.get("person_id"),
        "similarity": result.get("similarity") or 0.0,
        "reason": result.get("reason") or "",
    }


def identify_and_store(media_id: str) -> list[dict]:
    """얼굴을 찾아 위치까지 그래프에 저장한다

    상세 화면이 사진 위에 이름을 얹으려면 위치가 필요하다. 여는 순간마다 다시
    부르면 사진 한 장에 호출이 여러 번 나가고 느리다 — 한 번 찾은 것을 들고 있는다.

    Returns: 저장된 얼굴 목록 (person_id가 None인 것도 포함 — "누군지 모르는
        얼굴이 여기 있다"도 화면이 보여줘야 하는 정보다)
    """
    media = graph_manager.get_node(media_id)
    if not media or media.get("node_type") != NodeType.MEDIA:
        return []

    stored = [_to_stored(r) for r in identify(media)]
    graph_manager.update_node(media_id, {"face_boxes": stored})
    media["face_boxes"] = stored
    return stored


def stored_boxes(media: dict) -> list[dict]:
    """저장해 둔 얼굴 위치 (없으면 빈 목록 — 다시 찾지 않는다)

    화면이 여는 것만으로 유료 호출이 일어나지 않게 한다. 찾는 것은 업로드와
    초안을 만들 때, 그리고 사람이 직접 다시 찾기를 눌렀을 때만이다.
    """
    return list(media.get("face_boxes") or [])
