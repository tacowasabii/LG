/**
 * 답변의 근거를 사진으로 보여주는 알약 (기획안 "답변과 함께 실제 사진·음성 재생")
 *
 * 아이콘 + 제목만 있는 뱃지는 "무엇을 보고 답했는지"가 눈에 들어오지 않는다.
 * 그래서 근거의 원본 이미지를 알약의 왼쪽 눈으로 쓴다. 종류·제목·근거 강도를
 * 한 줄에 담아 답변 아래로 여러 개가 흘러도 답변보다 무거워지지 않게 한다.
 *
 * 썸네일은 백엔드가 내려주는 source.thumbnail을 쓴다. 추억 근거에는 그 추억의
 * 사진 한 장이 얼굴로 붙어 온다 (chat_engine._event_thumbnail).
 */

import { useState } from 'react'
import { ChatSource, mediaUrl } from '../lib/api'

const TYPE_LABEL: Record<string, string> = {
  media: '기록',
  event: '추억',
  memory: '기억',
  person: '인물',
  place: '장소',
  audio: '음성',
}

interface Props {
  source: ChatSource
  onSelect?: (source: ChatSource) => void
  active?: boolean
}

export default function EvidenceCard({ source, onSelect, active = false }: Props) {
  // 파일이 없으면 빈 원으로 되돌린다 (백엔드 없이 화면만 볼 때도 깨지지 않게)
  const [broken, setBroken] = useState(false)
  const thumbPath = source.thumbnail || null
  const thumb = thumbPath && !broken ? mediaUrl(thumbPath) : null
  const typeLabel = TYPE_LABEL[source.type] || source.type

  return (
    <button
      onClick={() => onSelect?.(source)}
      className="hover-border-accent flex cursor-pointer items-center gap-2.5 rounded-full
                 py-1.5 pl-1.5 pr-3 transition-colors duration-150 ease-out"
      style={{
        background: 'var(--paper-pure)',
        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
      }}
    >
      {thumb ? (
        <img
          src={thumb}
          alt=""
          className="h-[26px] w-[26px] shrink-0 rounded-full bg-ink-50 object-cover"
          onError={() => setBroken(true)}
        />
      ) : (
        <span
          className="t-mono flex h-[26px] w-[26px] shrink-0 items-center justify-center
                     rounded-full bg-ink-50 text-[10px] text-ink-300"
        >
          {typeLabel.slice(0, 1)}
        </span>
      )}

      <span className="max-w-[220px] truncate text-xs text-ink-500">
        {typeLabel} · {source.title || source.id}
      </span>

      {source.confidence != null && (
        <span className="t-mono shrink-0 text-[10px] text-ink-300">
          {Math.round(source.confidence * 100)}%
        </span>
      )}
    </button>
  )
}
