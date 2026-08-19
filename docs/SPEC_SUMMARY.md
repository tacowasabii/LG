# Family Memory Graph — 프론트/백엔드 스펙 및 API 호출 정리

## 전체 구조

```
[Frontend]  React 18 + Vite + TypeScript + Tailwind
     │
     │  HTTP (JSON / multipart)
     ▼
[Backend]   FastAPI (Python 3.11+)
     │
     ├── NetworkX (Memory Graph, JSON 영속화)
     ├── EXAONE API (LLM 호출)
     └── Static Files (사진/영상 서빙)
```

---

## 1. 백엔드 스펙

### 기술 스택
- **Framework**: FastAPI 0.115
- **Python**: 3.11+ (3.14에서도 동작 확인)
- **Graph 저장**: NetworkX + `data/graph.json`
- **미디어 분석**: Pillow (EXIF), exifread
- **LLM**: EXAONE API (OpenAI-compatible format)
- **의존성**: `backend/requirements.txt` 참조

### 실행
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 디렉토리 구조
```
backend/
├── main.py              # FastAPI 앱, CORS, 라우터 등록
├── config.py            # 환경변수, 경로 설정
├── routers/             # API 엔드포인트
│   ├── media.py         # 미디어 업로드/목록/상세/삭제/보충
│   ├── graph.py         # Graph 조회, Person/Event CRUD
│   ├── chat.py          # Memory Chat
│   ├── interview.py     # AI Interview
│   ├── gaps.py          # Memory Gap 탐지
│   └── tv.py            # TV Journey
├── services/            # 비즈니스 로직
│   ├── graph_manager.py # Graph CRUD + 검색
│   ├── media_analyzer.py# EXIF 추출, 썸네일
│   ├── event_resolver.py# 이벤트 자동 매칭/생성
│   ├── chat_engine.py   # EXAONE + Graph RAG
│   ├── interview_engine.py
│   ├── gap_detector.py
│   └── tv_curator.py
└── models/
    ├── graph_models.py  # 노드/엣지 dataclass
    └── schemas.py       # Pydantic request/response
```

---

## 2. API 엔드포인트 목록

Base URL: `http://localhost:8000`

### Health
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/health` | 서버 상태 확인 |

### Media
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/media/upload` | 파일 업로드 (multipart/form-data) |
| POST | `/api/media/supplement` | EXIF 없는 미디어 추가 정보 제공 |
| GET | `/api/media` | 미디어 목록 (쿼리: ?media_type=photo&person_id=P01) |
| GET | `/api/media/{id}` | 미디어 상세 |
| DELETE | `/api/media/{id}` | 미디어 삭제 |

### Graph
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/graph` | 전체 Graph (nodes + edges) |
| GET | `/api/graph/events` | 이벤트 목록 |
| GET | `/api/graph/event/{id}` | 이벤트 상세 (참여자, 미디어, 기억 포함) |
| PUT | `/api/graph/event/{id}` | 이벤트 수정 |
| GET | `/api/graph/persons` | 인물 목록 |
| GET | `/api/graph/person/{id}` | 인물 상세 |
| POST | `/api/graph/person` | 인물 추가 |

### Chat
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/chat` | 자연어 질의 → 답변 + 소스 |

### Interview
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/interview/start` | 인터뷰 세션 시작 |
| POST | `/api/interview/answer` | 답변 제출 → 다음 질문 |
| GET | `/api/interview/status/{session_id}` | 세션 상태 |

### Gaps
| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/gaps` | Memory Gap 목록 |
| GET | `/api/gaps/{id}` | Gap 상세 |

### Memory Film
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/film` | 사건 하나를 30~60초 이야기로 구성 |
| GET | `/api/film/anniversaries` | 다가오는 기념일 |

요청: `{"event_id": "E01", "length_sec": 45, "audience": "adult"}`
(`audience`: `child` | `adult` | `elder` — 장면 길이와 내레이션 어투가 달라진다)

응답의 장면마다 `source_label`(원본 출처)과 `ai_effects`(적용된 효과)가 실려 온다.
빈 배열이면 원본 그대로다. 화면은 이 목록을 감추지 않고 표시해야 한다.
요청한 길이에 맞추려고 장면을 뺐으면 `omitted_scenes`로 밝힌다.

### TV Journey
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/tv/journey` | Journey 생성 |
| GET | `/api/tv/journey/{id}` | Journey 조회 |

### Static Files
| Path | 설명 |
|------|------|
| `/media-files/{filename}` | 업로드된 사진/영상 서빙 |

---

## 3. 주요 API 호출 형식

### POST /api/media/upload
```
Content-Type: multipart/form-data
Body: file=<binary>
```
Response:
```json
{
  "id": "media_abc123",
  "media_type": "photo",
  "file_path": "/media-files/photo.jpg",
  "exif_date": "2015-07-20T14:30:00",
  "exif_lat": 35.1587,
  "exif_lng": 129.1604,
  "linked_event_id": "E01",
  "needs_info": false,
  "message": "업로드 및 분석 완료"
}
```

### POST /api/media/supplement
```json
{
  "media_id": "media_abc123",
  "date": "2015-07-20",
  "event_id": "E01",
  "description": "해운대 해변 사진"
}
```

