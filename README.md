# LG HomeStory

> 사람과 사건의 기억을 연결하고, 질문하면 실제 기록을 근거로 답해주는 "대화 가능한 기억 공간"
>
> 엔진명: Family Memory Graph · 관계는 가족·친구·연인을 모두 포함합니다

2026 LG Promptathon 출품작

---

## 한 줄 요약

흩어진 가족의 기록을 AI가 사람·시간·장소·사건으로 연결해, 검색·대화·재생 가능한 디지털 자산으로 만듭니다.

---

## 핵심 기능 (MVP)

| 기능 | 설명 |
|------|------|
| **Memory Graph** | 사진·영상·음성을 인물/이벤트/장소로 자동 연결하는 그래프 |
| **Memory Chat** | 자연어 질문 → Graph 검색 + EXAONE 답변 생성 |
| **AI Interview** | 기억의 빈 곳을 AI가 질문하며 새로운 기록 수집 |
| **Memory Gap** | 빠진 정보/한쪽 관점만 있는 기억 자동 탐지 |
| **TV Memory Journey** | 조건 기반 사진 슬라이드쇼 (LG TV 시뮬레이션) |

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Backend | FastAPI (Python 3.12) |
| Graph 저장 | NetworkX + JSON 파일 |
| LLM | EXAONE (LG AI Research) |
| 배포 | Vercel (프론트) + Railway (백엔드) |

---

## 프로젝트 구조

```
prompthon-2026/
├── backend/                 # FastAPI 백엔드
│   ├── main.py              # 앱 진입점 (CORS, 라우터 등록, Static Files)
│   ├── config.py            # 환경변수, 경로 설정
│   ├── routers/             # API 엔드포인트
│   │   ├── media.py         # 미디어 업로드/조회/삭제/보충
│   │   ├── graph.py         # Graph 조회, Person/Event CRUD
│   │   ├── chat.py          # Memory Chat (EXAONE)
│   │   ├── interview.py     # AI Interview 세션
│   │   ├── gaps.py          # Memory Gap 탐지
│   │   └── tv.py            # TV Memory Journey
│   ├── services/            # 비즈니스 로직
│   │   ├── graph_manager.py # NetworkX Graph CRUD + 검색 (싱글톤)
│   │   ├── media_analyzer.py# EXIF 추출, 썸네일 생성
│   │   ├── event_resolver.py# 미디어→이벤트 자동 매칭/생성
│   │   ├── chat_engine.py   # Graph RAG + EXAONE 호출
│   │   ├── interview_engine.py # 인터뷰 질문 생성 + 답변 구조화
│   │   ├── gap_detector.py  # 6가지 Gap 유형 탐지
│   │   └── tv_curator.py    # 조건 기반 슬라이드쇼 큐레이션
│   └── models/
│       ├── graph_models.py  # 노드/엣지 dataclass (Person, Event, Place, Media, Memory)
│       └── schemas.py       # Pydantic Request/Response 모델
│
├── frontend/                # React 프론트엔드
│   ├── src/
│   │   ├── App.tsx          # 라우팅 설정
│   │   ├── lib/api.ts       # API 클라이언트 (정적/동적 모드 분기)
│   │   ├── layouts/         # AppLayout (사이드바), TVLayout (풀스크린)
│   │   └── pages/           # 8개 페이지
│   │       ├── HomePage.tsx       # 타임라인 + 통계 + 미디어 갤러리
│   │       ├── UploadPage.tsx     # 드래그&드롭 업로드 + EXIF 없는 파일 정보 입력
│   │       ├── GraphPage.tsx      # react-force-graph-2d 시각화
│   │       ├── ChatPage.tsx       # 채팅 UI + 소스 뱃지
│   │       ├── InterviewPage.tsx  # AI 인터뷰 Q&A 플로우
│   │       ├── GapsPage.tsx       # Gap 카드 리스트
│   │       ├── TVViewPage.tsx     # 풀스크린 슬라이드쇼
│   │       └── FamilyPage.tsx     # 가족 구성원 + 프로필 모달
│   ├── public/mock/         # 정적 배포용 mock 데이터 + 사진
│   ├── .env.production      # 배포 환경변수
│   ├── vercel.json          # Vercel 설정
│   └── tailwind.config.js   # LG Red/Grey 테마
│
├── data/                    # 데이터 (git에서 일부 제외)
│   ├── metadata/            # Ground truth JSON (persons, events, media, memories)
│   ├── photos/              # 24장 합성 사진 (EXIF 포함)
│   ├── video/               # 4개 영상
│   ├── profiles/            # 자동 생성된 프로필 크롭
│   ├── media/               # 서빙용 (시드 시 photos에서 복사됨)
│   └── graph.json           # 생성된 Graph (57노드, 198엣지)
│
├── scripts/
│   ├── seed_from_metadata.py  # metadata → Graph 생성
│   ├── generate_profiles.py   # 사진에서 프로필 크롭
│   ├── seed_sample.py         # (레거시) 더미 데이터 생성
│   └── run_dev.sh             # 백엔드+프론트 동시 실행
│
├── docs/
│   ├── MVP_DESIGN.md        # Graph 스키마, API 설계, 화면 구성
│   └── SPEC_SUMMARY.md      # API 호출 형식 전체 정리
│
├── .env.example             # 환경변수 템플릿
├── .gitignore
├── Dockerfile               # Railway 배포용
└── railway.toml             # Railway 설정
```

