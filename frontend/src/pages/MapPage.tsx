/**
 * 타임라인 · 지도 (기획안 02장 EXPANSION · TIMELINE)
 *
 * 기존 홈 타임라인은 연도순 목록뿐이고 필터도 지도도 없었다. 장소 노드에 좌표가
 * 이미 들어 있는데 쓰이지 않던 상태라, 인물·연대 필터와 이동 지도, 그리고
 * 기획안이 말한 "기록 공백 구간 제안"을 한 화면에 모았다.
 *
 * 필터는 카드 안에 가두지 않고 화면 폭을 가로지르는 띠로 깔았다. 조건이 무엇이
 * 걸려 있는지가 결과 목록보다 먼저 읽혀야 하고, 띠는 그 역할에 카드보다 조용하다.
 *
 * 사건·장소·참여자·확인 상태는 GET /api/graph/events에서 온다.
 * 남은 교체 지점: KoreaMap -> 지도 SDK 컴포넌트 (좌표 변환 규칙은 그대로 쓴다)
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { mediaUrl } from '../lib/api'
import { coverageGaps } from '../lib/coverage'
import { useEvents } from '../lib/useGraphData'
import { useCurrentUser } from '../lib/currentUser'
import KoreaMap, { MapPoint } from '../components/KoreaMap'
import { STATE_CONFIG } from '../components/StatusPill'
import { Page, PageHeader } from '../components/Page'

const DECADES = [
  { label: '1990년대', from: 1990, to: 1999 },
  { label: '2000년대', from: 2000, to: 2009 },
  { label: '2010년대', from: 2010, to: 2019 },
  { label: '2020년대', from: 2020, to: 2029 },
]

export default function MapPage() {
  const { events, loading } = useEvents()
  const { members } = useCurrentUser()
  const [personIds, setPersonIds] = useState<string[]>([])
  const [decades, setDecades] = useState<string[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    // 오래된 것부터 — 지도의 이동 경로가 연도순으로 이어져야 한다
    const ordered = [...events].sort((a, b) =>
      (a.date_start || '').localeCompare(b.date_start || ''),
    )

    return ordered.filter((event) => {
      const year = Number((event.date_start || '').slice(0, 4))
      const participantIds = event.participants.map((p) => p.id)

      const personOk =
        personIds.length === 0 || personIds.every((id) => participantIds.includes(id))

      const decadeOk =
        decades.length === 0 ||
        decades.some((label) => {
          const d = DECADES.find((x) => x.label === label)
          return d ? year >= d.from && year <= d.to : true
        })

      return personOk && decadeOk
    })
  }, [events, personIds, decades])

  const gaps = useMemo(() => coverageGaps(filtered), [filtered])

  // 좌표가 없는 사건은 지도에 점을 찍을 수 없다 (목록에는 그대로 남는다)
  const points: MapPoint[] = filtered
    .filter((e) => e.place && e.place.lat != null && e.place.lng != null)
    .map((e) => ({
      id: e.id,
      name: (e.place!.name || '').replace(/\(.*\)/, ''),
      lat: e.place!.lat as number,
      lng: e.place!.lng as number,
      count: e.media_count,
      state: e.state,
    }))

  const togglePerson = (id: string) =>
    setPersonIds((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]))

  const toggleDecade = (label: string) =>
    setDecades((prev) => (prev.includes(label) ? prev.filter((d) => d !== label) : [...prev, label]))

  const filtersActive = personIds.length > 0 || decades.length > 0

  return (
    <Page width={1160}>
      <PageHeader
        eyebrow="Timeline & Map"
        title="타임라인 · 지도"
        lead="가족의 사건을 연도와 장소로 함께 봅니다. 비어 있는 시기도 함께 보여줍니다."
      />

      <div
        className="mt-10 flex flex-wrap items-start gap-8 py-5"
        style={{
          borderTop: '1px solid var(--border)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div className="min-w-[280px]">
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">인물 · 모두 참여한 사건</p>
          <div className="flex flex-wrap gap-1.5">
            {members.map((m) => (
              <button
                key={m.id}
                onClick={() => togglePerson(m.id)}
                className={`chip ${personIds.includes(m.id) ? 'chip-on' : ''}`}
              >
                {m.name}
                <span className="ml-[5px] text-ink-300">{m.relation}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">시기</p>
          <div className="flex flex-wrap gap-1.5">
            {DECADES.map((d) => (
              <button
                key={d.label}
                onClick={() => toggleDecade(d.label)}
                className={`chip ${decades.includes(d.label) ? 'chip-on' : ''}`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        {filtersActive && (
          <button
            onClick={() => {
              setPersonIds([])
              setDecades([])
            }}
            className="btn-link ml-auto self-center"
          >
            필터 초기화
          </button>
        )}
      </div>

      <div
        className="mt-10 grid items-start gap-10"
        style={{ gridTemplateColumns: 'minmax(0,0.8fr) minmax(320px,1.2fr)' }}
      >
        <div className="sticky top-0">
          <div className="flex items-baseline justify-between">
            <p className="t-eyebrow m-0">기억이 남은 곳</p>
            <span className="t-mono text-[11px] text-ink-300">{points.length}곳</span>
          </div>
          <div className="mt-3">
            <KoreaMap points={points} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
          <p className="t-caption mt-2.5">
            점 크기는 그 장소에 남은 기록 수입니다. 점선은 연도순 이동입니다.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          {loading ? (
            <p className="t-body-sm py-12 text-center text-ink-300">불러오는 중…</p>
          ) : filtered.length === 0 ? (
            <p className="t-body-sm py-12 text-center text-ink-300">
              조건에 맞는 사건이 없습니다.
            </p>
          ) : null}

          {filtered.map((event) => {
            const config = STATE_CONFIG[event.state] ?? STATE_CONFIG.alone
            const active = selectedId === event.id

            return (
              <div
                key={event.id}
                onClick={() => setSelectedId(event.id)}
                className="cursor-pointer rounded-lg px-6 py-5 transition-colors duration-150 ease-out"
                style={{
                  background: 'var(--paper-pure)',
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                }}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="t-mono m-0 text-[11px] text-accent-ink">
                      {event.date_start || '날짜 미상'}
                    </p>
                    <p className="m-0 mt-1 text-[17px] font-semibold text-ink-900">
                      {event.title}
                    </p>
                    <p className="t-body-sm m-0 mt-[3px] text-ink-400">
                      {event.place?.name || event.location_name || '장소 미상'}
                    </p>
                  </div>
                  <span className="pill" style={{ background: config.bg, color: config.fg }}>
                    {config.label}
                  </span>
                </div>

                {event.media_thumbs.length > 0 && (
                  <div className="mt-3.5 flex min-w-0 flex-wrap gap-1.5">
                    {event.media_thumbs.map((path) => (
                      <img
                        key={path}
                        src={mediaUrl(path)}
                        alt=""
                        className="h-14 w-[76px] shrink-0 rounded bg-ink-50 object-cover"
                      />
                    ))}
                  </div>
                )}

                <div className="mt-3 flex items-center gap-3">
                  <span className="t-caption text-ink-400">
                    {event.participants.map((p) => p.name).join(' · ')}
                  </span>
                  {event.voice_count > 0 && (
                    <span className="t-caption text-accent-ink">음성 {event.voice_count}개</span>
                  )}
                </div>
              </div>
            )
          })}

          {gaps.length > 0 && (
            <div className="rule-strong mt-5 pt-5">
              <p className="t-eyebrow m-0 mb-1">비어 있는 시기</p>
              <p className="t-caption m-0 mb-4">사건 사이가 3년 이상 벌어진 구간입니다.</p>
              {gaps.map((gap) => (
                <div
                  key={gap.from_year + '-' + gap.to_year}
                  className="flex items-center gap-5 py-4"
                  style={{ borderBottom: '1px solid var(--border)' }}
                >
                  <span className="t-mono whitespace-nowrap text-sm text-ink-900">
                    {gap.from_year} — {gap.to_year}
                  </span>
                  <span className="t-caption whitespace-nowrap text-accent-ink">
                    {gap.years}년
                  </span>
                  <span className="t-body-sm flex-1 text-ink-400">{gap.suggestion}</span>
                  <Link to="/interview" className="btn-outline no-underline hover:no-underline">
                    인터뷰로 채우기
                  </Link>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}
