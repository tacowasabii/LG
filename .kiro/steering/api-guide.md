---
inclusion: manual
---

# API 엔드포인트 가이드

이 문서는 전체 API 호출 형식을 정리한 참조 문서입니다.
API 작업 시 `#api-guide`로 불러서 사용하세요.

상세 스키마: #[[backend/models/schemas.py]]

---

## Base URL

- 로컬: `http://localhost:8000/api`
- 프론트엔드에서: `VITE_API_URL` 환경변수 또는 기본값 `/api`

---

## Health

```
GET /api/health
→ { "status": "ok", "service": "Family Memory Graph" }
```

---

## Media

### 파일 업로드

```
POST /api/media/upload
Content-Type: multipart/form-data
Body: file (이미지/영상 파일)

→ MediaUploadResponse {
    id, media_type, file_path, thumbnail_path,
    original_filename, exif_date, exif_lat, exif_lng,
    detected_faces, scene_description,
    linked_event_id, needs_info, message
  }
```

`needs_info: true`이면 EXIF가 없으므로 supplement API로 정보 보충 필요.

### 정보 보충 (EXIF 없는 미디어)

```
POST /api/media/supplement
Body: { "media_id": "...", "date": "2024-01-01", "event_id": "E01", "description": "..." }
→ { "message": "...", "linked_event_id": "..." }
```

### 미디어 목록

```
GET /api/media
→ MediaListItem[] (id, media_type, file_path, thumbnail_path, original_filename, created_at, exif_date)
```

### 미디어 삭제

```
DELETE /api/media/{id}
→ 204 No Content
```

---

## Graph

### 전체 그래프

```
GET /api/graph
→ { "nodes": [...], "edges": [...] }
```

### 이벤트 목록

```
GET /api/graph/events
→ EventListItem[] (id, title, date_start, date_end, location_name, participant_count, media_count)
```

### 이벤트 상세

```
GET /api/graph/event/{id}
→ EventResponse {
    id, title, description, date_start, date_end,
    location, confidence,
    participants: PersonNode[],
    media: MediaNode[],
    memories: MemoryNode[]
  }
```

### 인물 목록

```
GET /api/graph/persons
→ PersonResponse[] (id, name, relation, birth_year, thumbnail_url, events, media)
```

### 인물 추가

```
POST /api/graph/person
Body: { "name": "홍길동", "relation": "삼촌", "birth_year": 1985 }
→ PersonResponse
```

---

## Chat (Memory Chat)

```
POST /api/chat
Body: { "query": "부산 여행 언제 갔어?", "conversation_id": null }
→ ChatResponse {
    answer: "가족 기록을 확인해보니...",
    sources: [{ type: "event", id: "E01", title: "1998 부산 가족여행", confidence: 0.9 }],
    confidence: "confirmed",
    conversation_id: "uuid"
  }
```

- `conversation_id`를 유지하면 이전 대화 맥락 이어짐
- `sources`는 답변 근거 (media / event / memory)

---

## Interview (AI 인터뷰)

### 인터뷰 시작

```
POST /api/interview/start
Body: { "target_type": "event", "target_id": "E01" }
       또는 { "target_type": "auto" }
→ InterviewStartResponse {
    session_id: "uuid",
    question: "부산 여행에서 가장 기억에 남는 장면은?",
    context: { target_type, target_id, target_title }
  }
```

### 답변 제출

```
POST /api/interview/answer
Body: { "session_id": "uuid", "answer": "바닷가에서 모래성 쌓았던 거요" }
→ InterviewAnswerResponse {
    session_id, next_question, is_complete,
    updated_nodes: ["memory_abc123"],
    message: "새로운 기억이 추가되었습니다"
  }
```

- `is_complete: true`이면 인터뷰 종료
- `next_question`이 있으면 다음 질문 표시

---

## Gaps (Memory Gap 탐지)

```
GET /api/gaps
→ GapsResponse {
    gaps: GapItem[],
    total: 5
  }

GapItem {
  id, event_id, event_title, gap_type, description,
  suggested_question, target_person, priority
}
```

### gap_type 종류

| 타입 | 의미 |
|------|------|
| `missing_date` | 날짜 정보 없음 |
| `missing_place` | 장소 정보 없음 |
| `missing_person_memory` | 특정 인물의 기억이 없음 |
| `no_media` | 이벤트에 미디어 없음 |
| `single_perspective` | 한 사람 시점만 존재 |

---

## TV Journey (슬라이드쇼)

```
POST /api/tv/journey
Body: { "query": "부산 여행", "style": "timeline" }
→ TVJourneyResponse {
    id: "uuid",
    title: "부산의 추억",
    slides: TVSlide[],
    narration: "...",
    total_duration_sec: 120
  }

TVSlide {
  type: "photo" | "video" | "title" | "narration",
  media_id, file_path, caption, event_id, event_title, date
}
```

### style 옵션

| 값 | 설명 |
|----|------|
| `timeline` | 시간순 정렬 |
| `story` | AI가 스토리라인 구성 |
| `people` | 인물 중심 구성 |

---

## 미디어 파일 접근

업로드된 미디어 파일은 정적 파일로 서빙:

```
GET /media-files/{filename}
예: http://localhost:8000/media-files/E01_001.jpg
```

프론트엔드에서는 `mediaUrl()` 함수로 경로 변환하여 사용.

---

## 에러 응답 형식

```json
{
  "detail": "에러 메시지 (한국어)"
}
```

HTTP 상태 코드:
- `400` — 잘못된 요청
- `404` — 리소스 없음
- `500` — 서버 내부 오류
