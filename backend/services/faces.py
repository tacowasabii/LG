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
    client = _rekognition()
    try:
        _retry(lambda: _rekognition().create_collection(CollectionId=COLLECTION_ID),
               "컬렉션 만들기")
        print(f"[faces] 컬렉션을 만들었습니다: {COLLECTION_ID}", flush=True)
        return True
    except client.exceptions.ResourceAlreadyExistsException:
        return True
    except Exception as e:
        print(f"[faces] 컬렉션을 준비하지 못했습니다 ({type(e).__name__}: {e})", flush=True)
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
                print(f"[faces] {what} 실패 ({name}) — {attempts}번 시도했습니다", flush=True)
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
        print(f"[faces] {name} 을 읽지 못했습니다 ({type(e).__name__}: {e})", flush=True)
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
        print(f"[faces] 얼굴을 찾지 못했습니다 ({type(e).__name__}: {e})", flush=True)
        return []

    faces = []
    for item in detail:
        age = item.get("AgeRange") or {}
        faces.append({
            "box": item["BoundingBox"],
            "confidence": item.get("Confidence", 0.0),
            "age_low": age.get("Low"),
            "age_high": age.get("High"),
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
        print(f"[faces] {person_id}: 얼굴이 너무 작아 등록하지 않습니다 {face.size}", flush=True)
        return None

    client = _rekognition()
    payload = _to_jpeg(face, quality=95)

    # 크롭 안에 얼굴이 하나인지 본다
    try:
        found = _retry(
            lambda: client.detect_faces(Image={"Bytes": payload}), "크롭 확인"
        )["FaceDetails"]
    except Exception as e:
        print(f"[faces] {person_id}: 크롭 확인 실패 ({type(e).__name__})", flush=True)
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
        print(f"[faces] {person_id}: 등록 실패 ({type(e).__name__}: {e})", flush=True)
        return None

    records = result.get("FaceRecords") or []
    if not records:
        skipped = result.get("UnindexedFaces") or []
        reasons = [r.get("Reasons") for r in skipped]
        print(f"[faces] {person_id}: 등록되지 않았습니다 (이유: {reasons})", flush=True)
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
        print(f"[faces] {person_id}: 등록 삭제 실패 ({type(e).__name__}: {e})", flush=True)
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
        print(f"[faces] 등록 목록을 읽지 못했습니다 ({type(e).__name__})", flush=True)
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
            print(f"[faces] 검색 실패 ({name})", flush=True)
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

    for face in faces:
        entry = {
            "box": face["box"],
            "age_low": face["age_low"],
            "age_high": face["age_high"],
            "person_id": None,
            "similarity": 0.0,
            "reason": "",
        }
        crop = crop_face(image, face["box"])
        if min(crop.size) < MIN_FACE_PX:
            entry["reason"] = "얼굴이 너무 작습니다"
            results.append(entry)
            continue

        candidates = _search(crop)
        if not candidates:
            entry["reason"] = "등록된 얼굴 중에 없습니다"
            results.append(entry)
            continue

        # 나이가 맞지 않는 후보를 뺀다 (태어나기 전 사진 포함)
        fitting = [
            (pid, sim) for pid, sim in candidates
            if pid in persons and age_fits(persons[pid], when, face["age_low"], face["age_high"])
        ]
        if not fitting:
            entry["reason"] = "나이가 맞는 후보가 없습니다"
            results.append(entry)
            continue

        top_id, top_sim = fitting[0]
        runner_sim = fitting[1][1] if len(fitting) > 1 else 0.0

        if top_sim < MATCH_THRESHOLD:
            entry["reason"] = f"닮은 정도가 낮습니다 ({top_sim:.0f}점)"
        elif top_sim - runner_sim < MIN_MARGIN:
            # 여기서 넣으면 틀린 이름이 붙는다. 실측에서 아이가 이 구간에 걸렸다.
            entry["reason"] = f"두 사람이 비슷해 가릴 수 없습니다 ({top_sim:.0f} · {runner_sim:.0f})"
        else:
            entry["person_id"] = top_id
            entry["similarity"] = round(top_sim, 1)

        results.append(entry)

    # 한 사람이 한 사진에서 두 얼굴에 붙지 않게 한다 (점수 높은 쪽만 남긴다)
    taken: dict[str, int] = {}
    for index, entry in enumerate(results):
        pid = entry["person_id"]
        if not pid:
            continue
        previous = taken.get(pid)
        if previous is None:
            taken[pid] = index
            continue
        if entry["similarity"] > results[previous]["similarity"]:
            results[previous]["person_id"] = None
            results[previous]["reason"] = "같은 사람이 더 잘 맞는 얼굴이 있습니다"
            taken[pid] = index
        else:
            entry["person_id"] = None
            entry["reason"] = "같은 사람이 더 잘 맞는 얼굴이 있습니다"

    return results


def recognized_person_ids(media: dict) -> list[dict]:
    """알아본 사람만 골라 준다 -> [{person_id, similarity}]"""
    return [
        {"person_id": r["person_id"], "similarity": r["similarity"]}
        for r in identify(media)
        if r["person_id"]
    ]
