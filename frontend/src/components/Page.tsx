/**
 * 화면 골격 — 모든 화면이 같은 방식으로 열린다.
 *
 * 디자인 체계는 화면마다 "대문자 라벨 → 제목 → 한 줄 설명"으로 시작하고,
 * 본문 폭만 화면의 성격에 따라 달라진다. 읽는 화면은 좁게(760~900px), 표와
 * 지도를 나란히 놓는 화면은 넓게(1040~1160px) 잡는다. 열여섯 화면에 같은
 * 마크업을 반복하는 대신 여기 모아 두고 폭만 인자로 받는다.
 */

import { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface PageProps {
  /** 본문 최대 폭(px). 화면 성격에 맞춰 디자인이 정한 값을 그대로 넣는다 */
  width: number
  children: ReactNode
}

export function Page({ width, children }: PageProps) {
  return (
    <div className="page" style={{ maxWidth: width }}>
      {children}
    </div>
  )
}

interface PageHeaderProps {
  /** 화면 종류를 알려주는 영문 라벨 */
  eyebrow: string
  title: string
  /** 이 화면이 무엇을 하는지 한두 문장. 없는 화면(그래프)도 있다 */
  lead?: ReactNode
  /** 제목 오른쪽 끝에 놓을 동작 (신뢰도 리포트의 "다시 채점" 등) */
  action?: ReactNode
  /** 홈만 한 단계 큰 제목을 쓴다 */
  large?: boolean
}

export function PageHeader({
  eyebrow,
  title,
  lead,
  action,
  large = false,
}: PageHeaderProps) {
  const head = (
    <div>
      <p className="t-eyebrow m-0 mb-3">{eyebrow}</p>
      <h2 className={large ? 't-display m-0' : 't-title m-0'}>{title}</h2>
      {lead && <p className="t-lead mt-3 max-w-[52ch]">{lead}</p>}
    </div>
  )

  if (!action) return head

  return (
    <div className="flex flex-wrap items-end justify-between gap-8">
      {head}
      {action}
    </div>
  )
}

interface SectionHeadProps {
  title: string
  /** "그래프로 보기 →" 처럼 다른 화면으로 넘기는 고리 */
  to?: string
  linkLabel?: string
  /** 굵은 규칙선 — 표나 목록이 바로 이어질 때 쓴다 */
  strong?: boolean
  /** 제목 바로 옆에 붙는 각주 (목데이터 뱃지 등) */
  children?: ReactNode
}

export function SectionHead({
  title,
  to,
  linkLabel,
  strong = false,
  children,
}: SectionHeadProps) {
  return (
    <div
      className="flex items-baseline justify-between gap-4 pb-3"
      style={{
        borderBottom: strong ? '2px solid var(--ink-700)' : '1px solid var(--border)',
      }}
    >
      {/* 각주는 제목에 딸린 것이므로 한 묶음으로 둔다 — 떼어 놓으면 링크 쪽으로 밀린다 */}
      <span className="flex items-baseline gap-2.5">
        <h3 className="t-h3 m-0">{title}</h3>
        {children}
      </span>
      {to && linkLabel && (
        <Link to={to} className="shrink-0 text-[13px]">
          {linkLabel} →
        </Link>
      )}
    </div>
  )
}

export interface StatCell {
  value: ReactNode
  label: string
  /** 강조할 값 하나만 강조색을 쓴다 (예: 채워야 할 기억) */
  accent?: boolean
}

/**
 * 굵은 규칙선 아래 숫자를 나란히 세우는 표. 카드 대신 규칙선과 여백만으로
 * 묶는 것이 이 디자인 체계의 방식이다 — 숫자 자체가 이미 충분히 크다.
 */
export function StatRow({ cells, size = 40 }: { cells: StatCell[]; size?: number }) {
  return (
    <div
      className="rule-strong grid"
      style={{ gridTemplateColumns: `repeat(${cells.length}, 1fr)` }}
    >
      {cells.map((cell, i) => (
        <div
          key={cell.label}
          className="pt-5 pr-6"
          style={
            i === 0
              ? undefined
              : { paddingLeft: 28, borderLeft: '1px solid var(--border)' }
          }
        >
          <p
            className="m-0 font-bold leading-none tracking-display"
            style={{
              fontSize: size,
              color: cell.accent ? 'var(--accent-ink)' : 'var(--ink-900)',
            }}
          >
            {cell.value}
          </p>
          <p className="t-caption mb-5 mt-2">{cell.label}</p>
        </div>
      ))}
    </div>
  )
}
