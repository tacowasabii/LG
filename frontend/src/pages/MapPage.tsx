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
 * 지도의 점과 목록의 카드는 두 걸음으로 나눠 둔다. 점을 누르면 오른쪽 목록에서
 * 그 사건의 카드를 찾아 눈에 보이는 자리로 옮기고 표시만 한다. 상세를 여는 것은
 * 카드를 누를 때다 — 지도는 훑는 곳이라, 점을 스칠 때마다 화면 전체를 덮는 것이
 * 뜨면 다른 점을 보러 가는 길이 매번 막힌다.
 *
 * 카드를 누르면 EventSpotlight가 그 사건의 사진을 Memory Film처럼 크게 띄우고
 * 그날에 남은 기록을 함께 보여준다. 카드의 썸네일 세 장은 미리보기일 뿐이다.
 *
 * 사건·장소·참여자·확인 상태는 GET /api/graph/events에서 온다.
 * 남은 교체 지점: KoreaMap -> 지도 SDK 컴포넌트 (좌표 변환 규칙은 그대로 쓴다)
 */

import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { mediaUrl } from '../lib/api'
import { coverageGaps } from '../lib/coverage'
import { useEvents } from '../lib/useGraphData'
import { useCurrentUser } from '../lib/currentUser'
import KoreaMap, { MapPoint, isInBounds } from '../components/KoreaMap'
import { STATE_CONFIG } from '../components/StatusPill'
import { Page, PageHeader } from '../components/Page'
import EventSpotlight from '../components/EventSpotlight'

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
  /*
    크게 열어 둔 사건. 예전에는 사건을 눌러도 테두리 색만 바뀌었다 — 카드의
    썸네일 세 장이 그 사건에 남은 사진 전부인 것처럼 읽혔고, 누른 사람이
    기대한 "이 사건 보기"가 아무 데도 닿지 않았다.
  */
  const [openId, setOpenId] = useState<string | null>(null)

  /* 목록의 카드들. 지도에서 고른 사건을 화면 안으로 데려오는 데만 쓴다 */
  const cardRefs = useRef<Record<string, HTMLButtonElement | null>>({})

  /**
   * 지도의 점을 눌렀을 때 — 오른쪽 목록에서 그 사건을 찾아 준다.
   *
   * 상세를 바로 열지 않는다. 점 하나를 누른 것은 "이게 뭐지"에 가깝고, 여는 것은
   * 카드를 보고 나서 정할 일이다. 표시만 하고 두면 목록 아래쪽 카드는 화면 밖에
   * 있어서 누른 것이 아무 데도 닿지 않은 것처럼 보이므로, 화면 가운데로 옮긴다.
   */
  const focusEvent = (id: string) => {
    setSelectedId(id)
    const card = cardRefs.current[id]
    if (!card) return
    // 움직임을 줄이도록 설정한 사용자에게는 스르륵 넘기지 않고 바로 옮긴다
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    card.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' })
  }

  // 카드를 누르면 그 사건을 크게 본다
  const openEvent = (id: string) => {
    setSelectedId(id)
    setOpenId(id)
  }

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
  const located: MapPoint[] = filtered
    .filter((e) => e.place && e.place.lat != null && e.place.lng != null)
    .map((e) => ({
      id: e.id,
      name: (e.place!.name || '').replace(/\(.*\)/, ''),
      lat: e.place!.lat as number,
      lng: e.place!.lng as number,
      count: e.media_count,
      state: e.state,
    }))

  // 이 지도는 남한만 그린다. 그 밖의 좌표(해외 여행)는 점을 찍을 자리가 없다.
  // 조용히 빼면 "그 기억이 없는 것"으로 읽히므로 어디가 빠졌는지 밝힌다.
  const points = located.filter((p) => isInBounds(p.lat, p.lng))
  const offMap = located.filter((p) => !isInBounds(p.lat, p.lng))
  const offMapNames = Array.from(new Set(offMap.map((p) => p.name).filter(Boolean)))

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
            <KoreaMap points={points} selectedId={selectedId} onSelect={focusEvent} />
          </div>
          <p className="t-caption mt-2.5">
            점 크기는 그 장소에 남은 기록 수입니다. 점선은 연도순 이동입니다. 점을 누르면
            오른쪽 목록에서 그 사건을 찾아 줍니다.
          </p>
          {offMap.length > 0 && (
            <p className="t-caption mt-1.5" style={{ color: 'var(--ink-400)' }}>
              이 지도는 남한만 그립니다. {offMap.length}곳은 표시하지 못했습니다
              {offMapNames.length > 0 && ' — ' + offMapNames.join(' · ')}. 기록은 그대로
              있고 오른쪽 목록에도 남아 있습니다.
            </p>
          )}
        </div>

        <div className="flex flex-col gap-3">
          {!loading && filtered.length > 0 && (
            <div className="flex items-baseline justify-between">
              <p className="t-eyebrow m-0">사건</p>
              <span className="t-caption">
                누르면 그 사건의 사진을 크게 보고 남은 기록을 함께 읽습니다
              </span>
            </div>
          )}

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
              /*
                버튼으로 둔다. 예전에는 onClick을 얹은 div였는데, 누를 수 있는
                것이 키보드와 스크린 리더에는 없는 것과 같았다.
              */
              <button
                key={event.id}
                ref={(node) => {
                  cardRefs.current[event.id] = node
                }}
                type="button"
                onClick={() => openEvent(event.id)}
                aria-label={`${event.title} 크게 보기`}
                aria-current={active}
                className="block w-full cursor-pointer rounded-lg px-6 py-5 text-left
                           transition-[box-shadow,border-color] duration-200 ease-out"
                style={{
                  background: 'var(--paper-pure)',
                  border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                  /*
                    지도에서 고른 것이 이 카드라는 표시. 테두리 색 하나로는 사진이
                    깔린 카드에서 눈에 띄지 않아, 바깥으로 옅은 테를 한 겹 더 둔다.
                  */
                  boxShadow: active ? '0 0 0 3px var(--accent-soft)' : 'none',
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
                  {/* 카드에 걸린 썸네일은 세 장까지다. 그 뒤가 더 있으면 밝힌다 —
                      세 장이 전부인 것으로 읽히면 눌러 볼 이유가 없어진다.
                      media_count에는 음성도 들어 있어 voice_count를 뺀다. */}
                  {event.media_count - event.voice_count > event.media_thumbs.length && (
                    <span className="t-caption text-ink-300">
                      사진 · 영상 {event.media_count - event.voice_count}개
                    </span>
                  )}
                </div>
              </button>
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

      {openId && <EventSpotlight eventId={openId} onClose={() => setOpenId(null)} />}
    </Page>
  )
}