### POST /api/chat
```json
{ "query": "우리 가족이 부산 처음 간 게 언제야?", "conversation_id": null }
```
Response:
```json
{
  "answer": "2015년 여름에...",
  "sources": [
    { "type": "event", "id": "E01", "title": "1998 부산 가족여행", "confidence": 0.9 }
  ],
  "confidence": "confirmed",
  "conversation_id": "uuid-xxx"
}
```

### POST /api/interview/start
```json
{ "target_type": "auto", "target_id": null }
```
Response:
```json
{
  "session_id": "uuid-xxx",
  "question": "이 사진이 찍힌 날, 어떤 일이 있었는지 기억나세요?",
  "context": { "target_type": "event", "target_id": "E01", "target_title": "1998 부산 가족여행" }
}
```

### POST /api/interview/answer
```json
{ "session_id": "uuid-xxx", "answer": "그때 해변에서 모래성 만들었어" }
```
Response:
```json
{
  "session_id": "uuid-xxx",
  "next_question": "그때 함께 있었던 가족이 누구였나요?",
  "is_complete": false,
  "updated_nodes": ["memory_abc123"],
  "message": ""
}
```

### GET /api/gaps
Response:
```json
{
  "gaps": [
    {
      "id": "gap_E01_single_perspective",
      "event_id": "E01",
      "event_title": "1998 부산 가족여행",
      "gap_type": "single_perspective",
      "description": "'1998 부산 가족여행'에 대해 김지우의 기억이 없습니다.",
      "suggested_question": "김지우님, '1998 부산 가족여행' 때 어떤 기억이 있으세요?",
      "target_person": "김지우",
      "priority": 4
    }
  ],
  "total": 5
}
```

### POST /api/tv/journey
```json
{ "query": "부산 여행", "style": "timeline" }
```
Response:
```json
{
  "id": "uuid-xxx",
  "title": "부산 여행",
  "slides": [
    { "type": "title", "caption": "", "media_id": null },
    { "type": "photo", "media_id": "E01_001", "file_path": "/media-files/E01_001.jpg", "caption": "1998-08-13 - 1998 부산 가족여행", "event_title": "1998 부산 가족여행" }
  ],
  "narration": "부산에서의 우리 가족 추억...",
  "total_duration_sec": 35
}
```

### GET /api/graph
Response:
```json
{
  "nodes": [
    { "id": "P01", "node_type": "person", "name": "김민수", "relation": "아빠", ... },
    { "id": "E01", "node_type": "event", "title": "1998 부산 가족여행", ... },
    { "id": "E01_001", "node_type": "media", "media_type": "photo", "file_path": "/media-files/E01_001.jpg", ... }
  ],
  "edges": [
    { "source": "P01", "target": "E01", "relation": "participated_in", "properties": {"role": "참여자"} },
    { "source": "E01_001", "target": "E01", "relation": "captured_during", "properties": {} }
  ]
}
```

---

## 4. 프론트엔드 스펙

### 기술 스택
- **Framework**: React 18 + TypeScript
- **빌드**: Vite 5
- **스타일**: Tailwind CSS 3.4
- **폰트**: Inter (영문) + Noto Sans KR (한글)
- **Graph 시각화**: react-force-graph-2d
- **아이콘**: lucide-react
- **라우팅**: react-router-dom v6

### 실행
```bash
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

### 빌드 (배포용)
```bash
cd frontend && npm run build
# → frontend/dist/ 에 정적 파일 생성
```

### 페이지 구성
| 경로 | 페이지 | 호출 API |
|------|--------|----------|
| `/` | 홈 (타임라인 + 통계) | GET events, media, gaps |
| `/upload` | 미디어 업로드 | POST upload, POST supplement |
| `/graph` | Graph 시각화 | GET graph |
| `/chat` | Memory Chat | POST chat |
| `/interview` | AI Interview | POST start, POST answer |
| `/gaps` | Memory Gap 목록 | GET gaps |
| `/tv` | TV Memory Journey | POST journey |
| `/family` | 가족 구성원 관리 | GET persons, POST person |

### API 호출 방식
- `frontend/src/lib/api.ts`에 모든 API 함수 정의
- 개발 시: Vite proxy (`/api` → `localhost:8000`)
- 배포 시: 환경변수로 백엔드 URL 지정 필요

### Vite Proxy 설정 (vite.config.ts)
```ts
proxy: {
  '/api': { target: 'http://localhost:8000', changeOrigin: true },
  '/media-files': { target: 'http://localhost:8000', changeOrigin: true },
}
```

---

## 5. 환경변수 (.env)

```bash
# 백엔드 루트에 위치
EXAONE_API_URL=https://api-cloud.lgresearch.ai/api/v1/chat/completions
EXAONE_API_KEY=your-key
EXAONE_MODEL=exaone-deep
```

API 키 없으면 시뮬레이션 응답으로 폴백 (개발/데모 가능).

---

## 6. 데이터

### 시드 데이터
- `data/metadata/`: persons.json, events.json, media.json, memories.json
- `data/photos/`: 24장 JPG (EXIF 포함 합성 데이터)
- `data/video/`: 4개 MP4
- `data/profiles/`: 5명 프로필 크롭 이미지

### 시드 실행
```bash
python scripts/seed_from_metadata.py  # metadata → Graph 생성
python scripts/generate_profiles.py    # 프로필 사진 생성
```

### Graph 저장
- `data/graph.json` — 노드 57개, 엣지 198개
- 서버 시작 시 자동 로드, 변경 시 자동 저장
