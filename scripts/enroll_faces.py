"""가족 얼굴 등록 (Amazon Rekognition 컬렉션 만들기)

    python scripts/enroll_faces.py --dry-run     # 무엇을 등록할지만 본다 (검출 호출만)
    python scripts/enroll_faces.py              # 실제로 등록한다
    python scripts/enroll_faces.py --reset      # 전부 지우고 다시 등록한다
    python scripts/enroll_faces.py --list       # 지금 누가 몇 장 등록돼 있나

얼굴 인식이 동작하려면 "이 얼굴이 이 사람"이라는 참조가 먼저 있어야 한다. 그런데
그래프에는 사진마다 "누가 있다"만 있고 어느 얼굴이 누구인지는 없다.

그 대응을 **성별과 나이로** 만든다. 호칭에서 성별을 읽어 사람을 나누고, 같은 성별
안에서 촬영 연도 - birth_year로 계산한 나이 순서를 Rekognition 추정 나이 순서와
맞춘다.

    E03_003 (2006년)
      남자  6세 아들 · 36세 아빠      추정 2-6 · 41-49
      여자  10세 딸 · 33세 엄마       추정 8-14 · 33-41    -> 순서가 그대로 맞는다

**나이만으로 맞추면 안 된다.** 처음에 성별을 빼고 3년 간격만 보게 했더니 2010년
사진에서 아빠(40세)와 엄마(37세)가 뒤집혀 등록됐다. 그 뒤 두 사람이 서로 100점으로
나와서, 1·2등 격차가 0이 되어 인식이 통째로 애매해졌다 — 맞춤 22 / 놓침 17이었다.
Rekognition의 어른 나이 추정 오차가 ±5~8년이라 3년 차이는 가릴 수 없다.

그래서 성별로 먼저 나누고, 같은 성별 안에서는 8년 이상 벌어져 있을 때만 쓴다.
얼굴 수가 태그 수와 다르거나 검출된 성별 구성이 태그와 다른 사진은 건너뛴다.

한 사람에게 한 장만 있으면 다른 나이대에서 못 맞추므로, 되는 사진은 모두 등록해
연령대를 넓힌다.

돈이 드는 호출이다 (검출·등록 각 1건, 사진당 몇 센트 수준). 자동으로 돌지 않고
배포에도 들어가지 않는다. 컬렉션은 AWS 계정에 남는다.

필요한 것: .env의 AWS 자격증명 (.env.example 참고)
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.models.graph_models import MediaType  # noqa: E402
from backend.services import faces  # noqa: E402
from backend.services.graph_manager import graph_manager  # noqa: E402

# 같은 성별 안에서 나이가 이보다 가까우면 순서를 믿지 않는다.
#
# 실측: 3년으로 두었더니 2010년 사진의 아빠(40세)와 엄마(37세)가 뒤집혀 등록됐고,
# 그 뒤 두 사람이 서로 100점으로 나와 인식이 통째로 애매해졌다. Rekognition의
# 어른 나이 추정 오차는 ±5~8년이라 3년 차이는 가릴 수 없다.
MIN_AGE_GAP = 8

# 호칭에서 성별을 읽는다. 나이만으로 순서를 매기면 부부가 뒤집힌다.
# 판정에는 쓰지 않는다 — 등록할 때 짝을 맞추는 데만 쓴다.
MALE_TERMS = ("아빠", "아버지", "아들", "할아버지", "오빠", "형", "남동생", "손자", "삼촌")
FEMALE_TERMS = ("엄마", "어머니", "딸", "할머니", "누나", "언니", "여동생", "손녀", "이모", "고모")


def expected_gender(person: dict) -> str | None:
    """호칭으로 성별을 추정한다 (모르면 None)"""
    relation = person.get("relation") or ""
    if any(t in relation for t in MALE_TERMS):
        return "Male"
    if any(t in relation for t in FEMALE_TERMS):
        return "Female"
    return None


def capture_year(media: dict) -> int | None:
    raw = (media.get("exif_date") or media.get("created_at") or "")[:10]
    try:
        return date.fromisoformat(raw).year
    except ValueError:
        return None


def plan_photo(media: dict, persons: dict) -> list[tuple[str, dict]] | None:
    """이 사진에서 (person_id, 얼굴박스) 대응을 만든다. 못 만들면 None

    나이 순서로 맞춘다. 검출된 얼굴 수와 태그 수가 같아야 하고, 태그된 사람들의
    나이가 서로 충분히 벌어져 있어야 한다.
    """
    tagged = [p for p in (media.get("detected_faces") or []) if p in persons]
    if len(tagged) < 1:
        return None

    year = capture_year(media)
    if not year:
        return None

    # 성별로 먼저 나누고, 그 안에서 나이 순으로 맞춘다.
    # 성별을 모르는 사람이 있으면 이 사진을 쓰지 않는다 (뒤집힐 수 있다).
    groups: dict[str, list[tuple[int, str]]] = {}
    for pid in tagged:
        birth = persons[pid].get("birth_year")
        sex = expected_gender(persons[pid])
        if not birth or not sex:
            return None
        groups.setdefault(sex, []).append((year - int(birth), pid))

    for people in groups.values():
        people.sort()
        for i in range(len(people) - 1):
            if people[i + 1][0] - people[i][0] < MIN_AGE_GAP:
                return None

    image = faces.load_media_image(media.get("file_path", ""))
    if image is None:
        return None

    detected = faces.detect_faces(image)
    usable = [
        f for f in detected
        if min(faces.crop_face(image, f["box"]).size) >= faces.MIN_FACE_PX
        and f["age_low"] is not None and f.get("gender")
    ]
    if len(usable) != len(tagged):
        return None

    pairs = []
    for sex, people in groups.items():
        same = sorted(
            (f for f in usable if f["gender"] == sex),
            key=lambda f: (f["age_low"] + f["age_high"]) / 2,
        )
        if len(same) != len(people):
            return None  # 검출된 성별 구성이 태그와 다르다
        for (age, pid), face in zip(people, same):
            if not faces.age_fits(persons[pid], date(year, 7, 1), face["age_low"], face["age_high"]):
                return None
            pairs.append((pid, face))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="가족 얼굴 등록")
    parser.add_argument("--dry-run", action="store_true", help="등록하지 않고 계획만 본다")
    parser.add_argument("--reset", action="store_true", help="기존 등록을 지우고 다시 한다")
    parser.add_argument("--list", action="store_true", help="지금 등록 상태만 본다")
    parser.add_argument("--limit", type=int, default=None, help="앞 N장만")
    args = parser.parse_args()

    if not faces.enabled():
        print(
            "AWS 자격증명이 없습니다. .env에 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY 를\n"
            "넣으세요 (.env.example 참고). 자격증명이 없으면 얼굴 인식은 조용히 꺼지고,\n"
            "사람이 직접 지목하는 길은 그대로 동작합니다."
        )
        return 1

    persons = {p["id"]: p for p in graph_manager.get_persons()}
    names = {pid: p.get("name", pid) for pid, p in persons.items()}

    if args.list:
        counts = faces.enrolled_counts()
        if not counts:
            print("등록된 얼굴이 없습니다.")
            return 0
        print("등록 상태")
        for pid, n in sorted(counts.items()):
            print(f"  {pid} {names.get(pid, pid):8} {n}장")
        return 0

    if args.reset and not args.dry_run:
        removed = sum(faces.forget(pid) for pid in persons)
        print(f"기존 등록 {removed}장을 지웠습니다.\n")

    photos = [
        n for n in graph_manager.get_media_nodes()
        if n.get("media_type") == MediaType.PHOTO
    ]
    photos.sort(key=lambda n: n.get("exif_date") or "")
    if args.limit:
        photos = photos[: args.limit]

    print(f"사진 {len(photos)}장을 봅니다 (나이 순서로 얼굴과 인물을 짝짓습니다)\n")

    enrolled: dict[str, int] = {}
    skipped = 0

    for media in photos:
        pairs = plan_photo(media, persons)
        if not pairs:
            skipped += 1
            continue

        year = capture_year(media)
        label = ", ".join(
            f"{names[pid]}({year - int(persons[pid]['birth_year'])}세)" for pid, _ in pairs
        )
        print(f"  {media['id']} ({year}) -> {label}")

        if args.dry_run:
            continue

        image = faces.load_media_image(media.get("file_path", ""))
        if image is None:
            continue
        for pid, face in pairs:
            if faces.enroll(pid, image, face["box"]):
                enrolled[pid] = enrolled.get(pid, 0) + 1

    print()
    print(f"짝지은 사진 {len(photos) - skipped}장 · 건너뛴 사진 {skipped}장")
    if args.dry_run:
        print("--dry-run 이라 등록하지 않았습니다.")
        return 0

    if not enrolled:
        print("등록된 얼굴이 없습니다. 나이가 붙어 있거나 얼굴 수가 맞지 않았습니다.")
        return 1

    print("등록 결과")
    for pid, n in sorted(enrolled.items()):
        print(f"  {pid} {names.get(pid, pid):8} {n}장")
    missing = [names[p] for p in persons if p not in enrolled]
    if missing:
        print(f"\n등록되지 않은 사람: {', '.join(missing)}")
        print("이 사람들은 사진에서 자동으로 알아보지 못합니다. 화면에서 직접 지목하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
