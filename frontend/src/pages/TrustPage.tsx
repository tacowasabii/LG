/**
 * 신뢰도 리포트 — Memory Trust Harness (기획안 05장)
 *
 * 기획안이 평가항목 "구현 완성도"에 직접 내건 약속이다. 여기 있는 숫자는
 * data/goldset.json 정답표로 실제 질의를 돌려 채점한 결과다
 * (backend/services/trust_harness.py · scripts/run_trust_harness.py).
 *
 * 채점은 LLM 호출이 문항마다 들어가 몇 분 걸리므로 화면에서 돌리지 않는다.
 * 미리 돌려 저장한 리포트를 읽고, 아직 없으면 실행 방법을 알려 준다 —
 * 발표 중에 눌러서 기다리는 화면이 되지 않게.
 *
 * 칼럼 이름을 "실제 근거"에서 "답변이 읽은 기록"으로 바꿨다. 없는 것을 물은 문항
 * (no_record)에서도 검색은 가장 가까운 노드를 돌려주므로 이 칼럼이 늘 찬다 — "실제
 * 근거"라고 부르면 그 기록이 있다는 뜻으로 읽힌다. 판정은 이 목록이 아니라 신뢰도
 * 라벨(confidence)로 한다 (chat_engine._finish).
 *
 * 표를 <table>에서 grid로 옮겼다. 판정 칸에 알약과 사유 문장이 함께 들어가면서
 * 행 높이가 제각각이 되는데, grid는 열 너비를 고정하면서도 각 칸이 위로 정렬되어
 * 여러 줄을 훑을 때 눈이 열을 따라간다.
 */

import { useEffect, useState } from 'react'
import { TrustReport, TrustQuestionRow, getTrustReport } from '../lib/api'
import { Page, PageHeader } from '../components/Page'

type Verdict = TrustQuestionRow['verdict']

const VERDICT_LABEL: Record<Verdict, string> = {
  pass: '통과',
  partial: '부분',
  fail: '실패',
}

const VERDICT_STYLE: Record<Verdict, { bg: string; fg: string }> = {
  pass: { bg: 'var(--positive-soft)', fg: 'var(--positive-ink)' },
  partial: { bg: 'var(--critical-soft)', fg: 'var(--critical-ink)' },
  fail: { bg: 'var(--critical-soft)', fg: 'var(--critical-ink)' },
}

const GOLD_COLS = '2fr 1.2fr 1.4fr 150px'

