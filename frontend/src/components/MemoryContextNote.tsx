/**
 * 이 기억에서 발견된 맥락
 *
 * 원문 아래에 붙는다. 원문을 대신하지 않는다 — 위에 사람이 말한 문장이 있고,
 * 여기 있는 것은 그 문장에서 뽑은 조각이다
 * (backend/services/memory_context.py).
 *
 * 문구는 서버가 만든 것을 그대로 쓴다. 같은 문구가 상세 화면 · Memory Film ·
 * TV 세 곳에 나오는데 화면마다 조립하면 조용히 갈라진다 — 미세 모션 라벨에서
 * 이미 한 번 겪었다 (표시와 적용이 전부 어긋나 있었다).
 *
 * 특히 "사진에서 확인된 장면인가"는 화면이 판단하지 않는다. 확인되지 않은
 * 행동을 사진 설명처럼 적으면, 가족이 기억한 것이 사진에 찍힌 것으로 읽힌다.
 *
 * 목록(기억 이어가기)과 상세가 함께 쓴다. LearnedFromAnswer와 같은 이유로 뺐다 —
 * 한쪽에만 있으면 같은 데이터가 화면마다 다르게 읽힌다.
 */

import { MemoryContextInfo } from '../lib/api'

export default function MemoryContextNote({
  context,
  detailed = false,
}: {
  context?: MemoryContextInfo | null
  /** 상세 화면에서는 연결된 사진과 Film·TV 반영 여부까지 적는다 */
  detailed?: boolean
}) {
  if (!context) return null

  const who = context.speaker?.relation || context.speaker?.name
  const bits = [
    who ? `${who}가 기억한 장면` : null,
    ...context.subjects.map((p) => p.name),
    context.scene,
    context.action,
  ].filter(Boolean) as string[]

  if (bits.length === 0) return null

  return (
    <div className="mt-3 rounded px-3.5 py-2.5" style={{ background: 'var(--paper)' }}>
      <p className="t-caption m-0">이 기억에서 발견된 맥락</p>
      <p className="t-body-sm m-0 mt-1 text-ink-700">{bits.join(' · ')}</p>

      {context.highlight && <p className="t-caption m-0 mt-1">{context.highlight}</p>}

      {/* 사진에 그 장면이 있다고 단정하지 않는다 (memory_context.source_note) */}
      {context.source_note && <p className="t-caption m-0 mt-1">{context.source_note}</p>}

      {detailed && (
        <p className="t-caption m-0 mt-1">
          {context.media_ids.length > 0
            ? `연결된 사진 ${context.media_ids.length}장`
            : '사진은 잇지 않았습니다 — 근거가 확실하지 않아 맥락만 남겼습니다'}
          {context.used_in_film && ' · Memory Film의 자막과 내레이션에 반영됩니다'}
          {context.used_in_tv && ' · TV 자막에도 쓰입니다'}
        </p>
      )}

      {context.unmatched.length > 0 && (
        <p className="t-caption m-0 mt-1 text-ink-300">
          {context.unmatched.join(' · ')} 은 아직 가족 공간에 없어 잇지 않았습니다.
        </p>
      )}

      {detailed && context.confidence === 'inferred' && (
        <p className="t-caption m-0 mt-1 text-ink-300">
          원문에 그대로 적혀 있지 않아 미루어 짚은 값입니다 (AI 추정).
        </p>
      )}
    </div>
  )
}
