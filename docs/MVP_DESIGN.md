# Family Memory Graph — MVP 설계 문서

> 예선 MVP 범위: Memory Graph + Memory Chat + AI Interview + 추억 초안·기억 이어가기 + TV Memory Journey
>
> **기획 변경 (Memory Gap → 기억 이어가기)**: 이 문서의 초판은 빈칸을 "Memory Gap"
> 목록으로 보여주고 가족 전원이 확인해야 추억이 완료되는 구조였다. 가족에는 앱이
> 익숙하지 않은 고령자와 아이가 함께 있어 그 완료 조건이 성립하지 않는다. 그래서
> 추억은 한 사람이 만들면 즉시 게시되고, 다른 가족은 의무 없이 기억을 더하기만 한다.
> 아래 2.5절과 화면 구성이 그 변경을 반영한다.

---

## 1. Memory Graph 스키마

### 노드 (Nodes)

| 노드 타입 | 주요 속성 | 설명 |
|-----------|-----------|------|
| **Person** | `id`, `name`, `relation` (아빠/엄마/아들 등), `birth_year`, `thumbnail_url` | 가족 구성원 |
| **Event** | `id`, `title`, `description`, `date_start`, `date_end`, `location_id`, `confidence` | 추억 단위 (여행, 생일 등) |
| **Place** | `id`, `name`, `address`, `lat`, `lng` | 장소 |
| **Media** | `id`, `type` (photo/video/audio), `file_path`, `thumbnail_path`, `created_at`, `metadata` | 업로드된 미디어 파일 |
| **Memory** | `id`, `content`, `source_type` (interview/upload/manual), `contributor_id`, `confidence`, `created_at` | 구술 기억, 설명 텍스트 등 |

### 엣지 (Edges / Relations)

| 관계 | From → To | 속성 | 예시 |
|------|-----------|------|------|
| `PARTICIPATED_IN` | Person → Event | `role` (주인공/동행) | 아빠 → 부산 여행 |
| `TAKEN_AT` | Media → Place | — | 사진 → 해운대 |
| `CAPTURED_DURING` | Media → Event | — | 사진 → 부산 여행 |
| `DEPICTS` | Media → Person | `confidence` | 사진 → 엄마 |
| `LOCATED_AT` | Event → Place | — | 부산 여행 → 부산 |
| `REMEMBERS` | Person → Memory | — | 아빠 → "그때 비 왔었지" |
| `ABOUT` | Memory → Event | — | 기억 → 부산 여행 |
| `RELATED_TO` | Person → Person | `relation_type`, `category` | 아빠 → 아들 (부자/family), 딸 → 남동생 (남매/family) |

### 신뢰도 모델

```
confidence: "confirmed" | "ai_inferred" | "user_unverified"
source: "exif" | "user_input" | "ai_vision" | "ai_stt" | "interview"
```

- 모든 노드/엣지에 `confidence`와 `source` 필드를 붙여 "확정 사실 vs AI 추정" 분리

### 저장 방식 (MVP)

- **NetworkX** (Python in-memory graph) + **JSON 파일** 영속화
- `data/graph.json` — 노드/엣지 전체 직렬화
- 서버 시작 시 로드, 변경 시 저장

---

## 2. API 엔드포인트 설계

Base URL: `http://localhost:8000/api`

### 2.1 미디어 업로드 & 분석

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/media/upload` | 사진/영상/음성 업로드. 메타데이터 추출 후 Graph 자동 연결 |
| `GET` | `/media` | 전체 미디어 목록 (필터: type, date, person) |
| `GET` | `/media/{id}` | 미디어 상세 + 연결된 Event/Person |
| `DELETE` | `/media/{id}` | 미디어 삭제 |

**POST /media/upload 처리 흐름:**
1. 파일 저장 → `data/media/`
2. EXIF 추출 (날짜, GPS, 카메라 정보)
3. AI 분석 (얼굴 인식 → Person 매칭, 장면 분류)
4. Event Resolver: 기존 Event에 매칭 or 새 Event 생성
5. Graph 업데이트

### 2.2 Memory Graph

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/graph` | 전체 Graph (노드+엣지) 반환 |
| `GET` | `/graph/events` | Event 목록 (타임라인용) |
| `GET` | `/graph/event/{id}` | Event 상세 + 연결된 Person/Media/Memory |
| `GET` | `/graph/person/{id}` | Person 상세 + 참여 Event/Media |
| `POST` | `/graph/person` | 가족 구성원 수동 추가 |
| `PUT` | `/graph/event/{id}` | Event 정보 수정 |

### 2.3 Memory Chat (EXAONE)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/chat` | 자연어 질의 → 답변 + 근거 Media/Event 반환 |

**Request:**
```json
{
  "query": "우리 가족이 부산 처음 간 게 언제야?",
  "conversation_id": "optional-session-id"
}
```

**Response:**
```json
{
  "answer": "2015년 여름에 처음 부산에 가셨어요. 해운대에서...",
  "sources": [
    { "type": "media", "id": "m_001", "thumbnail": "...", "confidence": 0.95 },
    { "type": "event", "id": "e_003", "title": "2015 부산 여행" }
  ],
  "confidence": "confirmed"
}
```

