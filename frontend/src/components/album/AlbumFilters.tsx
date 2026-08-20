/**
 * 사진첩 필터 띠
 *
 * 타임라인·지도와 같은 방식으로, 카드에 가두지 않고 화면 폭을 가로지르는 띠로
 * 깐다. 지금 무엇이 걸려 있는지가 사진보다 먼저 읽혀야 한다.
 *
 * 여기서 고른 값은 화면 상태가 아니라 주소(URL)에 있다. 사진 하나를 찾아
 * 가족에게 보낼 때 링크만 보내면 같은 화면이 열려야 하고, 뒤로 가기로 직전
 * 조건으로 되돌아갈 수 있어야 한다 (AlbumPage가 useSearchParams로 쓴다).
 *
 * 연도 목록은 서버가 준다 (available_years). 화면이 지금 받은 사진에서 뽑으면
 * 첫 페이지에 없는 연도가 목록에서 빠진다.
 */

import { Search } from 'lucide-react'
import { AlbumEventStatus, AlbumSort, FamilyMember } from '../../lib/api'

export interface AlbumFilterValue {
  /** all | photo | video */
  type: string
  year: number | null
  personId: string | null
  eventStatus: AlbumEventStatus
  sort: AlbumSort
  /** 입력 중인 글자. 주소에 반영되기까지 잠깐 기다린다 (AlbumPage) */
  q: string
}

const TYPES: Array<{ value: string; label: string }> = [
  { value: 'all', label: '전체' },
  { value: 'photo', label: '사진' },
  { value: 'video', label: '영상' },
]

const EVENT_STATUSES: Array<{ value: AlbumEventStatus; label: string }> = [
  { value: 'all', label: '전체 기록' },
  { value: 'linked', label: '추억에 연결됨' },
  { value: 'unlinked', label: '미분류' },
]

const SORTS: Array<{ value: AlbumSort; label: string }> = [
  { value: 'captured_desc', label: '촬영일 최신순' },
  { value: 'captured_asc', label: '촬영일 오래된순' },
  { value: 'uploaded_desc', label: '최근 업로드순' },
]

interface AlbumFiltersProps {
  value: AlbumFilterValue
  years: number[]
  members: FamilyMember[]
  /** 입력 중인 검색어 (주소에 아직 반영되지 않은 값) */
  draftQuery: string
  onDraftQuery: (q: string) => void
  onChange: (patch: Partial<AlbumFilterValue>) => void
  onReset: () => void
  active: boolean
}

export default function AlbumFilters({
  value,
  years,
  members,
  draftQuery,
  onDraftQuery,
  onChange,
  onReset,
  active,
}: AlbumFiltersProps) {
  return (
    <div
      className="mt-8 flex flex-col gap-4 py-5"
      style={{
        borderTop: '1px solid var(--border)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <label className="relative flex min-w-[240px] flex-1 items-center">
          <Search
            size={15}
            strokeWidth={1.75}
            className="pointer-events-none absolute left-3 text-ink-300"
          />
          <input
            value={draftQuery}
            onChange={(e) => onDraftQuery(e.target.value)}
            placeholder="파일명 · 추억 · 인물 · 장소로 찾기"
            className="field field-sm pl-9"
            aria-label="사진 검색"
          />
        </label>

        <div className="flex gap-1.5" role="group" aria-label="미디어 유형">
          {TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => onChange({ type: t.value })}
              className={`tab tab-sm ${value.type === t.value ? 'tab-on' : ''}`}
              aria-pressed={value.type === t.value}
            >
              {t.label}
            </button>
          ))}
        </div>

        <select
          value={value.sort}
          onChange={(e) => onChange({ sort: e.target.value as AlbumSort })}
          className="field field-inline ml-auto"
          aria-label="정렬"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <div className="min-w-[260px]">
          <p className="t-eyebrow m-0 mb-2 text-[10px] text-ink-300">인물 · 사진에 지목된 사람</p>
          <div className="flex flex-wrap gap-1.5">
            {members.map((m) => (
              <button
                key={m.id}
                onClick={() =>
                  onChange({ personId: value.personId === m.id ? null : m.id })
                }
                className={`chip ${value.personId === m.id ? 'chip-on' : ''}`}
                aria-pressed={value.personId === m.id}
              >
                {m.name}
                <span className="ml-[5px] text-ink-300">{m.relation}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="t-eyebrow m-0 mb-2 text-[10px] text-ink-300">촬영 연도</p>
          <div className="flex flex-wrap gap-1.5">
            {years.length === 0 ? (
              <span className="t-caption">촬영일이 있는 사진이 없습니다</span>
            ) : (
              years.map((year) => (
                <button
                  key={year}
                  onClick={() => onChange({ year: value.year === year ? null : year })}
                  className={`chip ${value.year === year ? 'chip-on' : ''}`}
                  aria-pressed={value.year === year}
                >
                  {year}
                </button>
              ))
            )}
          </div>
        </div>

        <div>
          <p className="t-eyebrow m-0 mb-2 text-[10px] text-ink-300">추억 연결</p>
          <div className="flex flex-wrap gap-1.5">
            {EVENT_STATUSES.map((s) => (
              <button
                key={s.value}
                onClick={() => onChange({ eventStatus: s.value })}
                className={`chip ${value.eventStatus === s.value ? 'chip-on' : ''}`}
                aria-pressed={value.eventStatus === s.value}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {active && (
          <button onClick={onReset} className="btn-link ml-auto self-end pb-1.5">
            필터 초기화
          </button>
        )}
      </div>
    </div>
  )
}
