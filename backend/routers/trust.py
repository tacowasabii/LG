"""Trust Router — Memory Trust Harness 리포트

채점은 LLM 호출이 20번 들어가 몇 분 걸린다. 그래서 실행과 조회를 나눈다.
발표 중에 눌러서 기다리는 화면이 되지 않게, 미리 돌려 저장한 리포트를 읽는다.
"""

from fastapi import APIRouter, HTTPException, Query

from backend.services import trust_harness

router = APIRouter()


@router.get("/report")
async def get_report():
    """저장된 채점 리포트. 아직 돌린 적이 없으면 비어 있다고 알린다."""
    report = trust_harness.load_report()
    if not report:
        return {
            "ran": False,
            "message": "아직 채점하지 않았습니다. python scripts/run_trust_harness.py 로 실행하세요.",
            "question_count": len(trust_harness.load_goldset()),
        }
    return {"ran": True, **report}


@router.post("/run")
async def run_harness(limit: int = Query(None, description="정답표 앞에서 N문항만")):
    """채점 실행 (LLM 호출 포함, 수 분 소요)"""
    goldset = trust_harness.load_goldset()
    if not goldset:
        raise HTTPException(status_code=400, detail="정답표(data/goldset.json)가 없습니다.")

    report = await trust_harness.run(limit=limit)
    return {"ran": True, **report}