**내부 처리:**
1. 질의 → EXAONE으로 의도 분석 (검색 키워드/조건 추출)
2. Graph 필터링 + (향후) Vector 검색으로 관련 노드 검색
3. 검색 결과를 컨텍스트로 EXAONE에 전달 → 답변 생성
4. Source 연결 + confidence 표시

### 2.4 AI Interview

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/interview/start` | 인터뷰 세션 시작 (대상 Event 또는 Media 기반) |
| `POST` | `/interview/answer` | 사용자 답변 제출 → Graph 업데이트 + 다음 질문 |
| `GET` | `/interview/status` | 현재 인터뷰 진행 상태 |

**Flow:**
1. 아직 덜 채워진 Event/Media 기반으로 질문 생성 (`services/question_picker.py`)
2. 사용자 답변 → 구조화 → Memory 노드 생성 → Graph 연결
3. 추가 질문 or 종료 판단

### 2.5 추억 초안 · 기억 이어가기

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/memories/draft` | 올린 사진·영상으로 추억 초안 (제목·날짜·장소·인물·근거) |
| `POST` | `/memories` | 추억 만들기 — 저장 즉시 게시 (승인 없음) |
| `GET` | `/memories/feed` | 기억 이어가기 목록 |
| `POST` | `/memories/{id}/echo` | 나도 기억나요 (토글) |
| `POST` | `/memories/{id}/memory` | 내 기억 더하기 (원본 보존) |
| `POST` | `/memories/{id}/story` | 함께 기억한 이야기 (누가 맞는지 판정하지 않음) |

**초안 규칙 (services/memory_drafter.py):**
- 읽는 것: EXIF 촬영 시점·GPS, 지목된 인물, scene_description, 기존 가족 기록
- 못 읽은 값은 비워 둔다 (추측해서 채우지 않는다)
- 인물 추정은 동시 등장 통계로 순위를 매기고 "이 사진에 엄마도 있나요?"로 되묻는다
- 기존 추억과 관련 있어 보이면 알리고, 붙일지 새로 만들지는 사용자가 고른다

**기억 상태 (services/memories.state_of):**
- alone   만든 사람의 기억만 있다 (결함이 아니다)
- shared  가족이 기억을 더했다
- varied  조금 다르게 기억하는 내용이 함께 있다 — 한쪽을 정답으로 정하지 않는다

