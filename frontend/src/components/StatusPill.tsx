/**
 * 신뢰도 4단계 표시 (기획안 03장 CONFIRMED / SUPPORTED / INFERRED / CONFLICTED)
 *
 * 확인 요청 화면, 그래프 상세, 채팅 답변, 지도·타임라인이 같은 색과 같은 낱말을
 * 쓰도록 한 곳에 모았다. 상태 표기가 화면마다 다르면 "무엇이 사실인지"라는
 * 제품의 핵심 메시지가 흐려진다.
 *
 * 디자인 체계상 붉은 계열은 브랜드 강조색이 독점하므로 상태에는 쓰지 않는다.
 * 확인 완료는 teal, 기억 충돌은 번트 오렌지, 나머지는 잉크 계조로만 구분한다.
 * 아이콘을 붙이지 않는 것도 같은 이유다 — 색과 낱말만으로 충분하고, 알약이
 * 여러 개 늘어설 때 아이콘은 읽는 속도만 떨어뜨린다.
 *
 * dot은 알약 없이 점만 찍는 자리(범례, 상태 막대)에 쓴다.
 */

import type { VerificationState } from '../lib/api'

export const STATE_CONFIG: Record<
  VerificationState,
  { label: string; hint: string; bg: string; fg: string; dot: string }
> = {
  confirmed: {
    label: '확인 완료',
    hint: '가족이 확인했습니다.',
    bg: 'var(--positive-soft)',
    fg: 'var(--positive-ink)',
    dot: 'var(--positive)',
  },
  supported: {
    label: '다중 근거',
    hint: '두 사람 이상의 기억이 있습니다.',
    bg: 'var(--ink-50)',
    fg: 'var(--ink-700)',
    dot: 'var(--ink-700)',
  },
  inferred: {
    label: '확인 필요',
    hint: '아직 아무도 확인하지 않았습니다.',
    bg: 'var(--ink-50)',
    fg: 'var(--ink-400)',
    dot: 'var(--ink-200)',
  },
  conflicted: {
    label: '기억 충돌',
    hint: '기억이 서로 다릅니다. 양쪽 모두 보존됩니다.',
    bg: 'var(--critical-soft)',
    fg: 'var(--critical-ink)',
    dot: 'var(--critical)',
  },
}

/** 상태를 색 순서대로 훑을 때 쓰는 고정 순서 (확인된 것부터) */
export const STATE_ORDER: VerificationState[] = [
  'confirmed',
  'supported',
  'inferred',
  'conflicted',
]

interface Props {
  state: VerificationState
  /** md는 TV 10-foot 크기 — 3m 거리에서 읽히도록 vw로 커진다 */
  size?: 'sm' | 'md'
}

export default function StatusPill({ state, size = 'sm' }: Props) {
  const config = STATE_CONFIG[state]

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
