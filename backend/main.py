from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import MEDIA_DIR
from backend.routers import media, graph, chat, interview, gaps, tv, film

app = FastAPI(
    title="LG HomeStory",
    description="사람과 사건의 기억을 연결하고 대화할 수 있는 AI Native 서비스",
    version="0.1.0",
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
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


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "LG HomeStory"}
