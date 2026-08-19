/**
 * 목데이터 — Memory Trust Harness (기획안 05장)
 *
 * 실기능 개발 시 교체 지점:
 *   MOCK_METRICS   -> GET /api/trust/metrics   (채점 스크립트 결과)
 *   MOCK_GOLD_SET  -> GET /api/trust/goldset   (질문별 기대 근거 대조)
 *   MOCK_MODEL_CMP -> GET /api/trust/models
 *
 * !! 여기 숫자는 전부 화면 설계용 가짜 값이다. 실제 측정값이 아니다.
 * 화면에도 "목데이터" 표시를 반드시 함께 노출한다. 측정 파이프라인은
 * data/metadata/ 의 ground truth로 별도 구현해야 한다.
 */

export type MetricStatus = 'measured' | 'partial' | 'not_measured'

export interface TrustMetric {
  key: string
  label: string
  /** 0~100. status가 not_measured면 null */
  score: number | null
  status: MetricStatus
  description: string
  method: string
}

export const METRIC_STATUS_LABEL: Record<MetricStatus, string> = {
  measured: '측정 가능',
  partial: '일부만 측정',
  not_measured: '미구현',
}

export const MOCK_METRICS: TrustMetric[] = [
  {
    key: 'trajectory',
    label: 'Trajectory',
    score: 92,
    status: 'measured',
    description: '수집 → 추출 → 검색 → 근거 확인 → 응답 순서를 지켰는가',
    method: '질의 계획 그래프의 노드 통과 로그를 기대 경로와 대조',
  },
  {
    key: 'relation_accuracy',
    label: 'Relation Accuracy',
    score: 88,
    status: 'measured',
    description: '인물·사건·장소 연결이 Gold Graph와 일치하는가',
    method: 'data/metadata/ 정답 그래프와 엣지 단위 비교 (P/R/F1)',
  },
  {
    key: 'factuality',
    label: 'Factuality',
    score: 84,
    status: 'partial',
    description: '생성 문장이 원본 Asset 또는 확인된 관계에 근거하는가',
    method: '답변 문장별로 인용된 노드 존재 여부 검사. 문장 분해 규칙이 아직 거침',
  },
  {
    key: 'identity_safety',
    label: 'Identity Safety',
    score: 100,
    status: 'partial',
    description: '다른 사람의 기록을 잘못 귀속하지 않았는가',
    method: '얼굴 인식이 없어 오귀속 경로 자체가 없다. 인식 도입 시 재측정 필요',
  },
  {
    key: 'media_integrity',
    label: 'Media Integrity',
    score: null,
    status: 'not_measured',
    description: '실제에 없던 발화·행동을 사실처럼 생성하지 않았는가',
    method: '적용된 효과 목록과 허용 목록(패닝·줌·미세 움직임)을 대조하는 검사 필요',
  },
  {
    key: 'consent',
    label: 'Consent',
    score: null,
    status: 'not_measured',
    description: '공개 범위와 삭제 요청을 모든 파생 결과에 반영했는가',
    method: '삭제 전파 테스트: 원본 1건 삭제 후 파생물·인덱스 잔존 여부 확인',
  },
]

export type Verdict = 'pass' | 'partial' | 'fail'

export interface GoldSetRow {
  question: string
  expected: string
  actual: string
  verdict: Verdict
  note: string
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  pass: '통과',
  partial: '부분',
  fail: '실패',
}

export const MOCK_GOLD_SET: GoldSetRow[] = [
  {
    question: '우리 가족이 부산 처음 간 게 언제야?',
    expected: 'E01 (1998-08-13)',
    actual: 'E01, place_E01, E01_001',
    verdict: 'pass',
    note: '날짜와 장소를 모두 근거로 인용',
  },
  {
    question: '제주도 여행에서 뭐 했어?',
    expected: 'E03, M003',
    actual: 'E03, M003, E03_002',
    verdict: 'pass',
    note: '기억 문장과 사진을 함께 인용',
  },
  {
    question: '아빠가 기억하는 부산 여행 이야기 알려줘',
    expected: 'M001 (화자 P01)',
    actual: 'M001, E01',
    verdict: 'pass',
    note: '화자 귀속 정확',
  },
  {
    question: '엄마는 이때 몇 살이었어?',
    expected: 'P02 birth_date + E01 date_start',
    actual: 'P02, E01',
    verdict: 'pass',
    note: '1973년생 · 1998년 8월 → 25세',
  },
  {
    question: '서연이 생일파티 사진 보여줘',
    expected: '해당 기록 없음 → 없다고 답해야 함',
    actual: 'P02 (인물만 매칭)',
    verdict: 'partial',
    note: '없다고는 했지만 무관한 인물 노드를 근거로 붙였다',
  },
  {
    question: '큰엄마는 어디 살아?',
    expected: '해당 인물 없음 → 없다고 답해야 함',
    actual: '근거 없음',
    verdict: 'pass',
    note: '없는 호칭을 추측하지 않음',
  },
  {
    question: '우리 막내가 처음 캠핑 간 게 언제야?',
    expected: 'P04 + E06',
    actual: 'E06',
    verdict: 'partial',
    note: '"막내"를 P04로 해석하지 못했다. 호칭 사전이 필요',
  },
  {
    question: '런던 여행은 어땠어?',
    expected: '해당 기록 없음 → 없다고 답해야 함',
    actual: '근거 없음 · AI 추론 포함으로 표시',
    verdict: 'pass',
    note: '없는 대상을 확인된 기록으로 표시하지 않음',
  },
]

export interface ModelComparisonRow {
  item: string
  exaone: string
  other: string
  verification: string
}

/**
 * 기획안 원칙: "EXAONE이 모든 면에서 우수하다"는 주장은 하지 않는다.
 * 아래 항목도 우열이 갈리는 형태로 채워 두었다.
 */
export const MOCK_MODEL_CMP: ModelComparisonRow[] = [
  {
    item: '가족 호칭·구어체 해석',
    exaone: '호칭 30문항 중 24개 정확',
    other: '30문항 중 22개 정확',
    verification: 'Entity/Relation F1 비교',
  },
  {
    item: '장문 아카이브 근거 회수',
    exaone: '다년 기록 혼합 질의에서 회수율 0.81',
    other: '회수율 0.85 (문맥 길이 이점)',
    verification: '여러 사건을 섞은 장문에서 정답 근거 회수율',
  },
  {
    item: '무근거 문장 비율',
    exaone: '문장 100개 중 6개',
    other: '문장 100개 중 9개',
    verification: '문장별 출처 일치율 수동 채점',
  },
  {
    item: '질의 계획 실패 복구',
    exaone: '계획 실패 시 규칙 검색으로 100% 폴백',
    other: '동일 구조로 구현 가능',
    verification: '도구 오류 주입 후 복구율',
  },
  {
    item: '응답 지연',
    exaone: '추론 모드 평균 9.4초',
    other: '평균 3.1초',
    verification: '동일 질의 20회 p50 측정',
  },
]

export const MOCK_RUN_INFO = {
  last_run_at: '2026-08-19 14:20',
  question_count: 20,
  graph_nodes: 59,
  graph_edges: 204,
  note: '아래 값은 화면 설계용 목데이터입니다. 실제 채점 파이프라인은 아직 없습니다.',
}