### 2.6 TV Memory Journey

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/tv/journey` | 조건(시기/인물/장소) 기반 큐레이션 생성 |
| `GET` | `/tv/journey/{id}` | 생성된 Journey 데이터 (슬라이드 목록) |

**Request:**
```json
{
  "query": "우리 가족의 2015년",
  "style": "timeline"
}
```

**Response:**
```json
{
  "slides": [
    {
      "type": "photo",
      "media_id": "m_001",
      "caption": "1월 - 설날 가족 모임",
      "event_id": "e_001"
    },
    ...
  ],
  "narration": "2015년, 우리 가족은..."
}
```

---

## 3. 프론트엔드 화면 구성

### 3.1 페이지 목록

| 페이지 | 경로 | 설명 | 호출 API |
|--------|------|------|----------|
| **Home / Timeline** | `/` | 시간순 가족 기억 타임라인 | `GET /graph/events`, `GET /media` |
| **Upload** | `/upload` | 사진·영상·음성 업로드 | `POST /media/upload` |
| **Graph View** | `/graph` | Memory Graph 시각화 (노드·엣지) | `GET /graph` |
| **Chat** | `/chat` | Memory Chat 대화 UI | `POST /chat` |
| **Interview** | `/interview` | AI 인터뷰 (질문-답변 flow) | `/interview/*` |
| **기억 이어가기** | `/continue` | 가족의 추억 목록 + 내 기억 더하기 | `GET /memories/feed` |
| **추억 상세** | `/memory/:id` | 여러 사람의 기억이 쌓이는 곳 | `GET /memories/{id}` |
| **TV View** | `/tv` | TV Memory Journey (16:9, 풀스크린) | `/tv/journey` |
| **Family** | `/family` | 가족 구성원 관리 | `GET /graph/person/*` |

### 3.2 UI 컴포넌트 구조

```
src/
├── pages/
│   ├── HomePage.tsx          # Timeline + 최근 업로드
│   ├── CollectPage.tsx       # 모으기 — 업로드 + 보충 + 첫 질문
│   ├── GraphPage.tsx         # 인터랙티브 Graph 시각화
│   ├── ChatPage.tsx          # 채팅 UI (메시지 + 미디어 카드)
│   ├── InterviewPage.tsx     # 질문-답변 플로우
│   ├── ContinuePage.tsx      # 기억 이어가기 목록
│   ├── MemoryDetailPage.tsx  # 추억 상세
│   ├── TVViewPage.tsx        # 풀스크린 슬라이드쇼
│   └── FamilyPage.tsx        # 가족 구성원 카드
├── components/
│   ├── MediaCard.tsx         # 사진/영상/음성 썸네일 카드
│   ├── EventCard.tsx         # 추억 요약 카드
│   ├── ChatBubble.tsx        # 채팅 말풍선 (답변 + 소스 링크)
│   ├── GraphVisualization.tsx # D3 or react-force-graph
│   ├── TimelineView.tsx      # 세로 타임라인
│   ├── SourceBadge.tsx       # confidence 뱃지 (confirmed/inferred)
│   └── TVSlide.tsx           # TV Journey 슬라이드
├── layouts/
│   ├── AppLayout.tsx         # 일반 레이아웃 (사이드바 + 헤더)
│   └── TVLayout.tsx          # TV 전용 (풀스크린, 16:9)
└── lib/
    └── api.ts                # API 호출 함수 모음
```

### 3.3 핵심 UX 포인트

- **Chat 답변**: 텍스트 + 근거 미디어 카드 + confidence 뱃지 함께 표시
- **Graph 시각화**: Person/Event/Place 노드를 색상으로 구분, 클릭 시 상세
- **TV View**: 리모컨 UX 시뮬레이션 (키보드 좌/우로 슬라이드 이동)
- **추억 카드**: 사진 + 최초 작성자의 기억 + `나도 기억나요` · `내 기억 더하기`
- **Upload 후**: 자동 분석 결과 프리뷰 (감지된 인물, 장소, 매칭된 Event)

---

## 4. 프로젝트 디렉토리 구조

```
family_memory_graph/
├── backend/
│   ├── main.py                 # FastAPI 앱 진입점
│   ├── config.py               # 설정 (EXAONE API key 등)
│   ├── routers/
│   │   ├── media.py            # /api/media/*
│   │   ├── graph.py            # /api/graph/*
│   │   ├── chat.py             # /api/chat
│   │   ├── interview.py        # /api/interview/*
│   │   ├── memories.py         # /api/memories/*
│   │   └── tv.py               # /api/tv/*
│   ├── services/
│   │   ├── media_analyzer.py   # EXIF 추출, AI 분석 호출
│   │   ├── graph_manager.py    # NetworkX Graph CRUD
│   │   ├── event_resolver.py   # 미디어 → 이벤트 매칭/생성
│   │   ├── chat_engine.py      # EXAONE 질의 + Graph RAG
│   │   ├── interview_engine.py # 질문 생성 + 답변 구조화
│   │   ├── memories.py         # 추억 게시 · 기억 더하기
│   │   ├── memory_drafter.py   # 초안 · 인물 추정 · 기존 추억 연결
│   │   ├── question_picker.py  # 인터뷰가 물어볼 대상 고르기
│   │   └── tv_curator.py       # Journey 큐레이션
│   ├── models/
│   │   ├── schemas.py          # Pydantic 모델 (Request/Response)
│   │   └── graph_models.py     # 노드/엣지 데이터 클래스
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── data/
│   ├── media/                  # 업로드된 파일
│   ├── graph.json              # Graph 영속화
│   └── sample/                 # 데모용 샘플 데이터
└── scripts/
    ├── seed_sample.py          # 샘플 데이터 생성 스크립트
    └── run_dev.sh              # 백엔드+프론트 동시 실행
```

---

## 5. 기술 스택 요약

| 레이어 | 선택 | 이유 |
|--------|------|------|
| Backend | FastAPI + Python 3.11+ | 비동기, 자동 docs, 타입 힌트 |
| Graph | NetworkX + JSON | 설치 0, MVP 충분, 직렬화 쉬움 |
| LLM | EXAONE (LG AI Research) | 프롬프타톤 필수 |
| 메타데이터 | Pillow + exifread | EXIF/GPS 추출 |
| Frontend | React 18 + TypeScript + Vite | 빠른 빌드, 타입 안전 |
| 스타일 | Tailwind CSS | 유틸리티 기반, 빠른 UI 구현 |
| Graph 시각화 | react-force-graph 또는 D3 | 인터랙티브 노드/엣지 |
| 상태관리 | Zustand 또는 React Query | 가볍고 직관적 |

---

## 6. MVP 데모 시나리오 매핑

| 데모 단계 | 화면 | 핵심 동작 |
|-----------|------|-----------|
| ① 업로드 | Upload 페이지 | 가족 사진 5~10장 + 음성 1개 드래그 업로드 |
| ② Graph 생성 | Graph 페이지 | 자동 생성된 노드·엣지 시각화 확인 |
| ③ Chat 질의 | Chat 페이지 | "부산 여행 언제 갔어?" 질문 |
| ④ 근거 답변 | Chat 페이지 | 답변 + 사진 카드 + confidence 표시 |
| ⑤ 기억 이어가기 | 기억 이어가기 페이지 | "이때 아빠가 길을 잘못 들었어요" 기억이 더해지는 것 |
| ⑥ Interview | Interview 페이지 | AI 질문 → 답변 입력 |
| ⑦ Graph 업데이트 | Graph 페이지 | 새 Memory 노드 추가된 것 확인 |
| ⑧ TV Journey | TV View | "우리 가족의 2015년" 풀스크린 슬라이드 |
