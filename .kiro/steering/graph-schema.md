---
inclusion: manual
---

# Memory Graph 스키마 레퍼런스

이 문서는 Graph의 노드/엣지 구조와 데이터 규약을 정리한 참조 문서입니다.
Graph 관련 작업 시 `#graph-schema`로 불러서 사용하세요.

## 저장 구조

- **런타임**: NetworkX DiGraph (메모리)
- **영속화**: `data/graph.json` (노드 배열 + 엣지 배열)
- **관리**: `GraphManager` 싱글톤 (변경 시 자동 save)

```json
{
  "nodes": [{ "id": "...", "node_type": "...", ...속성들 }],
  "edges": [{ "source": "...", "target": "...", "relation": "...", "properties": {} }]
}
```

---

## 노드 타입 (5종)

### Person

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | `person_{uuid8}` 또는 Ground truth의 경우 `P01`~`P05` |
| node_type | string | `"person"` |
| name | string | 이름 (한국어) |
| relation | string | 관계 (`"아빠"`, `"엄마"`, `"딸"`, `"아들"`, `"할머니"`, `"친구"`, `"연인"`) |
| birth_year | int? | 출생 연도 |
| thumbnail_url | string? | 프로필 이미지 경로 |
| created_at | string | ISO datetime |

### Event

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | `event_{uuid8}` 또는 `E01`~`E08` |
| node_type | string | `"event"` |
| title | string | 이벤트 제목 (예: "1998 부산 가족여행") |
| description | string | 설명 |
| date_start | string? | ISO date (`"1998-08-13"`) |
| date_end | string? | ISO date (단일 날이면 null) |
| location_id | string? | 연결된 Place 노드 ID |
| confidence | string | `confirmed` / `ai_inferred` / `user_unverified` |
| source | string | `exif` / `user_input` / `ai_vision` / `interview` |
| created_at | string | ISO datetime |

### Place

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | `place_{uuid8}` |
| node_type | string | `"place"` |
| name | string | 장소명 (예: "부산 광안리 해수욕장") |
| address | string? | 주소 |
| lat | float? | 위도 |
| lng | float? | 경도 |
| created_at | string | ISO datetime |

### Media

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | `media_{uuid8}` 또는 `E01_001` 형식 |
| node_type | string | `"media"` |
| media_type | string | `"photo"` / `"video"` / `"audio"` |
| file_path | string | 서빙 경로 (예: `/media-files/E01_001.jpg`) |
| thumbnail_path | string? | 썸네일 경로 |
| original_filename | string | 원본 파일명 |
| exif_date | string? | EXIF에서 추출한 촬영 일시 |
| exif_lat | float? | EXIF 위도 |
| exif_lng | float? | EXIF 경도 |
| exif_camera | string? | 카메라 정보 |
| detected_faces | list[str] | 감지된 인물 ID 목록 |
| scene_description | string? | AI가 생성한 장면 설명 |
| confidence | string | 데이터 확실도 |
| source | string | 데이터 출처 |
| created_at | string | ISO datetime |

### Memory

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | `memory_{uuid8}` |
| node_type | string | `"memory"` |
| content | string | 기억 내용 (한국어 텍스트) |
| source_type | string | `user_input` / `interview` |
| contributor_id | string? | 이 기억을 제공한 Person ID |
| confidence | string | `confirmed` / `ai_inferred` / `user_unverified` |
| created_at | string | ISO datetime |

---

## 엣지 타입 (8종)

| relation | From → To | 의미 | 예시 |
|----------|-----------|------|------|
| `participated_in` | Person → Event | 인물이 이벤트에 참여 | 김민수 → 부산여행 |
| `captured_during` | Media → Event | 미디어가 이벤트 중 촬영됨 | E01_001.jpg → 부산여행 |
| `taken_at` | Media → Place | 미디어 촬영 장소 | E01_001.jpg → 광안리 |
| `depicts` | Media → Person | 미디어에 인물 등장 | E01_001.jpg → 김하늘 |
| `located_at` | Event → Place | 이벤트 발생 장소 | 부산여행 → 광안리 |
| `remembers` | Person → Memory | 인물이 기억을 보유 | 김민수 → "캠코더를..." |
| `about` | Memory → Event | 기억이 이벤트에 대한 것 | "캠코더를..." → 부산여행 |
| `related_to` | Person → Person | 사람 사이 관계 (가족·친구·연인) | 김민수 → 김하늘 |

**엣지 properties 예시**:
```json
{ "role": "주인공" }
{ "confidence": 0.9 }
{ "relation_type": "부녀" }
```

---

## 신뢰도 모델

### confidence (확실도)

| 값 | 의미 | 사용 시점 |
|----|------|-----------|
| `confirmed` | 사용자가 확인함 | 직접 입력, 검증 완료 |
| `ai_inferred` | AI 추론 결과 | 자동 이벤트 매칭, 얼굴 인식 |
| `user_unverified` | 입력됐지만 미확인 | 업로드 직후, 시스템 생성 |

### source (출처)

| 값 | 의미 |
|----|------|
| `exif` | 사진 EXIF 메타데이터에서 추출 |
| `user_input` | 사용자가 UI에서 직접 입력 |
| `ai_vision` | AI 이미지 분석으로 추출 |
| `ai_stt` | AI 음성→텍스트 변환 |
| `interview` | AI 인터뷰 세션에서 수집 |

---

## 현재 데이터 규모 (Ground Truth)

- **Person**: 5명 (P01 김민수/아빠, P02 박서연/엄마, P03 김하늘/딸, P04 김지우/아들, P05 이정자/할머니)
- **Event**: 8개 (E01~E08, 1998~2024년)
- **Media**: 24장 사진 + 4개 영상
- **Memory**: 8개 (이벤트별 1개씩, 각기 다른 가족 구성원 시점)
- **Place**: 이벤트별 1개씩

---

## ID 체계

| 타입 | 패턴 | 예시 |
|------|------|------|
| Ground truth Person | `P{번호}` | `P01`, `P02` |
| Ground truth Event | `E{번호}` | `E01`, `E08` |
| Ground truth Media | `E{이벤트번호}_{순번}` | `E01_001`, `E03_002` |
| 동적 생성 | `{타입}_{uuid8}` | `person_a1b2c3d4`, `event_e5f6g7h8` |