export default function TrustPage() {
  const [report, setReport] = useState<TrustReport | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getTrustReport()
      .then(setReport)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Page width={1000}>
        <p className="t-caption">불러오는 중…</p>
      </Page>
    )
  }

  // 아직 채점하지 않았다 — 가짜 숫자를 채우지 않고 실행 방법을 알린다
  if (!report?.ran) {
    return (
      <Page width={1000}>
        <PageHeader
          eyebrow="Memory Trust Harness"
          title="신뢰도 리포트"
          lead="답변이 실제 기록에 근거하는지, 관계가 정답 그래프와 맞는지 측정합니다."
        />
        <div
          className="mt-10 rounded-lg px-7 py-8"
          style={{ border: '1px dashed var(--border-strong)' }}
        >
          <p className="m-0 text-[17px] font-semibold text-ink-900">아직 채점하지 않았습니다</p>
          <p className="t-body-sm mt-2.5 max-w-[45em]">
            정답표 {report?.question_count ?? 0}문항이 준비되어 있습니다. 아래 명령으로 채점하면
            결과가 이 화면에 남습니다. 문항마다 실제 질의를 돌리므로 몇 분 걸립니다.
          </p>
          <pre
            className="t-mono mt-5 overflow-x-auto rounded px-4 py-3 text-xs"
            style={{ background: 'var(--ink-50)', color: 'var(--ink-700)' }}
          >
            python scripts/run_trust_harness.py
          </pre>
          <p className="t-caption mt-4">
            빠르게 확인하려면 <span className="t-mono">--limit 5</span> 를 붙여 앞 5문항만 돌릴 수
            있습니다.
          </p>
        </div>
      </Page>
    )
  }

  const counts = report.counts
  const details = report.details
  const badges: Array<{ label: string; value: number; bg: string; fg: string }> = counts
    ? [
        {
          label: '통과',
          value: counts.pass,
          bg: 'var(--positive-soft)',
          fg: 'var(--positive-ink)',
        },
        {
          label: '부분',
          value: counts.partial,
          bg: 'var(--critical-soft)',
          fg: 'var(--critical-ink)',
        },
        { label: '실패', value: counts.fail, bg: 'var(--ink-50)', fg: 'var(--ink-400)' },
      ]
    : []

  return (
    <Page width={1000}>
      <PageHeader
        eyebrow="Memory Trust Harness"
        title="신뢰도 리포트"
        lead="답변이 실제 기록에 근거하는지, 관계가 정답 그래프와 맞는지 측정합니다."
      />

      {/* LLM 없이 돌린 결과는 품질 측정이 아니다. 지표보다 먼저 밝힌다. */}
      {report.llm_enabled === false && (
        <p
          className="t-body-sm mt-8 rounded-lg px-6 py-5"
          style={{ background: 'var(--critical-soft)', color: 'var(--critical-ink)' }}
        >
          LLM 키 없이 시뮬레이션 응답으로 채점한 결과입니다. 실제 답변 품질이 아닙니다.
        </p>
      )}

      <div className="rule-strong mt-8 grid grid-cols-4">
        {[
          { label: '마지막 채점', value: (report.ran_at || '').replace('T', ' ') },
          { label: '문항 수', value: (counts?.total ?? 0) + '개' },
          { label: '그래프 노드', value: (report.graph?.nodes ?? 0) + '개' },
          { label: '그래프 엣지', value: (report.graph?.edges ?? 0) + '개' },
        ].map((r, i) => (
          <div
            key={r.label}
            className="py-[18px] pr-6"
            style={
              i === 0 ? undefined : { paddingLeft: 28, borderLeft: '1px solid var(--border)' }
            }
          >
            <p className="t-caption m-0">{r.label}</p>
            <p className="t-mono m-0 mt-1.5 text-sm text-ink-900">{r.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-4">측정 지표</p>
        <div className="grid grid-cols-2 gap-4">
          {(report.metrics || []).map((metric) => (
            <div key={metric.key} className="surface p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="m-0 text-[15px] font-semibold text-ink-900">{metric.label}</p>
                  <p className="t-caption m-0 mt-1.5">{metric.description}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p
                    className="m-0 text-[32px] font-bold leading-none tracking-display"
                    style={{ color: metric.score == null ? 'var(--ink-200)' : 'var(--ink-900)' }}
                  >
                    {metric.score == null ? '—' : metric.score}
                  </p>
                  <p
                    className="t-caption m-0 mt-1"
                    style={{
                      color: metric.score == null ? 'var(--ink-300)' : 'var(--positive-ink)',
                    }}
                  >
                    {metric.score == null ? '측정 대상 없음' : '측정됨'}
                  </p>
                </div>
              </div>

              {metric.score != null && (
                <div className="mt-[18px] h-0.5" style={{ background: 'var(--ink-100)' }}>
                  <div
                    className="h-0.5"
                    style={{
                      background: metric.score >= 90 ? 'var(--accent)' : 'var(--critical)',
                      width: metric.score + '%',
                    }}
                  />
                </div>
              )}

              <p className="t-caption mt-3.5 text-ink-300">측정 방법 · {metric.method}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-10">
        <div className="flex flex-wrap items-baseline justify-between gap-5">
          <div>
            <p className="t-eyebrow m-0">Gold Set 채점</p>
            <p className="t-caption m-0 mt-1">
              질문마다 어떤 근거가 나와야 하는지 미리 정해두고 대조합니다. 기록이 없어야 하는
              질문은 “없다”고 답하는지를 봅니다. “답변이 읽은 기록”은 그 답을 쓸 때 모델이 읽은
              자료이며, 질문이 사실이라는 증거가 아닙니다 — 없는 것을 물으면 가장 가까운 기록이
              대신 잡힙니다.
            </p>
          </div>
          <div className="flex gap-1.5">
            {badges.map((c) => (
              <span
                key={c.label}
                className="pill px-2.5 py-1"
                style={{ background: c.bg, color: c.fg }}
              >
                {c.label} {c.value}
              </span>
            ))}
          </div>
        </div>

        <div className="rule-strong mt-4">
          <div
            className="grid gap-4 px-1 py-2.5"
            style={{ gridTemplateColumns: GOLD_COLS, borderBottom: '1px solid var(--border)' }}
          >
            <span className="t-eyebrow text-ink-300">질문</span>
            <span className="t-eyebrow text-ink-300">나와야 할 근거</span>
            <span className="t-eyebrow text-ink-300">답변이 읽은 기록</span>
            <span className="t-eyebrow text-ink-300">판정</span>
          </div>
          {(report.questions || []).map((row) => (
            <div
              key={row.id || row.query}
              className="grid items-start gap-4 px-1 py-3.5"
              style={{ gridTemplateColumns: GOLD_COLS, borderBottom: '1px solid var(--border)' }}
            >
              <span className="text-sm text-ink-900">{row.query}</span>
              <span className="t-caption text-ink-400">{row.expected}</span>
              <span className="t-caption text-ink-400">{row.actual}</span>
              <span>
                <span
                  className="pill px-[9px]"
                  style={{
                    background: VERDICT_STYLE[row.verdict].bg,
                    color: VERDICT_STYLE[row.verdict].fg,
                  }}
                >
                  {VERDICT_LABEL[row.verdict]}
                </span>
                <span className="t-caption mt-1.5 block text-ink-300">{row.note}</span>
                {row.unsupported_persons.length > 0 && (
                  <span
                    className="t-caption mt-1 block"
                    style={{ color: 'var(--critical-ink)' }}
                  >
                    근거 없이 언급: {row.unsupported_persons.join(', ')}
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 그래프·파일 검사 결과 */}
      {details && (
        <div className="mt-10">
          <p className="t-eyebrow m-0 mb-4">그래프 · 파일 검사</p>
          <div className="grid grid-cols-3 gap-4">
            <div className="surface p-6">
              <p className="m-0 text-sm font-semibold text-ink-900">관계 정합성</p>
              <p className="t-caption m-0 mt-2">
                기대 관계 {details.relations.expected}개 중 {details.relations.found}개 일치
              </p>
              <p
                className="t-caption m-0 mt-1"
                style={{
                  color:
                    details.relations.missing_count > 0
                      ? 'var(--critical-ink)'
                      : 'var(--positive-ink)',
                }}
              >
                누락 {details.relations.missing_count}개
              </p>
            </div>
            <div className="surface p-6">
              <p className="m-0 text-sm font-semibold text-ink-900">Film 효과</p>
              <p className="t-caption m-0 mt-2">
                장면 {details.media_integrity.scenes_checked}개 검사
              </p>
              <p
                className="t-caption m-0 mt-1"
                style={{
                  color:
                    details.media_integrity.violation_count > 0
                      ? 'var(--critical-ink)'
                      : 'var(--positive-ink)',
                }}
              >
                허용 범위 위반 {details.media_integrity.violation_count}건
              </p>
            </div>
            <div className="surface p-6">
              <p className="m-0 text-sm font-semibold text-ink-900">원본 파일</p>
              <p className="t-caption m-0 mt-2">
                미디어 {details.asset_integrity.media_total}개 검사
              </p>
              <p
                className="t-caption m-0 mt-1"
                style={{
                  color:
                    details.asset_integrity.missing_file_count +
                      details.asset_integrity.orphan_edge_count >
                    0
                      ? 'var(--critical-ink)'
                      : 'var(--positive-ink)',
                }}
              >
                파일 없음 {details.asset_integrity.missing_file_count} · 고아 엣지{' '}
                {details.asset_integrity.orphan_edge_count}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 모델 비교는 다른 모델을 실제로 돌린 뒤에만 적는다 */}
      <div className="mt-10">
        <p className="t-eyebrow m-0">모델 비교</p>
        <p className="t-body-sm mt-2 max-w-[52em]">
          아직 비교하지 않았습니다. 기획안이 정한 방식은 같은 정답표를 다른 모델로 돌려 근거
          회수율과 무근거 문장 비율을 나란히 놓는 것입니다. 다른 모델 키를 넣고{' '}
          <span className="t-mono text-xs">EXAONE_MODEL</span> 을 바꿔 다시 채점하면 이 자리에
          두 결과가 함께 남습니다. “EXAONE이 모든 면에서 우수하다”는 문장은 쓰지 않습니다.
        </p>
      </div>
    </Page>
  )
}
