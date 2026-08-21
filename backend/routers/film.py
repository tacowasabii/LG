"""Film Router — Memory Film 구성과 기념일 큐레이션"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.config import MOTION_AUTOGEN_NEW_ONLY

from backend.models.schemas import (
    AnniversaryItem,
    FilmRequest,
    FilmResponse,
    MotionReady,
    MotionStatusResponse,
)
from backend.services import film_composer, motion_clips
from backend.services.permissions import current_actor

router = APIRouter()


@router.post("", response_model=FilmResponse)
async def compose_film(
    request: FilmRequest,
    actor: Optional[dict] = Depends(current_actor),
):
    """추억 하나를 30~60초 이야기로 구성

    장면마다 원본 기록과 적용된 효과를 함께 내려보낸다. 화면이 그것을 감추지
    않고 표시하는 것이 기획안의 진정성 원칙이다.
    """
    board = await film_composer.compose(
        request.event_id,
        length_sec=request.length_sec,
        audience=request.audience,
        viewer_id=actor["id"] if actor else None,
    )

    if not board:
        raise HTTPException(
            status_code=404,
            detail="이 추억으로는 아직 이야기를 만들 수 없습니다. 사진이나 영상을 먼저 연결해주세요.",
        )

    return FilmResponse(**board)


@router.get("/motion", response_model=MotionStatusResponse)
async def motion_status(media_ids: str = ""):
    """맡긴 미세 모션 클립이 준비됐는지

    화면이 주기적으로 묻는다. POST /api/film 을 다시 부르지 않는 이유는 그쪽이
    내레이션을 위해 모델을 호출하기 때문이다 — 되묻는 값이 응답 시간과 돈으로
    돌아온다. 여기는 파일 목록만 읽는다.

        GET /api/film/motion?media_ids=E01_001,E01_002
    """
    wanted = [x.strip() for x in media_ids.split(",") if x.strip()]
    clips = motion_clips.manifest()
    failed = motion_clips.failures()
    in_flight = set(motion_clips.pending_ids())

    if wanted:
        clips = {k: v for k, v in clips.items() if k in wanted}
        pending = [media_id for media_id in wanted if media_id in in_flight]
        failed = {k: v for k, v in failed.items() if k in wanted}
    else:
        pending = sorted(in_flight)

    ready = {
        media_id: MotionReady(
            file=clip["file"],
            poster=clip.get("poster"),
            # 라벨은 서버가 정한다 — 화면이 조립하면 갈라진다
            label=film_composer.generated_label(clip),
        )
        for media_id, clip in clips.items()
        if clip.get("file")
    }

    return MotionStatusResponse(
        ready=ready,
        pending=pending,
        failed=failed,
        enabled=motion_clips.enabled(),
        attempts_left=motion_clips.attempts_left(),
        new_events_only=MOTION_AUTOGEN_NEW_ONLY,
    )


@router.get("/anniversaries", response_model=list[AnniversaryItem])
async def list_anniversaries(limit: int = 4):
    """다가오는 기념일 — TV 대기화면이 먼저 말을 걸 근거"""
    return [AnniversaryItem(**item) for item in film_composer.anniversaries(limit=limit)]
