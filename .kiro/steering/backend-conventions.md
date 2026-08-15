---
inclusion: fileMatch
fileMatchPattern: "**/*.py"
---

# Backend 개발 규칙 (Python / FastAPI)

## 파일 구조 원칙

```
backend/
  routers/       # HTTP 인터페이스만 (request 파싱 → service 호출 → response 반환)
  services/      # 비즈니스 로직 (Graph 조작, LLM 호출, 데이터 처리)
  models/
    graph_models.py   # 내부 저장용 dataclass (Person, Event, Place, Media, Memory)
    schemas.py        # API용 Pydantic 모델 (Request/Response)
```

**규칙**: Router에 비즈니스 로직을 넣지 않는다. 항상 service로 위임.

## 새 API 엔드포인트 추가 시

1. `backend/models/schemas.py`에 Request/Response 모델 정의
2. `backend/services/`에 로직 함수 작성
3. `backend/routers/`에 라우터 함수 작성 (service 호출만)
4. `backend/main.py`에서 `include_router()` 등록

## GraphManager 사용법

```python
from backend.services.graph_manager import graph_manager  # 전역 싱글톤

# 노드 조회
graph_manager.get_node("person_abc123")
graph_manager.get_persons()
graph_manager.get_events()
graph_manager.search_nodes("부산")

# 노드 추가 (자동으로 save() 호출됨)
graph_manager.add_person(PersonNode(name="...", relation="..."))
graph_manager.add_event(EventNode(title="...", date_start="2024-01-01"))

# 엣지 추가
graph_manager.add_edge(Edge(source="person_x", target="event_y", relation="participated_in"))

# 연결 노드 탐색
graph_manager.get_connected_nodes("event_abc", relation="captured_during")
graph_manager.get_event_detail("event_abc")  # Event + participants/media/memories
```

**주의**: `graph_manager`를 직접 import해서 사용. 새로 인스턴스를 만들지 않는다.

## 코딩 스타일

- **네이밍**: snake_case (함수, 변수), PascalCase (클래스)
- **타입 힌트**: 함수 시그니처에 반드시 작성. `from __future__ import annotations` 사용
- **docstring**: 한국어, 1줄 요약. 복잡한 함수는 Flow 설명 추가
- **에러 처리**: FastAPI의 HTTPException 활용. 500 에러는 로깅 후 사용자에게는 일반 메시지
- **async**: I/O 바운드(외부 API 호출 등)는 async, CPU 바운드(Graph 검색 등)는 sync OK

## 신뢰도 모델 (필수)

Graph에 데이터를 추가할 때 반드시 아래 필드를 설정:

```python
# confidence: 데이터의 확실도
"confirmed"         # 사용자가 직접 확인
"ai_inferred"       # AI가 추론
"user_unverified"   # 입력됐지만 미확인

# source: 데이터 출처
"exif"              # 사진 메타데이터에서 추출
"user_input"        # 사용자 직접 입력
"ai_vision"         # AI 이미지 분석
"ai_stt"            # AI 음성 인식
"interview"         # AI 인터뷰에서 수집
```

## EXAONE (LLM) 연동 패턴

```python
from backend.config import EXAONE_API_URL, EXAONE_API_KEY, EXAONE_MODEL

# API 키 없으면 시뮬레이션 응답 반환 (개발 편의)
if not EXAONE_API_KEY:
    return _simulate_response(...)

# httpx로 비동기 호출
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.post(EXAONE_API_URL, ...)
```

**항상 시뮬레이션 폴백을 구현한다** — API 키 없이도 앱이 동작해야 함.

## 환경 설정

- 경로 상수는 `backend/config.py`에서 가져온다 (GRAPH_FILE, MEDIA_DIR 등)
- 환경 변수는 `.env` 파일 + `python-dotenv`로 로드
- 새 환경 변수 추가 시 `.env.example`에도 반영

## 의존성

- 새 패키지 추가 시 `backend/requirements.txt`에 추가
- 가급적 기존 패키지로 해결 (NetworkX, httpx, Pillow, python-multipart 등)
