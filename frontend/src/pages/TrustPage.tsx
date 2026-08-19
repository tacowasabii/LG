/**
 * 신뢰도 리포트 — Memory Trust Harness (기획안 05장)
 *
 * 기획안이 평가항목 "구현 완성도"에 직접 내건 약속이다: 6개 지표와 Gold Set으로
 * 정확성을 검증한다. 지금은 채점 파이프라인이 없어 화면부터 만들었다.
 * 숫자는 전부 목데이터이며 화면에도 그렇게 표시한다.
 *
 * 표를 <table>에서 grid로 옮겼다. 판정 칸에 알약과 사유 문장이 함께 들어가면서
 * 행 높이가 제각각이 되는데, grid는 열 너비를 고정하면서도 각 칸이 위로 정렬되어
 * 여러 줄을 훑을 때 눈이 열을 따라간다.
 *
 * 실기능 개발 시 교체 지점:
 *   MOCK_METRICS   -> GET /api/trust/metrics
 *   MOCK_GOLD_SET  -> GET /api/trust/goldset  (data/metadata/ 정답과 대조)
 *   MOCK_MODEL_CMP -> GET /api/trust/models
 *   "채점 다시 돌리기" -> POST /api/trust/run
 */

import { useEffect, useState } from 'react'
import {
  METRIC_STATUS_LABEL,
  MOCK_GOLD_SET,
  MOCK_METRICS,
  MOCK_MODEL_CMP,
  MOCK_RUN_INFO,
  VERDICT_LABEL,
  Verdict,
} from '../mock/trust'
import { Page, PageHeader } from '../components/Page'

const VERDICT_STYLE: Record<Verdict, { bg: string; fg: string }> = {
  pass: { bg: 'var(--positive-soft)', fg: 'var(--positive-ink)' },
  partial: { bg: 'var(--critical-soft)', fg: 'var(--critical-ink)' },
  fail: { bg: 'var(--critical-soft)', fg: 'var(--critical-ink)' },
}

const GOLD_COLS = '2fr 1.4fr 1.4fr 130px'
const MODEL_COLS = '1.3fr 1.5fr 1.5fr 1.4fr'

