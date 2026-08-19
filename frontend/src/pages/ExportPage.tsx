/**
 * 가족 아카이브 내보내기 (기획안 02장 EXPANSION · LEGACY)
 *
 * "플랫폼에 종속되지 않는다"는 약속을 화면으로 보여주는 자리다.
 * 원본·그래프·이야기를 통째로 받아갈 수 있어야 가족이 장기 자산으로 신뢰한다.
 *
 * 항목마다 아이콘을 달지 않는다. 다섯 줄짜리 목록에서 아이콘은 체크 표시와
 * 경쟁만 하고, 여기서 눌러야 하는 것은 체크 하나다.
 *
 * 실기능 개발 시 교체 지점:
 *   항목 용량      -> GET  /api/export/manifest
 *   내보내기 실행  -> POST /api/export  (작업 큐 + 진행률 폴링)
 *   다운로드 링크  -> 서명된 임시 URL
 */

import { useEffect, useState } from 'react'
import { Page, PageHeader } from '../components/Page'

interface ExportItem {
  id: string
  label: string
  detail: string
  size_mb: number
  /** 끌 수 없는 항목 — 원본과 그래프는 아카이브의 뼈대다 */
  required?: boolean
}

const ITEMS: ExportItem[] = [
  {
    id: 'media',
    label: '원본 사진 · 영상',
    detail: '사진 24장, 영상 4개 · 보정 없는 원본',
    size_mb: 412,
    required: true,
  },
  {
    id: 'graph',
    label: 'Memory Graph',
    detail: '노드 59개, 엣지 204개 · JSON',
    size_mb: 1,
    required: true,
  },
  {
    id: 'voice',
    label: '음성과 전사문',
    detail: '인터뷰 음성 4개 · 텍스트 포함',
    size_mb: 18,
  },
  {
    id: 'chronicle',
    label: '가족 연대기 PDF',
    detail: '1998–2024 · 사건 8개 · 사진과 기억 문장 포함',
    size_mb: 26,
  },
  {
    id: 'film',
    label: 'Memory Film 영상',
    detail: '만들어 둔 30–60초 영상 3편',
    size_mb: 154,
  },
]

type Phase = 'idle' | 'running' | 'done'

function sizeLabel(mb: number): string {
  return mb >= 1000 ? (mb / 1024).toFixed(1) + 'GB' : mb + 'MB'
}

export default function ExportPage() {
  const [selected, setSelected] = useState<string[]>(ITEMS.map((i) => i.id))
  const [phase, setPhase] = useState<Phase>('idle')
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    if (phase !== 'running') return

    const timer = window.setInterval(() => {
      setProgress((prev) => {
        const next = prev + 5
        if (next >= 100) {
          setPhase('done')
          return 100
        }
        return next
      })
    }, 110)

    return () => window.clearInterval(timer)
  }, [phase])

  const toggle = (item: ExportItem) => {
    if (item.required) return
    setSelected((prev) =>
      prev.includes(item.id) ? prev.filter((i) => i !== item.id) : [...prev, item.id],
    )
  }

  const totalMb = ITEMS.filter((i) => selected.includes(i.id)).reduce(
    (sum, i) => sum + i.size_mb,
    0,
  )
  const totalGb = (totalMb / 1024).toFixed(2)

  return (
    <Page width={820}>
      <PageHeader
        mock
        eyebrow="Export"
        title="기록은 가족의 것입니다"
        lead="언제든 통째로 받아갈 수 있습니다. 그래프는 표준 JSON이라 다른 도구에서도 열립니다."
      />

      <div className="mt-10 flex flex-col gap-2">
        {ITEMS.map((item) => {
          const on = selected.includes(item.id)

          return (
            <button
              key={item.id}
              onClick={() => toggle(item)}
              className={`flex w-full items-center gap-4 rounded-lg px-5 py-[18px] text-left
                          ${item.required ? 'cursor-default' : 'cursor-pointer'}`}
              style={{
                background: 'var(--paper-pure)',
                border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`,
              }}
            >
              <span
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm text-[11px]"
                style={
                  on
                    ? {
                        background: 'var(--accent)',
                        color: 'var(--accent-fg)',
                        border: '1px solid var(--accent)',
                      }
                    : { border: '1px solid var(--border-strong)' }
                }
              >
                {on ? '✓' : ''}
              </span>

              <span className="min-w-0 flex-1">
                <span className="block text-[15px] text-ink-900">
                  {item.label}
                  {item.required && (
                    <span className="t-caption ml-2.5 text-ink-300">항상 포함</span>
                  )}
                </span>
                <span className="t-caption mt-[3px] block">{item.detail}</span>
              </span>

              <span className="t-mono shrink-0 text-xs text-ink-300">
                {sizeLabel(item.size_mb)}
              </span>
            </button>
          )
        })}
      </div>

      <div
        className="mt-6 flex items-center justify-between gap-5 pt-5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <p className="t-body-sm m-0">
          합계 약 {totalGb}GB · 항목 {selected.length}개
        </p>

        {phase === 'idle' && (
          <button
            onClick={() => {
              setProgress(0)
              setPhase('running')
            }}
            className="btn-primary px-[22px]"
          >
            아카이브 만들기
          </button>
        )}

        {phase === 'running' && (
          <span className="t-mono text-xs text-ink-400">준비 중 {progress}%</span>
        )}
      </div>

      {phase === 'running' && (
        <div className="mt-4 h-0.5" style={{ background: 'var(--ink-100)' }}>
          <div
            className="h-0.5 transition-all duration-150"
            style={{ background: 'var(--accent)', width: progress + '%' }}
          />
        </div>
      )}

      {phase === 'done' && (
        <div
          className="mt-5 flex items-center gap-5 rounded-lg p-6"
          style={{ background: 'var(--positive-soft)' }}
        >
          <span className="min-w-0 flex-1">
            <span
              className="block text-[15px] font-semibold"
              style={{ color: 'var(--positive-ink)' }}
            >
              아카이브가 준비됐습니다
            </span>
            <span
              className="t-caption mt-1 block"
              style={{ color: 'var(--positive-ink)' }}
            >
              homestory-archive-2026-08-19.zip · 약 {totalGb}GB · 링크는 48시간 뒤 만료됩니다
            </span>
          </span>
          <button
            className="shrink-0 cursor-pointer rounded border-0 px-5 py-2.5 text-[13px] font-semibold"
            style={{ background: 'var(--positive)', color: 'var(--paper)' }}
          >
            받기 ↓
          </button>
          <button
            onClick={() => {
              setPhase('idle')
              setProgress(0)
            }}
            className="btn-link"
            style={{ color: 'var(--positive-ink)' }}
          >
            처음으로
          </button>
        </div>
      )}

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-2.5">계정 이전과 상속</p>
        <p className="t-body m-0 max-w-[64ch]">
          가족 관리자는 다른 구성원에게 관리 권한을 넘길 수 있습니다. 서비스를 그만 쓰더라도
          아카이브 파일 하나로 원본과 관계, 이야기가 모두 남습니다.
        </p>
      </div>

      <p className="t-body-sm mt-8 rounded-lg bg-ink-50 px-6 py-5">
        비공개로 설정한 기록은 소유자가 직접 내보낼 때만 포함됩니다. 다른 구성원의 아카이브에는
        들어가지 않습니다.
      </p>
    </Page>
  )
}
