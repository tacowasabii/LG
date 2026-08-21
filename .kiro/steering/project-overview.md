---
inclusion: always
---

# LG HomeStory — 프로젝트 개요

## 프로젝트 소개

가족의 사진·영상·음성·기억을 AI가 사람·시간·장소·추억으로 연결해,
검색·대화·재생 가능한 "대화 가능한 가족 기억 공간"을 만드는 서비스.

2026 LG Promptathon 출품작.

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Backend | FastAPI (Python 3.12) |
| Graph 저장 | NetworkX + JSON 파일 (data/graph.json) |
| LLM | EXAONE (LG AI Research) — API 키 없으면 시뮬레이션 폴백 |
| 배포 | Vercel (프론트) + Railway (백엔드) |

## 디렉토리 구조 요약

```
backend/          FastAPI 앱
  main.py           진입점 (CORS, 라우터 등록, 정적 파일 서빙)
  config.py         환경변수, 경로 상수
  routers/          API 엔드포인트 (media, graph, chat, interview, memories, film, tv 등)
  services/         비즈니스 로직 (graph_manager, chat_engine 등)
  models/           graph_models.py (dataclass), schemas.py (Pydantic)

frontend/         React SPA
  src/App.tsx       라우팅 (AppLayout 안에 7페이지, TVLayout 안에 TV페이지)
  src/lib/api.ts    API 클라이언트 (정적/동적 모드 분기)
  src/pages/        *Page.tsx 파일들
  src/layouts/      AppLayout, TVLayout

data/             데이터
  graph.json        Graph 본체 (57 노드, 198 엣지)
  metadata/         Ground truth JSON (persons, events, media, memories)
  media/            서빙용 미디어 파일
  photos/           원본 사진 (EXIF 포함)
```

## 핵심 아키텍처 패턴

1. **GraphManager 싱글톤** — NetworkX DiGraph를 메모리에 유지하고 변경 시 JSON 파일로 영속화
2. **Router → Service 분리** — Router는 HTTP 인터페이스만, 로직은 services/에 위임
3. **Pydantic 스키마** — Request/Response는 모두 `backend/models/schemas.py`에 정의
4. **신뢰도 모델** — 모든 데이터에 `confidence` (confirmed / ai_inferred / user_unverified)와 `source` (exif / user_input / ai_vision / ai_stt / interview) 필수
5. **정적 모드 지원** — 프론트엔드는 `VITE_STATIC_MODE=true`면 public/mock/ JSON에서 읽어서 백엔드 없이 동작

## 언어 규칙

- **UI 텍스트**: 한국어
- **코드 변수/함수명**: 영어 (snake_case for Python, camelCase for TS)
- **주석/docstring**: 한국어 OK (간결하게)
- **커밋 메시지**: 한국어 또는 영어 (팀 내 자유)

## 로컬 실행

```bash
# 백엔드 (포트 8000)
uvicorn backend.main:app --reload --reload-exclude "venv/*" --port 8000

# 프론트엔드 (포트 5173)
cd frontend && npm run dev
```

## 환경 변수

`EXAONE_API_KEY` — LLM 연동 시 필요, 없으면 시뮬레이션 모드로 동작.
자세한 목록은 `.env.example` 참조.