---

## 로컬 개발 시작

### 사전 준비
- Python 3.11+ (3.12 권장)
- Node.js 18+
- npm

### 설치 및 실행

```bash
# 1. 백엔드
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# 2. 시드 데이터
python scripts/seed_from_metadata.py
python scripts/generate_profiles.py

# 3. 프론트엔드
cd frontend && npm install && cd ..

# 4. 실행 (터미널 2개)
uvicorn backend.main:app --reload --reload-exclude "venv/*" --port 8000
cd frontend && npm run dev  # → http://localhost:5173
```

### LLM 연동 (선택)
```bash
cp .env.example .env
# .env에 EXAONE_API_KEY 입력
# API 키 없어도 시뮬레이션 응답으로 동작함
```

---

## 배포 구성

| 서비스 | 플랫폼 | URL |
|--------|--------|-----|
| Frontend | Vercel | (자동 배포) |
| Backend | Railway | sparkling-luck-production-4bd7.up.railway.app |

### Vercel (프론트)
- Root Directory: `frontend`
- Framework: Vite
- 환경변수: `.env.production` 참조

### Railway (백엔드)
- 별도 폴더 `prompthon-2026-railway/`에서 `railway up`
- 또는 Dockerfile 기반 자동 빌드

---

## Graph 스키마

### 노드 (5 종류)
| 타입 | 주요 속성 |
|------|-----------|
| **Person** | name, relation, birth_year, birth_date, thumbnail_url |
| **Event** | title, description, date_start, location_id, confidence |
| **Place** | name, address, lat, lng |
| **Media** | media_type, file_path, exif_date, exif_lat/lng, detected_faces |
| **Memory** | content, source_type, contributor_id, confidence |

### 엣지 (8 종류)
| 관계 | From → To |
|------|-----------|
| PARTICIPATED_IN | Person → Event |
| CAPTURED_DURING | Media → Event |
| TAKEN_AT | Media → Place |
| DEPICTS | Media → Person |
| LOCATED_AT | Event → Place |
| REMEMBERS | Person → Memory |
| ABOUT | Memory → Event |
| RELATED_TO | Person → Person |

### 신뢰도 모델
- `confidence`: confirmed / ai_inferred / user_unverified
- `source`: exif / user_input / ai_vision / ai_stt / interview

---

## API 엔드포인트 요약

| 도메인 | 엔드포인트 | 설명 |
|--------|-----------|------|
| Health | `GET /api/health` | 서버 상태 |
| Media | `POST /api/media/upload` | 파일 업로드 + 자동 분석 |
| | `POST /api/media/supplement` | EXIF 없는 미디어 정보 보충 |
| | `GET /api/media` | 미디어 목록 |
| Graph | `GET /api/graph` | 전체 노드+엣지 |
| | `GET /api/graph/events` | 이벤트 목록 |
| | `GET /api/graph/event/{id}` | 이벤트 상세 |
| | `GET /api/graph/persons` | 인물 목록 |
| | `POST /api/graph/person` | 인물 추가 |
| Chat | `POST /api/chat` | 자연어 질의 → 답변 |
| Interview | `POST /api/interview/start` | 인터뷰 시작 |
| | `POST /api/interview/answer` | 답변 제출 |
| Gaps | `GET /api/gaps` | Gap 목록 |
| TV | `POST /api/tv/journey` | Journey 생성 |

상세 요청/응답 형식: `docs/SPEC_SUMMARY.md` 참조

---

## 데모 시나리오 (발표 흐름)

1. **홈 화면** — 타임라인으로 가족 이벤트 8개 확인
2. **이벤트 클릭** — 소속 사진 펼쳐보기
3. **Graph 시각화** — 57개 노드의 관계 탐색
4. **Chat** — "부산 여행 언제 갔어?" 질문 → 근거 기반 답변
5. **Gap 탐지** — "서연의 기억이 빠져있어요" 확인
6. **Interview** — AI가 질문 → 답변으로 Graph 업데이트
7. **TV Journey** — "부산 여행" 풀스크린 슬라이드쇼

---

## 역할 분담 가이드

| 역할 | 담당 영역 | 주요 파일 |
|------|-----------|-----------|
| **프론트엔드** | UI/UX, 페이지 추가, 스타일링 | `frontend/src/` |
| **백엔드** | API 로직, Graph 처리, LLM 연동 | `backend/` |
| **데이터/AI** | Graph 스키마, 검색 로직, 프롬프트 최적화 | `backend/services/`, `data/metadata/` |
| **인프라/배포** | Vercel, Railway, 환경 설정 | `Dockerfile`, `vercel.json`, `.env` |

---

## 주요 설계 원칙

1. **사실 vs 추정 분리** — 모든 데이터에 `confidence`와 `source` 명시
2. **관점별 기억 보존** — 같은 사건도 가족마다 다른 기억 병렬 저장
3. **Private by Default** — 가족 데이터는 기본 비공개
4. **환각 최소화** — Chat 답변에 반드시 Source 연결

---

## 참고 문서

- `docs/MVP_DESIGN.md` — 설계 상세 (Graph 스키마, API, 화면 구성)
- `docs/SPEC_SUMMARY.md` — API 호출 형식 전체 정리
- `.env.example` — 환경변수 설명
