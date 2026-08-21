"""Memory Trust Harness (기획안 05장)

기획안이 평가 항목으로 직접 내건 약속이다. 여기서 재는 것은 여섯 가지다.

  Evidence Recall     질문마다 나와야 할 근거가 실제로 나왔는가
  Grounding Honesty   기록에 없는 것을 없다고 말하는가
  Attribution Safety  화면에 보이는 근거에 없는 인물을 답변이 이름으로 단정하지 않는가
  Relation Accuracy   그래프 관계가 정답(data/metadata)과 일치하는가
  Media Integrity     Film 효과가 허용 범위(패닝·줌·미세 움직임)를 넘지 않는가
  Asset Integrity     원본 파일과 그래프 참조가 어긋난 곳이 없는가

측정할 수 없는 것은 재지 않는다. "감동적인가", "자연스러운가"는 여기서 다루지
않는다. LLM으로 LLM을 채점하지도 않는다 — 답이 맞는지는 정답표로만 본다.

앞의 세 지표는 실제 질의를 돌리므로 LLM 호출이 있고 몇 분 걸린다.
뒤의 세 지표는 그래프와 파일만 보므로 즉시 끝난다.

    python scripts/run_trust_harness.py          # 전체 실행 후 리포트 저장
    GET  /api/trust/report                       # 저장된 리포트 조회
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import (
    GOLDSET_FILE,
    GRAPH_FILE,
    MEDIA_DIR,
    METADATA_DIR,
    TRUST_REPORT_FILE as REPORT_FILE,
)
from backend.models.graph_models import MediaType, NodeType, RelationType
from backend.services import film_composer, llm_client
from backend.services.chat_engine import process_chat
from backend.services.graph_manager import graph_manager


# --- 정답표 -----------------------------------------------------------------


def load_goldset() -> list[dict]:
    if not GOLDSET_FILE.exists():
        return []
    with open(GOLDSET_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("questions", [])


# --- 질의 기반 지표 ----------------------------------------------------------


async def score_questions(limit: Optional[int] = None) -> dict:
    """정답표를 돌려 근거 회수·정직성·귀속을 채점한다"""
    questions = load_goldset()
    if limit:
        questions = questions[:limit]

    person_names = {
        node["id"]: node.get("name", "")
        for node in graph_manager.get_persons()
        if node.get("name")
    }

    rows = []
    for question in questions:
        result = await process_chat(question["query"])
        source_ids = [s.id for s in result["sources"]]
        answer = result["answer"]
        confidence = result["confidence"]

        expected = question.get("expect_any") or []
        no_record = bool(question.get("no_record"))

        if no_record:
            # 없는 것을 물었을 때 "확인된 기록"이라고 말하면 안 된다
            passed = confidence != "confirmed"
            verdict = "pass" if passed else "fail"
            note = (
                "기록 없음을 지켰다"
                if passed
                else "근거가 없는데 확인된 기록으로 표시했다"
            )
        else:
            hit = [node_id for node_id in expected if node_id in source_ids]
            if hit:
                verdict = "pass"
                note = "기대 근거 " + ", ".join(hit)
            elif source_ids:
                verdict = "partial"
                note = "다른 근거만 붙었다: " + ", ".join(source_ids[:3])
            else:
                verdict = "fail"
                note = "근거가 없다"

        # 답변이 이름을 댔지만 화면의 근거 목록에는 없는 인물.
        # 검색 문맥에는 있었을 수 있다 — 근거 뱃지는 상위 5개만 보여주기 때문이다.
        # 그래도 감점한다: 화면에 근거가 없으면 사용자는 확인할 방법이 없다.
        unsupported = [
            name
            for person_id, name in person_names.items()
            if name and name in answer and person_id not in source_ids
        ]

        rows.append({
            "id": question.get("id", ""),
            "query": question["query"],
            "expected": "기록 없음" if no_record else ", ".join(expected),
            # 화면 칼럼 "답변이 읽은 기록". 질문이 사실이라는 증거가 아니라 그 답을 쓸
            # 때 문맥으로 들어간 노드다. 없는 것을 물어도 검색은 가장 가까운 것을
            # 돌려주므로 이 목록은 비지 않는다 — no_record 판정을 여기서 하지 않는
            # 이유다 (confidence로 본다).
            "actual": ", ".join(source_ids) or "근거 없음",
            "confidence": confidence,
            "verdict": verdict,
            "note": note,
            "unsupported_persons": unsupported,
        })

    graded = [r for r in rows if r["expected"] != "기록 없음"]
    honesty_rows = [r for r in rows if r["expected"] == "기록 없음"]

    recall = _ratio([r["verdict"] == "pass" for r in graded])
    honesty = _ratio([r["verdict"] == "pass" for r in honesty_rows])
    attribution = _ratio([not r["unsupported_persons"] for r in rows])

    return {
        "rows": rows,
        "metrics": {
            "evidence_recall": recall,
            "grounding_honesty": honesty,
            "attribution_safety": attribution,
        },
        "counts": {
            "total": len(rows),
            "graded": len(graded),
            "no_record": len(honesty_rows),
            "pass": sum(1 for r in rows if r["verdict"] == "pass"),
            "partial": sum(1 for r in rows if r["verdict"] == "partial"),
            "fail": sum(1 for r in rows if r["verdict"] == "fail"),
        },
        "llm_enabled": llm_client.is_enabled(),
    }


# --- 그래프·파일 기반 지표 ---------------------------------------------------


def score_relations() -> dict:
    """그래프 관계가 정답 메타데이터와 일치하는지

    시드 스크립트가 만든 그래프를 원본 메타데이터와 다시 맞춰 본다.
    업로드·인터뷰로 그래프가 자란 뒤에도 원래 관계가 남아 있는지 보는 검사다.
    """
    expected: set[tuple[str, str, str]] = set()

    media_file = METADATA_DIR / "media.json"
    memories_file = METADATA_DIR / "memories.json"

    if media_file.exists():
        with open(media_file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                expected.add((item["media_id"], item["event_id"], RelationType.CAPTURED_DURING))
                for person_id in item.get("people", []):
                    expected.add((item["media_id"], person_id, RelationType.DEPICTS))
                    expected.add((person_id, item["event_id"], RelationType.PARTICIPATED_IN))

    if memories_file.exists():
        with open(memories_file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                expected.add((item["memory_id"], item["event_id"], RelationType.ABOUT))
                expected.add((item["speaker"], item["memory_id"], RelationType.REMEMBERS))

    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in graph_manager.get_all_edges()
    }

    missing = sorted(expected - actual)
    found = len(expected & actual)

    return {
        "expected": len(expected),
        "found": found,
        "missing": [
            {"source": s, "target": t, "relation": r} for s, t, r in missing[:20]
        ],
        "missing_count": len(missing),
        "accuracy": _ratio([True] * found + [False] * len(missing)),
    }


async def score_media_integrity() -> dict:
    """Film이 허용된 움직임만 쓰는지, 원본 영상을 건드리지 않는지"""
    checked = 0
    violations = []

    for event in graph_manager.get_events():
        board = await film_composer.compose(event["id"])
        if not board:
            continue

        for scene in board["scenes"]:
            checked += 1
            media = graph_manager.get_node(scene["media_id"]) or {}
            is_video = media.get("media_type") == MediaType.VIDEO

            for effect in scene["ai_effects"]:
                if effect not in film_composer.ALLOWED_EFFECTS:
                    violations.append({
                        "event_id": event["id"],
                        "media_id": scene["media_id"],
                        "reason": "허용 목록에 없는 효과: " + effect,
                    })

            if is_video and scene["ai_effects"]:
                violations.append({
                    "event_id": event["id"],
                    "media_id": scene["media_id"],
                    "reason": "원본 영상에 효과가 붙었다",
                })

            if not scene["source_label"]:
                violations.append({
                    "event_id": event["id"],
                    "media_id": scene["media_id"],
                    "reason": "출처 문구가 없다",
                })

    return {
        "scenes_checked": checked,
        "violations": violations[:20],
        "violation_count": len(violations),
        "score": _ratio([True] * (checked - len(violations)) + [False] * len(violations)),
    }


def score_asset_integrity() -> dict:
    """원본 파일과 그래프 참조가 어긋난 곳

    삭제가 파생물까지 전파되지 않으면 여기서 고아 참조로 드러난다.
    (기획안 08장 "삭제·이관" 원칙의 최소 검사)
    """
    orphan_edges = []
    missing_files = []

    node_ids = {node["id"] for node in graph_manager.get_all_nodes()}
    for edge in graph_manager.get_all_edges():
        if edge["source"] not in node_ids or edge["target"] not in node_ids:
            orphan_edges.append(edge)

    for media in graph_manager.get_media_nodes():
        path = media.get("file_path") or ""
        if not path.startswith("/media-files/"):
            continue
        if not (MEDIA_DIR / Path(path).name).exists():
            missing_files.append({"media_id": media["id"], "file_path": path})

    total = len(graph_manager.get_media_nodes())
    return {
        "media_total": total,
        "orphan_edges": orphan_edges[:20],
        "orphan_edge_count": len(orphan_edges),
        "missing_files": missing_files[:20],
        "missing_file_count": len(missing_files),
        "score": _ratio(
            [True] * (total - len(missing_files)) + [False] * len(missing_files)
        ),
    }


# --- 실행 --------------------------------------------------------------------


async def run(limit: Optional[int] = None) -> dict:
    """전체 채점. 질의 지표는 LLM 호출이 있어 몇 분 걸린다."""
    questions = await score_questions(limit=limit)
    relations = score_relations()
    media = await score_media_integrity()
    assets = score_asset_integrity()

    graph_nodes = len(graph_manager.get_all_nodes())
    graph_edges = len(graph_manager.get_all_edges())

    report = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "graph": {"nodes": graph_nodes, "edges": graph_edges, "file": str(GRAPH_FILE.name)},
        "llm_enabled": questions["llm_enabled"],
        "metrics": [
            {
                "key": "evidence_recall",
                "label": "Evidence Recall",
                "score": questions["metrics"]["evidence_recall"],
                "description": "질문마다 나와야 할 근거가 실제로 나왔는가",
                "method": f"정답표 {questions['counts']['graded']}문항의 기대 근거를 답변 소스와 대조",
            },
            {
                "key": "grounding_honesty",
                "label": "Grounding Honesty",
                "score": questions["metrics"]["grounding_honesty"],
                "description": "기록에 없는 것을 없다고 말하는가",
                "method": f"기록 없는 질문 {questions['counts']['no_record']}문항에서 '확인된 기록' 표시 여부",
            },
            {
                "key": "attribution_safety",
                "label": "Attribution Safety",
                "score": questions["metrics"]["attribution_safety"],
                "description": "화면에 보이는 근거에 없는 인물을 이름으로 단정하지 않는가",
                "method": (
                    "답변에 등장한 인물명이 화면에 노출되는 근거 목록에 있는지 검사. "
                    "검색 문맥에는 있었어도 근거로 보여주지 않았다면 감점한다"
                ),
            },
            {
                "key": "relation_accuracy",
                "label": "Relation Accuracy",
                "score": relations["accuracy"],
                "description": "그래프 관계가 정답 메타데이터와 일치하는가",
                "method": f"기대 관계 {relations['expected']}개와 실제 엣지 대조",
            },
            {
                "key": "media_integrity",
                "label": "Media Integrity",
                "score": media["score"],
                "description": "Film 효과가 허용 범위를 넘지 않는가",
                "method": f"장면 {media['scenes_checked']}개의 효과·출처 검사",
            },
            {
                "key": "asset_integrity",
                "label": "Asset Integrity",
                "score": assets["score"],
                "description": "원본 파일과 그래프 참조가 어긋난 곳이 없는가",
                "method": f"미디어 {assets['media_total']}개의 파일 존재와 고아 엣지 검사",
            },
        ],
        "questions": questions["rows"],
        "counts": questions["counts"],
        "details": {
            "relations": relations,
            "media_integrity": media,
            "asset_integrity": assets,
        },
    }

    save_report(report)
    return report


def save_report(report: dict) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def load_report() -> Optional[dict]:
    if not REPORT_FILE.exists():
        return None
    with open(REPORT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _ratio(flags: list[bool]) -> Optional[float]:
    """비율을 0~100으로. 잴 것이 없으면 None (0점과 구분한다)"""
    if not flags:
        return None
    return round(sum(1 for f in flags if f) / len(flags) * 100, 1)
