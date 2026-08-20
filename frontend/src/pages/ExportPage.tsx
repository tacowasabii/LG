/**
 * 가족 아카이브 내보내기 (기획안 02장 EXPANSION · LEGACY)
 *
 * "플랫폼에 종속되지 않는다"는 약속을 화면으로 보여주는 자리다.
 * 원본·그래프·이야기를 통째로 받아갈 수 있어야 가족이 장기 자산으로 신뢰한다.
 *
 * 항목마다 아이콘을 달지 않는다. 네 줄짜리 목록에서 아이콘은 체크 표시와
 * 경쟁만 하고, 여기서 눌러야 하는 것은 체크 하나다.
 *
 * 용량은 서버가 디스크에서 잰 실제 값이고, zip도 실제로 만들어진다. 가짜
 * 진행률을 돌리지 않는다 — 만드는 동안 "만들고 있습니다"만 정직하게 띄운다.
 */

import { useEffect, useState } from 'react'
import {
  ExportManifest,
  ExportResult,
  buildArchive,
  exportDownloadUrl,
  getExportManifest,
} from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { Page, PageHeader } from '../components/Page'

type Phase = 'idle' | 'running' | 'done'

function sizeLabel(bytes: number | null): string {
  if (bytes == null) return '만들 때 결정'
  if (bytes < 1024) return bytes + 'B'
  const mb = bytes / 1048576
  if (mb < 1) return Math.round(bytes / 1024) + 'KB'
  if (mb >= 1024) return (mb / 1024).toFixed(2) + 'GB'
  return mb.toFixed(1) + 'MB'
}

export default function ExportPage() {
  const { current } = useCurrentUser()
  const [manifest, setManifest] = useState<ExportManifest | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [phase, setPhase] = useState<Phase>('idle')
  const [result, setResult] = useState<ExportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getExportManifest()
      .then((data) => {
        setManifest(data)
        // 담을 것이 있는 항목만 기본 선택 (빈 항목을 체크해 두면 거짓말이 된다)
        setSelected(data.items.filter((i) => i.required || i.count > 0).map((i) => i.id))
      })
      .catch((e) => {
        console.error(e)
        setError('내보낼 목록을 불러오지 못했습니다.')
      })
  }, [current?.id])

  const toggle = (id: string, required: boolean) => {
    if (required) return
    setSelected((prev) => (prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]))
  }

  const build = async () => {
    setPhase('running')
    setError(null)
    try {
      setResult(await buildArchive(selected))
      setPhase('done')
    } catch (e) {
      console.error(e)
      setError('아카이브를 만들지 못했습니다.')
      setPhase('idle')
    }
  }

  if (!manifest) {
    return (
      <Page width={820}>
        <p className="t-caption">{error || '불러오는 중…'}</p>
      </Page>
    )
  }

  const chosen = manifest.items.filter((i) => selected.includes(i.id))
  const knownTotal = chosen.reduce((sum, i) => sum + (i.size_bytes ?? 0), 0)

  return (
    <Page width={820}>
      <PageHeader
        eyebrow="Export"
        title="기록은 가족의 것입니다"
        lead="언제든 통째로 받아갈 수 있습니다. 그래프는 표준 JSON이고 연대기는 브라우저로 열립니다."
      />

      <div className="mt-10 flex flex-col gap-2">
        {manifest.items.map((item) => {
          const on = selected.includes(item.id)
          const empty = item.count === 0 && !item.required

          return (
            <button
              key={item.id}
              onClick={() => toggle(item.id, item.required)}
              disabled={empty}
              className={
                'flex w-full items-center gap-4 rounded-lg px-5 py-[18px] text-left ' +
                (item.required || empty ? 'cursor-default' : 'cursor-pointer')
              }
              style={{
                background: 'var(--paper-pure)',
                border: '1px solid ' + (on ? 'var(--accent)' : 'var(--border)'),
                opacity: empty ? 0.55 : 1,
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
                {sizeLabel(item.size_bytes)}
              </span>
            </button>
          )
        })}
      </div>

      <div
        className="mt-6 flex flex-wrap items-center justify-between gap-5 pt-5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <p className="t-body-sm m-0">
          합계 {sizeLabel(knownTotal)} · 항목 {chosen.length}개
        </p>

        {phase === 'idle' && (
          <button onClick={build} className="btn-primary px-[22px]">
            아카이브 만들기
          </button>
        )}

        {phase === 'running' && (
          <span className="t-mono text-xs text-ink-400">만들고 있습니다…</span>
        )}
      </div>

      {/* 열람 범위 밖의 기록은 담기지 않는다는 사실을 숫자로 밝힌다 */}
      <p className="t-caption mt-3">
        {manifest.note}
        {manifest.hidden_media > 0 && ' (' + manifest.hidden_media + '개 제외)'}
      </p>

      {error && (
        <p className="t-body-sm mt-4" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {phase === 'done' && result && (
        <div
          className="mt-5 flex flex-wrap items-center gap-5 rounded-lg p-6"
          style={{ background: 'var(--positive-soft)' }}
        >
          <span className="min-w-0 flex-1">
            <span
              className="block text-[15px] font-semibold"
              style={{ color: 'var(--positive-ink)' }}
            >
              아카이브가 준비됐습니다
            </span>
            <span className="t-caption mt-1 block" style={{ color: 'var(--positive-ink)' }}>
              {result.file_name} · {sizeLabel(result.size_bytes)} ·{' '}
              {result.built_at.replace('T', ' ')}
            </span>
          </span>

          <a
            href={exportDownloadUrl(result)}
            download={result.file_name}
            className="shrink-0 cursor-pointer rounded border-0 px-5 py-2.5 text-[13px]
                       font-semibold no-underline hover:no-underline"
            style={{ background: 'var(--positive)', color: 'var(--paper)' }}
          >
            받기 ↓
          </a>

          <button
            onClick={() => {
              setPhase('idle')
              setResult(null)
            }}
            className="btn-link"
            style={{ color: 'var(--positive-ink)' }}
          >
            처음으로
          </button>
        </div>
      )}

      <div className="mt-10">
        <p className="t-eyebrow m-0 mb-2.5">아카이브에 들어 있는 것</p>
        <p className="t-body m-0 max-w-[48em]">
          원본 사진·영상은 보정 없이 그대로, 그래프는 표준 JSON, 가족이 남긴 문장은
          memories.md로 들어갑니다. 연대기는 chronicle.html이며 사진을 상대 경로로 가리키므로
          zip을 풀고 브라우저로 열면 그대로 보입니다. 이 서비스 없이도 열립니다.
        </p>
      </div>

      <p className="t-body-sm mt-8 rounded-lg bg-ink-50 px-6 py-5">
        비공개로 설정한 기록은 소유자가 직접 내보낼 때만 포함됩니다. 다른 구성원의 아카이브에는
        들어가지 않습니다.
      </p>
    </Page>
  )
}
