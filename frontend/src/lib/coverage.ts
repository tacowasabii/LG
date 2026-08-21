/**
 * 기록 공백 구간 (기획안 02장 "기록 공백 구간 제안")
 *
 * 추억 사이가 오래 벌어진 구간은 "기록이 없는 시기"다. 사진이 없는 시절을
 * 화면에 드러내는 것이 이 제품에서 중요한데, 빈 구간을 보여주지 않으면
 * 가족은 이미 다 정리됐다고 착각한다.
 *
 * 서버에서 계산할 수도 있지만, 필터가 걸린 목록에 대해서도 즉시 다시 계산해야
 * 하므로 화면 쪽에 둔다.
 */

import { EventListItem } from './api'

/** 이 정도 벌어지면 공백으로 본다 */
const GAP_YEARS = 3

export interface CoverageGap {
  from_year: number
  to_year: number
  years: number
  suggestion: string
}

export function coverageGaps(events: EventListItem[]): CoverageGap[] {
  const dated = events.filter((e) => !!e.date_start)
  const sorted = [...dated].sort((a, b) => (a.date_start || '').localeCompare(b.date_start || ''))
  const gaps: CoverageGap[] = []

  for (let i = 1; i < sorted.length; i++) {
    const from = Number((sorted[i - 1].date_start || '').slice(0, 4))
    const to = Number((sorted[i].date_start || '').slice(0, 4))
    if (!from || !to) continue

    const years = to - from
    if (years >= GAP_YEARS) {
      gaps.push({
        from_year: from,
        to_year: to,
        years,
        suggestion:
          from +
          '년과 ' +
          to +
          '년 사이 ' +
          years +
          '년의 기록이 없습니다. 이 시기 사진이나 이야기가 있나요?',
      })
    }
  }

  return gaps
}
