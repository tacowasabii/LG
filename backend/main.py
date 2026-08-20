from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import (
    ALLOWED_ORIGINS,
    ALLOWED_ORIGIN_REGEX,
    DEV_ORIGINS,
    MEDIA_DIR,
)
from backend.routers import (
    media, graph, chat, interview, gaps, tv, film, trust, family, export,
)

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
app.include_router(gaps.router, prefix="/api/gaps", tags=["Gaps"])
app.include_router(tv.router, prefix="/api/tv", tags=["TV"])
app.include_router(film.router, prefix="/api/film", tags=["Film"])
app.include_router(trust.router, prefix="/api/trust", tags=["Trust"])
app.include_router(family.router, prefix="/api/family", tags=["Family"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "LG HomeStory"}
