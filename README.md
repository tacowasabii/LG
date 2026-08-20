# LG HomeStory

> 사람과 사건의 기억을 연결하고, 질문하면 실제 기록을 근거로 답해주는 "대화 가능한 기억 공간"
>
> 엔진명: Family Memory Graph

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
| **AI Interview** | 기억의 빈 곳을 AI가 질문하며 새로운 기록 수집 (녹음 + 브라우저 전사) |
| **추억 초안** | 사진·영상을 올리면 촬영 시점·좌표·등장인물·기존 기록으로 초안 작성 |
| **기억 이어가기** | 가족이 만든 추억에 글·목소리·사진으로 자기 기억을 더한다 (확인 의무 없음) |
| **TV Memory Journey** | 조건 기반 사진 슬라이드쇼 + 내레이션 낭독 (LG TV 시뮬레이션) |

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
│   │   ├── memories.py      # 추억 초안·만들기·기억 이어가기
│   │   └── tv.py            # TV Memory Journey
│   ├── services/            # 비즈니스 로직
│   │   ├── graph_manager.py # NetworkX Graph CRUD + 검색 (싱글톤)
│   │   ├── album.py         # 사진첩 목록 (필터·정렬·커서·공개 범위, AI 없음)
│   │   ├── media_analyzer.py# EXIF 추출, 썸네일 생성
│   │   ├── event_resolver.py# 미디어→인물·장소 연결 (사건 자동 생성은 하지 않음)
│   │   ├── chat_engine.py   # Graph RAG + EXAONE 호출
│   │   ├── interview_engine.py # 인터뷰 질문 생성 + 답변 구조화
│   │   ├── memories.py      # 추억 게시·기억 더하기·함께 기억한 이야기
│   │   ├── memory_drafter.py# 사진에서 추억 초안 + 인물 추정 + 기존 추억 연결
│   │   ├── question_picker.py # 인터뷰가 물어볼 대상 하나 고르기
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
│   │   └── pages/           # 화면들
│   │       ├── HomePage.tsx       # 타임라인 + 통계 + 미디어 갤러리
│   │       ├── AlbumPage.tsx      # 사진첩 — 연월 그리드 + 필터 + Lightbox
│   │       ├── CollectPage.tsx    # 모으기 — 업로드 → AI 초안 → 추억 만들기
│   │       ├── GraphPage.tsx      # react-force-graph-2d 시각화
│   │       ├── ChatPage.tsx       # 채팅 UI + 소스 뱃지
│   │       ├── InterviewPage.tsx  # AI 인터뷰 Q&A 플로우
│   │       ├── ContinuePage.tsx   # 기억 이어가기 (나도 기억나요 · 내 기억 더하기)
│   │       ├── MemoryDetailPage.tsx # 추억 상세 (여러 사람의 기억이 쌓이는 곳)
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
│   ├── build_motion_covers.py # 사진 → 미세 모션 클립 (fal, 수동 실행·유료)
│   ├── seed_sample.py         # (레거시) 더미 데이터 생성
│   └── run_dev.sh             # 백엔드+프론트 동시 실행
│
├── docs/
│   ├── USER_GUIDE.md        # 화면별 사용법, TV 리모컨 조작, 문제 해결
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

용도에 따라 모델이 갈립니다.

| 용도 | 어디로 | 왜 |
|------|--------|-----|
| 채팅 답변 · 인터뷰 질문 · Film/TV 내레이션 | **EXAONE** | 한국어 서술, 가족 호칭("큰엄마"), 세대별 어투. 신뢰도 채점(Trust Harness)도 이 경로를 돕니다 |
| 질의 계획 · 인터뷰 답변 추출 | **Bedrock** (기본값) | 질문·답변에서 JSON 조각만 뽑는 기계적인 호출. 질의 계획은 채팅 응답 시간에 그대로 더해져서 빠른 모델이 유리합니다 |

