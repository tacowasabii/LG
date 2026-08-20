from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import (
    ALLOWED_ORIGINS,
    ALLOWED_ORIGIN_REGEX,
    DEV_ORIGINS,
    MEDIA_DIR,
    STATE_DIR,
)
from backend.services import llm_client
from backend.services.graph_manager import graph_manager
from backend.routers import (
    media, graph, chat, interview, memories, tv, film, trust, family, export,
)

# 프로세스가 언제 떴는지. 배포가 실제로 새 컨테이너로 갈렸는지 밖에서 구분하려면
# 이게 필요하다 — 재시작이 안 된 채로 파일이 남아 있는 것과, 재시작 후에도 남아
# 있는 것은 전혀 다른 이야기이고, 후자만 볼륨이 붙었다는 증거가 된다.
BOOTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="LG HomeStory",
    description="사람과 사건의 기억을 연결하고 대화할 수 있는 AI Native 서비스",
    version="0.1.0",
)

# CORS — 개발 서버 + 배포된 프론트(ALLOWED_ORIGINS) + Vercel 프리뷰(정규식)
# 배포 주소를 여기 넣지 않으면 브라우저가 요청을 막아 화면이 빈 채로 뜬다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS + ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    # X-Viewer-Id를 포함해 전부 허용한다
    allow_headers=["*"],
)

# Serve uploaded media files
app.mount("/media-files", StaticFiles(directory=str(MEDIA_DIR)), name="media-files")

# Register routers
app.include_router(media.router, prefix="/api/media", tags=["Media"])
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(interview.router, prefix="/api/interview", tags=["Interview"])
app.include_router(memories.router, prefix="/api/memories", tags=["Memories"])
app.include_router(tv.router, prefix="/api/tv", tags=["TV"])
app.include_router(film.router, prefix="/api/film", tags=["Film"])
app.include_router(trust.router, prefix="/api/trust", tags=["Trust"])
app.include_router(family.router, prefix="/api/family", tags=["Family"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])


@app.get("/api/health")
async def health_check():
    """살아있는지 + 무엇에 기대어 사는지

    배포에서 저장소를 잘못 붙이면 앱은 정상으로 보이고 데이터만 조용히 사라진다.
    (볼륨 없는 컨테이너에 사진을 올리면 재배포 때 없어진다.) 밖에서 확인할 수
    있어야 해서 저장소 종류와 상태 디렉터리를 함께 알린다.

    접속 문자열은 자격증명이 있으므로 내보내지 않는다 — 종류만 알린다.
    """
    return {
        "status": "ok",
        "service": "LG HomeStory",
        "store": "postgres" if type(graph_manager).__name__ == "PostgresGraphStore" else "json",
        "state_dir": str(STATE_DIR),
        "media_dir_exists": MEDIA_DIR.exists(),
        # 용도별로 어디를 부르는지. 키가 없으면 "off"이고, 그때 답변은 모델 없이
        # 규칙으로 만들어진다 — 화면은 정상으로 보이므로 밖에서 구분이 필요하다.
        "llm": {
            purpose or "answer": (
                llm_client.provider_for(purpose) if llm_client.is_enabled(purpose) else "off"
            )
            for purpose in (None, "plan", "extract")
        },
        "booted_at": BOOTED_AT.isoformat(),
        "uptime_sec": round((datetime.now(timezone.utc) - BOOTED_AT).total_seconds(), 1),
    }
