"""Memory Trust Harness 실행 (기획안 05장)

    python scripts/run_trust_harness.py            # 정답표 전체
    python scripts/run_trust_harness.py --limit 5  # 앞 5문항만 (빠른 확인)

정답표(data/goldset.json)를 돌려 근거 회수·정직성·귀속을 채점하고, 그래프와
파일 정합성까지 함께 본 뒤 data/trust_report.json에 저장한다.
화면(/trust)은 이 파일을 읽는다.

질의 지표는 LLM 호출이 문항마다 한 번씩 들어간다. 추론 모드에서는 문항당
10초 가까이 걸리므로 전체 실행에 몇 분을 잡아야 한다.
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.services import trust_harness  # noqa: E402


def _fmt(score):
    return "미측정" if score is None else f"{score:.1f}"


async def main(limit: int | None) -> int:
    goldset = trust_harness.load_goldset()
    if not goldset:
        print("정답표(data/goldset.json)가 없습니다.")
        return 1

    total = len(goldset[:limit]) if limit else len(goldset)
    print(f"정답표 {total}문항으로 채점합니다. LLM 호출이 있어 시간이 걸립니다.\n")

    report = await trust_harness.run(limit=limit)

    print("지표")
    for metric in report["metrics"]:
        print(f"  {metric['label']:<20} {_fmt(metric['score']):>7}    {metric['description']}")

    counts = report["counts"]
    print(
        f"\n문항  통과 {counts['pass']} · 부분 {counts['partial']} · 실패 {counts['fail']}"
        f"  (총 {counts['total']})"
    )

    failed = [r for r in report["questions"] if r["verdict"] != "pass"]
    if failed:
        print("\n통과하지 못한 문항")
        for row in failed:
            print(f"  [{row['verdict']}] {row['query']}")
            print(f"         나와야 할 근거: {row['expected']}")
            print(f"         읽은 기록:     {row['actual']}  ({row['note']})")
            if row["unsupported_persons"]:
                print(f"         근거 없이 언급한 인물: {', '.join(row['unsupported_persons'])}")

    details = report["details"]
    if details["relations"]["missing_count"]:
        print(f"\n빠진 관계 {details['relations']['missing_count']}개 (앞 20개만 리포트에 담김)")
    if details["media_integrity"]["violation_count"]:
        print(f"Film 효과 위반 {details['media_integrity']['violation_count']}건")
    if details["asset_integrity"]["missing_file_count"]:
        print(f"파일이 없는 미디어 {details['asset_integrity']['missing_file_count']}개")
    if details["asset_integrity"]["orphan_edge_count"]:
        print(f"고아 엣지 {details['asset_integrity']['orphan_edge_count']}개")

    if not report["llm_enabled"]:
        print("\n주의: LLM 키가 없어 시뮬레이션 응답으로 채점했습니다. 실제 품질이 아닙니다.")

    print(f"\n리포트 저장: {trust_harness.REPORT_FILE}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="앞 N문항만 채점")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.limit)))
