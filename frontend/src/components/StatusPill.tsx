/**
 * 기억이 쌓인 정도 표시 (alone / shared / varied)
 *
 * 예전에는 확인 상태 4단계(확인 완료 · 다중 근거 · 확인 필요 · 기억 충돌)였다.
 * 그 표기를 버린 이유는 화면이 아니라 제품의 전제가 바뀌었기 때문이다 — 추억은
 * 한 사람이 만들면 그 자리에서 게시되고, 확인을 기다리는 상태가 없다.
 *
 * 그래서 남은 것은 "이 기억에 가족이 얼마나 함께 있는가" 하나다.
 *
 *   한 사람의 기억   아직 만든 사람 혼자 기억한다 (결함이 아니다)
 *   함께 기억        다른 가족이 기억을 더했다
 *   다르게 기억      조금 다르게 기억하는 내용이 함께 있다
 *
 * '다르게 기억'은 경고가 아니다. 해결해야 할 충돌로 읽히면 안 되므로 낱말에서
 * '충돌'과 '필요'를 뺐다. 색은 그대로 번트 오렌지를 쓰지만(붉은 계열은 브랜드
 * 강조색이 독점한다) 문장이 "그대로 보존됩니다"라고 말한다.
 *
 * dot은 알약 없이 점만 찍는 자리(범례, 상태 막대)에 쓴다.
 */

import type { MemoryState } from '../lib/api'

export const STATE_CONFIG: Record<
  MemoryState,
  { label: string; hint: string; bg: string; fg: string; dot: string }
> = {
  shared: {
    label: '함께 기억',
    hint: '가족이 기억을 더했습니다.',
    bg: 'var(--positive-soft)',
    fg: 'var(--positive-ink)',
    dot: 'var(--positive)',
  },
  alone: {
    label: '한 사람의 기억',
    hint: '만든 사람의 기억만 있습니다. 기억나는 것이 있으면 더할 수 있어요.',
    bg: 'var(--ink-50)',
    fg: 'var(--ink-400)',
    dot: 'var(--ink-200)',
  },
  varied: {
    label: '다르게 기억',
    hint: '가족들이 조금 다르게 기억하고 있어요. 모두 그대로 보존됩니다.',
    bg: 'var(--critical-soft)',
    fg: 'var(--critical-ink)',
    dot: 'var(--critical)',
  },
}

/** 상태를 훑을 때 쓰는 고정 순서 (함께 기억한 것부터) */
export const STATE_ORDER: MemoryState[] = ['shared', 'alone', 'varied']

interface Props {
  state: MemoryState
  /** md는 TV 10-foot 크기 — 3m 거리에서 읽히도록 vw로 커진다 */
  size?: 'sm' | 'md'
}

export default function StatusPill({ state, size = 'sm' }: Props) {
  const config = STATE_CONFIG[state] ?? STATE_CONFIG.alone

  return (
    <span
      className={
        size === 'md'
          ? 'tv-caption font-semibold rounded-full whitespace-nowrap px-[0.9vw] py-[0.3vh]'
          : 'pill'
      }
      style={{ background: config.bg, color: config.fg }}
      title={config.hint}
    >
      {config.label}
    </span>
  )
}