Bedrock은 `.env`에 AWS 키를 넣으면 켜집니다 (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_REGION`). **넣지 않으면 전부 EXAONE으로 돕니다** —
설정하지 않은 사람의 화면이 깨지지 않습니다. 모델은 `BEDROCK_MODEL_ID` 한 줄로
바꿉니다 (Claude·Nova·Llama 모두 같은 Converse API입니다). 어느 용도를 어디로
보낼지는 `LLM_PLAN_PROVIDER` · `LLM_EXTRACT_PROVIDER`로 정합니다 —
`exaone`으로 되돌리면 예전과 똑같이 동작합니다.

### 미세 모션 클립 (선택)

Memory Film의 사진은 기본적으로 CSS 카메라 움직임(느린 줌·패닝)만 걸립니다.
파도가 치거나 머리카락이 흔들리는 것처럼 **화면 안의 것이 실제로 움직이게**
하려면 짧은 클립이 필요합니다. 만드는 길이 둘입니다.

| | 언제 | 어디에 쌓이나 |
|---|---|---|
| **미리 만들기** | 손으로 스크립트를 돌린다 | `data/motion/` — 커밋된다 |
| **만들 때 만들기** | 사용자가 Film을 만들면 서버가 채운다 | `STATE_DIR` — 배포에서는 볼륨 |

만드는 방법은 `backend/services/motion_clips.py` 한 곳에 있습니다. 두 경로가
각자 만들면 미리 만든 것과 그때 만든 것이 다르게 생겨서, 어느 쪽을 보고 있는지
화면에서 구분되지 않습니다. 찾을 때는 둘을 합쳐 보고, 같은 사진이 양쪽에 있으면
런타임 쪽을 씁니다.

#### 만들 때 만들기 (`MOTION_AUTOGEN`)

기본값은 **꺼짐**입니다. 켜면 사용자가 Film을 만들 때 그 사건의 **대표 사진**을
그 자리에서 만듭니다.

```bash
MOTION_AUTOGEN=true
MOTION_AUTOGEN_MAX=50          # 누적 상한. 50건 = 약 $10
MOTION_COVERS_PER_EVENT=3      # 사건 하나에서 만들 사진 수의 상한
MOTION_AUTOGEN_NEW_ONLY=true   # 앞으로 생기는 사건만 (기본)
```

**기존 사건은 만들지 않습니다.** 켠 시점의 사건 목록이
`STATE_DIR/motion_baseline.json`에 기준선으로 적히고, 그 뒤에 만들어진 사건만
자동 생성 대상이 됩니다 — 이미 쌓여 있던 앨범 전체를 한꺼번에 만들면 지출이 한
번에 튀기 때문입니다. 기존 사건에 클립을 넣으려면 아래 "미리 만들기"로 합니다.

기준선을 파일에 적어 두는 것이 요점입니다. id 모양(시드가 붙이는 `E01` 같은
규칙)이나 만든 시각으로 가르면 재시드·이관에서 조용히 달라집니다. 전부를
대상으로 하려면 `MOTION_AUTOGEN_NEW_ONLY=false`로 둡니다.

**사진이 상한보다 적으면 전부 만듭니다.** 미세 모션은 파도가 치거나 머리카락·
옷자락이 살짝 흔들리는 정도라, 정적으로 보이는 사진도 만들면 살아납니다. 세
장뿐인 사건에서 골라낼 이유가 없습니다.

상한은 **사진 백 장인 앨범** 때문에 있습니다 (한 장에 약 $0.2). 그때는 대표를
골라 그만큼만 만들고, 고르는 데 `cover_picker`가 모델을 씁니다.

- **상한 이하면 모델을 부르지 않습니다.** "셋 중 셋을 고르라"는 값만 쓰고 답이
  정해진 질문입니다
- **넘칠 때 모델이 사진 설명을 읽고 고릅니다.** 기준은 순서대로 ① 그날이 어떤
  날이었는지 한 장으로 보여주는가 ② 비슷한 사진이 여러 장이면 하나만 ③ 나머지가
  비슷하면 물·불꽃·바람처럼 저절로 움직이는 것이 있는 쪽. 사진을 직접 보여주지는
  않습니다(EXAONE 게이트웨이는 이미지를 받지 않습니다) — 대신 설명을 읽는데,
  그 설명 자체가 사진을 본 결과입니다
- **한 번 고른 것을 지킵니다.** 고를 때마다 달라지면 방문마다 다른 사진을 만들어
  돈이 계속 나갑니다. 선택은 `STATE_DIR/motion_covers.json`에 이유와 함께 남고,
  정원이 남아 다시 고를 때도 앞선 선택은 그대로 둡니다
- **이미 클립이 있는 사진이 그 자리를 차지합니다.** 미리 만들어 커밋한 것이
  있으면 그만큼 정원이 줄어 같은 사건에 또 만들지 않습니다
- **모델이 없으면 앞에서부터 채웁니다.** 목록이 시간순이라 아무 기준이 없는 것은
  아닙니다 — 키를 설정하지 않은 사람의 화면도 같은 방식으로 동작해야 합니다

지금 데이터셋(사건 8개 · 사진 24장, 사건마다 3장)은 **전부 기준선에 들어가므로
자동 생성되지 않습니다.** 새로 만든 추억은 사진이 3장 이하면 전부가 대표가 되고
모델은 호출되지 않습니다 — 넘칠 때만 고르는 일이 생깁니다.

한 장에 40초쯤 걸리므로 **응답에서 기다리지 않습니다.** 서버는 맡기고 바로
응답하면서 `motion_pending`에 만들고 있는 사진을 담아 주고, 화면은
`GET /api/film/motion`으로 되물어 준비된 장면만 바꿔 끼웁니다. 그 사이에는
카메라 움직임으로 재생되고, 화면에 "만들고 있습니다"가 적힙니다.

한 번 만든 것은 계속 씁니다. 같은 사진을 다시 만들지 않고, 실패한 것도 다시
맡지 않습니다 — 화면이 주기적으로 되묻는 구조라서 실패를 재시도하면 같은
호출이 끝없이 반복됩니다.

⚠️ **이 API에는 인증이 없습니다.** CORS는 브라우저만 막고 `curl`에는 열려
있습니다(`config.py` 주석 참고). 배포에서 켜면 주소를 아는 누구나 생성을
일으킬 수 있으므로 `MOTION_AUTOGEN_MAX`가 유일한 방어선입니다. 센 횟수는
`STATE_DIR/motion_spend.json`에 남아 재시작에도 유지됩니다. 상한을 넘으면 더
만들지 않고, 클립이 없는 사진은 원래대로 카메라 움직임으로 돕니다.

배포에서 켜려면 이미지에 `ffmpeg`(Dockerfile에 넣었습니다)와
`fal-client`(requirements에 넣었습니다)가 있어야 하고 `FAL_KEY`를 줘야 합니다.
셋 중 하나라도 없으면 `MOTION_AUTOGEN`과 무관하게 꺼진 것처럼 동작합니다.

#### 미리 만들기

```bash
pip install fal-client                 # 로컬 스크립트 전용 (배포에는 안 들어갑니다)
winget install Gyan.FFmpeg             # 루프·합성용
# .env에 FAL_KEY 입력

# 무엇을 어떤 프롬프트로 만들지만 봅니다 (호출 없음, 0원)
python scripts/build_motion_covers.py E01 --dry-run

# 한 장으로 룩을 확인한 뒤 (480p 한 건 약 $0.2, 다시 뽑을 때마다 다시 과금됩니다)
python scripts/build_motion_covers.py E01 --resolution 480p
```

사건 id(`E01`)를 주면 그 사건의 대표 사진 한 장만, 사진 id(`E01_001`)를 주면
그 사진만 만듭니다. 결과는 `data/motion/`에 쌓이고 커밋 대상입니다 — 시드가
`MEDIA_DIR/motion`으로 옮기고 화면이 재생합니다. **클립이 없는 사진은 지금까지처럼
CSS 카메라 움직임으로 돕니다**, 그래서 일부만 만들어도 화면이 깨지지 않습니다.

**길이를 짧게 씁니다.** 생성 모델은 시간이 갈수록 원본에서 멀어집니다. 5초를
그대로 쓰면 끝에서 얼굴이 다른 사람이 되고 배경 인물이 사라집니다(실제로
확인했습니다). 그래서 5초를 요청해 **앞부분만** 씁니다(`--use-seconds`, 기본 2.0).
가격은 생성 건당이라 앞부분만 써도 더 들지 않습니다.

**루프가 어려운 이유는 줌입니다.** 프롬프트에 `static camera`를 넣고 negative로
막아도 모델이 지키지 않아 화면이 서서히 줌 인됩니다. 그래서 끝과 처음이 어긋나고,
`--loop-mode`의 두 방식 모두 그 대가를 치릅니다.

| 방식 | 무엇이 보이나 |
|---|---|
| `pingpong` | 역재생 구간. 줌 인이 역방향에서 줌 아웃이 되어 화면이 숨쉬듯 커졌다 작아집니다 |
| `crossfade` | 겹치는 구간의 **잔상**(반투명 이중상). 방향은 한쪽뿐입니다 |
| `none` | 다시 시작할 때 튐. 드리프트가 작으면 거의 안 보입니다 |

**움직일 것이 화면의 일부라면 마스크가 답입니다.** 그 부분만 남기고 나머지를
원본 픽셀로 고정하면 드리프트가 생길 자리가 없어서, `--loop-mode none`으로 그냥
잘라 붙여도 이음새가 보이지 않습니다. 정적 영역이 많아지므로 파일도 작아집니다.

반대로 **움직일 것이 화면의 대부분이면 마스크가 오히려 해롭습니다.** 타원으로
그린 마스크는 피사체 윤곽을 따르지 않아서, 경계에서 정지한 영역과 움직이는
영역이 맞닿아 번져 보입니다. 그때는 마스크 없이 짧게 자르는 편이 낫습니다.

지금 들어 있는 두 클립이 그 두 경우입니다.

| | 마스크 | 움직이는 곳 | 길이 · 크기 |
|---|---|---|---|
| E01 부산 | 없음 (바다가 화면 대부분) | 바다 | 2.0초 · 250KB |
| E06 캠핑 | 랜턴만 뚫음 | 불꽃 | 2.5초 · 91KB |

E06은 마스크를 씌우고 199KB → 91KB로 줄었습니다.

```bash
# 원본을 남겨 두면 루프 길이·방식을 호출 없이(0원) 다시 맞출 수 있습니다
python scripts/build_motion_covers.py E01 --resolution 480p --keep-source
python scripts/build_motion_covers.py E01 --from-source --use-seconds 3.0 --crossfade 0.6
```

남긴 원본(`data/motion/*.source.mp4`)은 커밋에서 제외됩니다 — 루프를 다시 맞출
때만 필요한 중간물입니다.

마스크는 `data/motion/masks/<media_id>.png`에 클립과 같은 크기로 두고,
**흰색 = 원본 픽셀을 유지할 영역**입니다. 두 방향으로 쓸 수 있습니다.

- 인물이 많으면 **인물만 흰색**으로 (검은 배경) → 얼굴이 변할 수가 없습니다
- 움직일 것이 하나뿐이면 **거기만 검게 뚫습니다** (흰 배경) → 그것만 움직입니다

경계는 몇 px 흐려 두면 이어 붙인 자리가 드러나지 않습니다. 마스크를 쓴 장면은
AI 라벨에 "인물은 원본"이 함께 붙습니다.

카메라 움직임과 생성된 움직임은 라벨을 나눠 적습니다 — 앞은 원본 픽셀을 옮긴
것이고 뒤는 없던 픽셀이 생긴 것이라 같은 문구로 덮지 않습니다. 라벨에 무엇이
움직이는지까지는 적지 않습니다(사진마다 다르고 틀리게 적으면 없는 것을 밝힌
셈이 됩니다). 무엇을 요청했는지는 `data/motion/manifest.json`의 `prompt`에
남습니다.

---

## 저장소

그래프 저장소를 갈아끼울 수 있습니다. 호출부는 `graph_manager` 하나만 알고,
고르는 곳은 `backend/services/graph_manager.py` 한 파일입니다.

| `DATABASE_URL` | 저장소 | 쓰는 곳 |
|---|---|---|
| 없음 | `graph.json` 한 개 (NetworkX + 파일) | 로컬 개발·데모 |
| 있음 | Postgres (`nodes`/`edges` + JSONB) | 실제 데이터 |

```bash
# 이전 (여러 번 돌려도 됩니다 — id 기준 UPSERT)
DATABASE_URL="postgresql://..." python scripts/migrate_to_postgres.py --reset

# 이후 백엔드에 DATABASE_URL만 주면 Postgres를 씁니다.
# Railway에서 Postgres를 붙이면 자동으로 주입됩니다.
```

Postgres 쪽이 없애는 것: 쓰기마다 파일 전체 재작성 · 락 없음(동시 업로드 유실) ·
검색 전수 스캔(trigram 색인). JSON 파일은 그대로 남으므로 `DATABASE_URL`을 지우면
되돌아갑니다.

의미 차이 하나: 같은 두 노드 사이에 관계가 둘 이상이면 Postgres는 모두 남기고
JSON(NetworkX)은 마지막 하나만 남깁니다. Postgres 쪽이 옳습니다.

대량 수집은 `graph_manager.batch()`로 감싸면 저장이 한 번으로 모입니다
(JSON에서 사진 400장을 한 장씩 넣으면 24초, batch로는 한 번).

---

## 검증

```bash
# 회귀 테스트 (venv 활성화 상태에서)
python tests/test_chat_search.py        # 검색 15개
python tests/test_chat_graph.py         # 질의 계획 8개
python tests/test_memories.py           # 추억 게시·기억 더하기 6개
python tests/test_events_and_voice.py   # 사건 요약·음성·화자 귀속 11개
python tests/test_film.py               # Memory Film 12개
python tests/test_motion_clips.py       # 미세 모션 클립 15개 (새 사건만·대표 선정·상한·TV)
python tests/test_family_visibility.py  # 가족 공간·초대 참여·공개 범위 18개
python tests/test_permissions.py        # 역할 가드 11개
python tests/test_interview_extraction.py # 답변에서 인물·장소·시점 추출
python tests/test_interview_questions.py  # 인터뷰 대상·없는 호칭·질문 반복 13개
python tests/test_media_person_tags.py  # 기록에 있는 사람 지목 6개
python tests/test_album.py              # 사진첩 목록·필터·커서·공개 범위·삭제 23개
python tests/test_transcript_source.py  # 전사문 출처·녹음 분류 7개
python tests/test_video_upload.py       # 영상 길이·첫 장면 썸네일 4개
python tests/test_tv_motion.py          # TV가 미세 모션 클립을 쓰는지 5개
python tests/test_faces.py              # 얼굴 인식 가드 9개
python tests/test_geocoder.py           # 좌표 -> 대략적인 지명 7개

# 같은 테스트를 Postgres 저장소로도 돌립니다 (구현이 갈리지 않게)
DATABASE_URL="postgresql://..." python tests/test_memories.py

# Postgres 저장소 자체의 회귀 (검색 이스케이프·동시 쓰기·트랜잭션·순서)
# 운영 DB를 건드리지 않으려고 별도 변수를 씁니다. 없으면 스스로 건너뜁니다.
TEST_DATABASE_URL="postgresql://..." python tests/test_store_pg.py   # 8개

# Memory Trust Harness — 정답표로 실제 질의를 돌려 채점
python scripts/enroll_faces.py --dry-run       # 얼굴 등록 계획 보기 (0원)
python scripts/enroll_faces.py                 # 가족 얼굴 등록 (Rekognition)
python scripts/describe_photos.py              # 사진 장면 설명 채우기 (장당 약 8초)
python scripts/run_trust_harness.py            # 20문항 (LLM 호출, 수 분)
python scripts/run_trust_harness.py --limit 5  # 앞 5문항만
```

채점 결과는 `data/trust_report.json`에 저장되고 `/trust` 화면이 그 파일을 읽습니다.
정답표는 `data/goldset.json`이며, 그래프를 바꾸면 함께 손봐야 합니다.

측정하는 것: 근거 회수율 · 기록 없음을 없다고 말하는 정직성 · 인물 귀속 안전성 ·
관계 정합성(정답 메타데이터 대조) · Film 효과가 허용 범위 안인지 · 원본 파일과
그래프 참조의 정합성.

---

## 배포 구성

프론트(Vercel)와 백엔드(Railway)를 따로 올립니다. **둘을 서로 알려 줘야** 동작합니다 —
프론트는 백엔드 주소를, 백엔드는 프론트 도메인을 알아야 합니다.

### 1. 백엔드 (Railway)

1. Railway에서 New Project → Deploy from GitHub repo → 이 저장소 선택
2. Root Directory는 저장소 루트 그대로 둡니다 (`Dockerfile`이 루트에 있습니다)
3. Variables에 넣습니다:

| 변수 | 값 | 필요성 |
|------|-----|--------|
| `ALLOWED_ORIGINS` | `https://<내-앱>.vercel.app` | **필수.** 없으면 브라우저가 요청을 막아 화면이 빈 채로 뜹니다 |
| `EXAONE_API_KEY` | 발급받은 키 | 없으면 채팅·인터뷰·내레이션이 시뮬레이션 문장으로 동작합니다 |
| `EXAONE_API_URL`, `EXAONE_MODEL` | `.env.example` 참고 | 키를 넣을 때 함께 |
| `DATABASE_URL` | Postgres 접속 문자열 | 없으면 `graph.json` 한 파일을 씁니다. Railway에서 Postgres를 붙이면 자동 주입됩니다 |
| `APP_BASE_URL` | `https://<내-앱>.vercel.app` | 초대 링크에 쓰입니다. 없으면 화면이 자기 주소로 링크를 만듭니다 |

Vercel 프리뷰 도메인(커밋마다 바뀜)은 `ALLOWED_ORIGIN_REGEX` 기본값
(`https://.*\.vercel\.app`)으로 함께 허용됩니다.

시드는 빌드가 아니라 **시작할 때** 돌아갑니다 (`scripts/docker_start.sh`).
`--if-empty`라서 저장소가 비어 있을 때만 넣습니다 — 재배포해도 가족이 쌓은 기억을
지우지 않습니다. 배포 후 확인:

```
GET https://<앱>.up.railway.app/api/health   -> {"status":"ok"}
GET https://<앱>.up.railway.app/api/family   -> 구성원 목록
```

`/api/family`가 404면 예전 코드가 떠 있는 것입니다.

#### 데이터를 어디에 둘지 (둘 중 하나는 해야 합니다)

업로드한 사진·녹음과 그래프는 컨테이너 파일시스템에 쌓입니다. 그대로 두면
재배포할 때 사라집니다 — 발표 중 녹음한 목소리도 함께.

**(a) 볼륨** — Railway에서 Volume을 만들어 **`/app/var`** 에 마운트합니다
(`STATE_DIR` 기본값). 읽기 전용 자산(`data/metadata`, `data/photos`)은 이미지에
그대로 있으니 `data/`에 마운트하면 안 됩니다 — 시드 원본이 가려져 빈 화면이 됩니다.

**(b) Postgres** — Railway에서 Postgres를 붙이면 `DATABASE_URL`이 주입되고 그래프가
DB에 들어갑니다. 파일로 쌓이는 것은 업로드한 미디어뿐이라, 미디어까지 지키려면
볼륨도 함께 붙입니다.

이미 파일로 쓰던 그래프를 Postgres로 옮기려면:

```bash
DATABASE_URL="postgresql://..." python scripts/migrate_to_postgres.py
```

JSON 파일은 그대로 남습니다. `DATABASE_URL`을 지우면 다시 파일로 돌아갑니다.

### 2. 프론트 (Vercel)

1. Add New → Project → 이 저장소 Import
2. **Root Directory: `frontend`** (이걸 빼면 빌드가 실패합니다)
3. Framework Preset은 Vite로 자동 감지됩니다 (`npm run build` → `dist`)
4. Environment Variables:

| 변수 | 값 |
|------|-----|
| `VITE_API_URL` | `https://<내-railway-앱>.up.railway.app/api` |

`VITE_API_URL`을 넣지 않으면 프론트가 자기 도메인의 `/api`를 부르고, 거기엔 백엔드가
없어서 사이드바에 "연결 안 됨"이 표시됩니다.

`frontend/.env.production`에는 주소를 적지 않습니다. 파일에 박아 두면 다른 사람의
백엔드로 붙는 사고가 납니다.

### 3. 배포 후 확인

- 사이드바에 가족 이름이 뜨는가 (안 뜨면 `VITE_API_URL` 또는 `ALLOWED_ORIGINS`)
- 타임라인·지도에 사건 8개와 지도 점이 보이는가 (안 보이면 백엔드가 옛 코드)
- 채팅에 질문했을 때 근거 뱃지가 붙는가 (안 붙으면 `EXAONE_API_KEY` 확인)

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
- `confidence`: confirmed / ai_inferred / user_unverified — 자료 출처의 신뢰도
- `source`: exif / user_input / ai_vision / ai_stt / interview
- `state`: alone / shared / varied — 추억에 기억이 얼마나 쌓였는가.
  확인 상태가 아니다. 추억은 한 사람이 만들면 그 순간 게시되고, `varied`(가족이
  조금 다르게 기억함)도 해결할 문제가 아니라 그대로 보존하는 사실이다.

---

## API 엔드포인트 요약

| 도메인 | 엔드포인트 | 설명 |
|--------|-----------|------|
| Health | `GET /api/health` | 서버 상태 |
| Media | `POST /api/media/upload` | 파일 업로드 + 자동 분석 (음성은 길이·파형·전사, 영상은 길이·첫 장면을 함께 받음) |
| | `PUT /api/media/{id}/persons` | 이 기록에 있는 사람 지목 (보낸 목록이 최종 상태) |
| | `GET /api/media` | 미디어 목록 (`?media_type=audio&person_id=P02`) |
| | `GET /api/media/album` | 사진첩 — 사진·영상만, 사건·인물·장소를 붙여 커서로 나눠 준다 (`?year=2025&person_id=P02&types=photo&event_status=unlinked`) |
| | `POST /api/media/bulk-delete` | 고른 원본 여러 개를 한 번에 삭제 (막힌 것은 이유와 함께 돌려준다) |
| Graph | `GET /api/graph` | 전체 노드+엣지 |
| | `GET /api/graph/events` | 사건 목록 + 장소 좌표·참여자·썸네일·기억 상태 |
| | `GET /api/graph/event/{id}` | 이벤트 상세 |
| | `GET /api/graph/persons` | 인물 목록 |
| | `POST /api/graph/person` | 인물 추가 |
| Chat | `POST /api/chat` | 자연어 질의 → 답변 |
| Interview | `POST /api/interview/start` | 인터뷰 시작 (`speaker_id` — 질문받는 사람) |
| | `POST /api/interview/answer` | 답변 제출 (`speaker_id`, `audio_media_id`) |
| Memories | `POST /api/memories/draft` | 올린 사진·영상으로 추억 초안 (제목·날짜·장소·인물·근거) |
| | `POST /api/memories` | 추억 만들기 (저장 즉시 게시, 승인 없음) |
| | `GET /api/memories/feed` | 기억 이어가기 목록 |
| | `GET /api/memories/{id}` | 추억 상세 (작성자의 기억 + 가족이 더한 기억) |
| | `POST /api/memories/{id}/echo` | 나도 기억나요 (토글) |
| | `POST /api/memories/{id}/memory` | 내 기억 더하기 (글·목소리·사진, 원본 보존) |
| | `POST /api/memories/{id}/media` | 기존 추억에 사진·영상 추가 |
| | `POST /api/memories/{id}/story` | 함께 기억한 이야기 생성 (누가 맞는지 판정하지 않음) |
| Film | `POST /api/film` | 사건 하나를 30~60초 이야기로 구성 |
| | `GET /api/film/anniversaries` | 다가오는 기념일 |
| Trust | `GET /api/trust/report` | 마지막 채점 리포트 |
| | `POST /api/trust/run` | 채점 실행 (LLM 호출, 수 분) |
| Family | `GET /api/family` | 가족 공간 · 구성원 · 역할 · 초대 |
| | `PUT /api/family/member/{id}` | 역할 변경 · 비공개 요청 |
| | `POST /api/family/invite` | 초대 링크 발급 (72시간) |
| | `GET /api/family/invite/{code}` | 코드가 아직 쓸 수 있는지 |
| | `POST /api/family/join` | 초대 코드로 참여 (코드는 한 번 쓰면 소진) |
| | `PUT /api/family/media/{id}/visibility` | 기록별 공개 범위 |
| | `GET /api/family/media/{id}/cascade` | 삭제 영향 미리보기 |
| Export | `GET /api/export/manifest` | 내보낼 항목과 실제 용량 |
| | `POST /api/export` | 아카이브(zip) 생성 |
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

- `docs/USER_GUIDE.md` — 사용법 (화면별 조작, TV 리모컨, 막혔을 때)
- `docs/MVP_DESIGN.md` — 설계 상세 (Graph 스키마, API, 화면 구성)
- `docs/SPEC_SUMMARY.md` — API 호출 형식 전체 정리
- `.env.example` — 환경변수 설명