export default function TrustPage() {
  const [running, setRunning] = useState(false)
  const [ranAt, setRanAt] = useState(MOCK_RUN_INFO.last_run_at)

  useEffect(() => {
    if (!running) return
    const t = window.setTimeout(() => {
      setRunning(false)
      setRanAt(MOCK_RUN_INFO.last_run_at + ' (재실행)')
    }, 1800)
    return () => window.clearTimeout(t)
  }, [running])

  const counts: Array<{ label: string; value: number; bg: string; fg: string }> = [
    {
      label: '통과',
      value: MOCK_GOLD_SET.filter((r) => r.verdict === 'pass').length,
      bg: 'var(--positive-soft)',
      fg: 'var(--positive-ink)',
    },
    {
      label: '부분',
      value: MOCK_GOLD_SET.filter((r) => r.verdict === 'partial').length,
      bg: 'var(--critical-soft)',
      fg: 'var(--critical-ink)',
    },
    {
      label: '실패',
      value: MOCK_GOLD_SET.filter((r) => r.verdict === 'fail').length,
      bg: 'var(--ink-50)',
      fg: 'var(--ink-400)',
    },
  ]

  return (
    <Page width={1000}>
      <PageHeader
        mock
        eyebrow="Memory Trust Harness"
        title="신뢰도 리포트"
        lead="답변이 실제 기록에 근거하는지, 관계가 정답 그래프와 맞는지 측정합니다."
        action={
          <button
            onClick={() => setRunning(true)}
            disabled={running}
            className="btn-quiet px-[18px] py-2.5 text-[13px]"
          >
            {running ? '채점 중…' : '채점 다시 돌리기'}
          </button>
        }
      />

      {/* 숫자가 가짜라는 사실을 지표보다 먼저 읽히게 둔다 */}
      <p
        className="t-body-sm mt-8 rounded-lg px-6 py-5"
        style={{ background: 'var(--critical-soft)', color: 'var(--critical-ink)' }}
      >
        {MOCK_RUN_INFO.note} 실제 측정은 data/metadata의 정답 그래프와 질문 정답표로 채점
        스크립트를 붙여야 합니다.
      </p>

      {/*
        여기는 점수가 아니라 채점을 언제 무엇으로 돌렸는지를 밝히는 자리다. 숫자를
        크게 세우는 통계 표와 달리 라벨을 먼저 두고 값은 고정폭으로 작게 적는다.
      */}
      <div className="rule-strong mt-8 grid grid-cols-4">
        {[
          { label: '마지막 채점', value: ranAt },
          { label: '질문 수', value: MOCK_RUN_INFO.question_count + '개' },
          { label: '그래프 노드', value: MOCK_RUN_INFO.graph_nodes + '개' },
          { label: '그래프 엣지', value: MOCK_RUN_INFO.graph_edges + '개' },
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
          {MOCK_METRICS.map((metric) => (
            <div key={metric.key} className="surface p-6">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="m-0 text-[15px] font-semibold text-ink-900">{metric.label}</p>
                  <p className="t-caption m-0 mt-1.5">{metric.description}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p
                    className="m-0 text-[32px] font-bold leading-none tracking-display"
                    style={{
                      color: metric.score == null ? 'var(--ink-200)' : 'var(--ink-900)',
                    }}
                  >
                    {metric.score == null ? '—' : metric.score}
                  </p>
                  <p
                    className="t-caption m-0 mt-1"
                    style={{
                      color:
                        metric.status === 'measured'
                          ? 'var(--positive-ink)'
                          : metric.status === 'partial'
                            ? 'var(--critical-ink)'
                            : 'var(--ink-300)',
                    }}
                  >
                    {METRIC_STATUS_LABEL[metric.status]}
                  </p>
                </div>
              </div>

              {metric.score != null && (
                <div className="mt-[18px] h-0.5" style={{ background: 'var(--ink-100)' }}>
                  <div
                    className="h-0.5"
                    style={{
                      background:
                        metric.status === 'measured' ? 'var(--accent)' : 'var(--critical)',
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
              질문마다 어떤 근거가 나와야 하는지 미리 정해두고 대조합니다.
            </p>
          </div>
          <div className="flex gap-1.5">
            {counts.map((c) => (
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
            style={{
              gridTemplateColumns: GOLD_COLS,
              borderBottom: '1px solid var(--border)',
            }}
          >
            <span className="t-eyebrow text-ink-300">질문</span>
            <span className="t-eyebrow text-ink-300">기대 근거</span>
            <span className="t-eyebrow text-ink-300">실제 근거</span>
            <span className="t-eyebrow text-ink-300">판정</span>
          </div>
          {MOCK_GOLD_SET.map((row) => (
            <div
              key={row.question}
              className="grid items-start gap-4 px-1 py-3.5"
              style={{
                gridTemplateColumns: GOLD_COLS,
                borderBottom: '1px solid var(--border)',
              }}
            >
              <span className="text-sm text-ink-900">{row.question}</span>
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
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-10">
        <p className="t-eyebrow m-0">모델 비교</p>
        <p className="t-caption m-0 mt-1">
          “EXAONE이 모든 면에서 우수하다”고 말하지 않습니다. 어느 항목이 유리하고 어느 항목이
          불리한지 그대로 적습니다.
        </p>

        <div className="rule-strong mt-4">
          <div
            className="grid gap-4 px-1 py-2.5"
            style={{
              gridTemplateColumns: MODEL_COLS,
              borderBottom: '1px solid var(--border)',
            }}
          >
            <span className="t-eyebrow text-ink-300">항목</span>
            <span className="t-eyebrow text-ink-300">EXAONE</span>
            <span className="t-eyebrow text-ink-300">비교 대상 상용 LLM</span>
            <span className="t-eyebrow text-ink-300">검증 방식</span>
          </div>
          {MOCK_MODEL_CMP.map((row) => (
            <div
              key={row.item}
              className="grid items-start gap-4 px-1 py-3.5"
              style={{
                gridTemplateColumns: MODEL_COLS,
                borderBottom: '1px solid var(--border)',
              }}
            >
              <span className="text-sm text-ink-900">{row.item}</span>
              <span className="t-caption text-ink-500">{row.exaone}</span>
              <span className="t-caption text-ink-500">{row.other}</span>
              <span className="t-caption text-ink-300">{row.verification}</span>
            </div>
          ))}
        </div>
      </div>
    </Page>
  )
}
