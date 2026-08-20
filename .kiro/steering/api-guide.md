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

`needs_info: true`이면 EXIF가 없다는 뜻이다. 서버가 날짜를 추측하지 않는다.
`POST /api/media/supplement`는 **삭제됐다** — 빈칸을 사람이 폼으로 메우는 대신
`POST /api/memories/draft`가 초안을 쓰고 사용자가 고친다.

영상을 올릴 때는 브라우저가 길이(`duration_sec`)와 첫 장면(`poster`, 이미지 파일)을
함께 보낸다. 서버에 ffmpeg를 두지 않기 위한 분업이다 (`frontend/src/lib/videoMeta.ts`).
음성은 같은 자리에 `waveform`·`transcript`·`transcript_source`를 보낸다.

### 이 기록에 있는 사람 지목

```
PUT /api/media/{id}/persons
Body: { "person_ids": ["P01", "P03"] }
→ { "media_id": "...", "detected_faces": ["P01", "P03"] }
```

얼굴 인식은 없다. 이 요청이 `detected_faces`의 유일한 출처이고, 보낸 목록이
최종 상태가 된다 (빈 배열이면 태그를 모두 뗀다).

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

## Memories (추억 · 기억 이어가기)

`GET /api/gaps`와 Memory Gap은 **삭제됐다.** 빠진 것을 목록으로 세워 가족에게
할 일을 주는 방향을 버렸다 — 앱이 익숙하지 않은 가족이 있으면 그 목록은 영원히
줄지 않는다. 대신 추억은 만들면 즉시 게시되고, 가족은 원할 때 기억을 더한다.

```
POST /api/memories/draft   Body: { "media_ids": [...] }
  → 초안 (제목·날짜·장소·인물 후보·설명·기존 추억 연결 후보). 확정이 아니다

POST /api/memories         → 추억 만들기 (저장 즉시 게시)
GET  /api/memories/feed    → 기억 이어가기 목록
GET  /api/memories/{id}    → 추억 상세
POST /api/memories/{id}/echo     → 나도 기억나요 (토글)
POST /api/memories/{id}/memory   → 내 기억 더하기
POST /api/memories/{id}/media    → 기존 추억에 사진·영상 추가
POST /api/memories/{id}/story    → 함께 기억한 이야기 생성
```

확인(맞음/모름/이견) 엔드포인트는 없다. 상태는 저장하지 않고 기억에서 파생한다.

| 상태 | 의미 |
|------|------|
| `alone` | 만든 사람의 기억만 있다 |
| `shared` | 가족이 기억을 더했다 |
| `varied` | 조금 다르게 기억하는 내용이 함께 있다 (고칠 오류가 아니다) |

호출 형식 전체는 `docs/SPEC_SUMMARY.md`를 본다.

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
