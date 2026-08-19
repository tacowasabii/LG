import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getEvents,
  getMediaList,
  getGaps,
  getGraph,
  EventListItem,
  MediaItem,
  GapsResponse,
  mediaUrl,
} from '../lib/api'
import { STATE_CONFIG, STATE_ORDER } from '../components/StatusPill'
import AudioClip from '../components/AudioClip'
import MockBadge from '../components/MockBadge'
import { Page, PageHeader, SectionHead, StatRow } from '../components/Page'
import { MOCK_TIMELINE, eventById } from '../mock/timeline'
import { MOCK_VOICE_CLIPS } from '../mock/voice'
import { MOCK_MEMBERS } from '../mock/family'

interface EventMedia {
  id: string
  file_path: string
  thumbnail_path?: string
  media_type?: string
}

/** 연도는 왼쪽 기둥에 따로 세우므로 제목에서 뗀다 */
function shortTitle(title: string): string {
  return title.replace(/^\d{4}\s*/, '')
}

function memberName(id: string): string {
  return MOCK_MEMBERS.find((m) => m.id === id)?.name || id
}

export default function HomePage() {
  const [events, setEvents] = useState<EventListItem[]>([])
  const [media, setMedia] = useState<MediaItem[]>([])
  const [gaps, setGaps] = useState<GapsResponse | null>(null)
  const [memoryCount, setMemoryCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null)
  const [eventMedia, setEventMedia] = useState<Record<string, EventMedia[]>>({})

  const toggleEvent = async (eventId: string) => {
    if (expandedEvent === eventId) {
      setExpandedEvent(null)
      return
    }
    setExpandedEvent(eventId)
    // 이미 로드했으면 스킵
    if (eventMedia[eventId]) return
    try {
      const staticMode = import.meta.env.VITE_STATIC_MODE === 'true'
      const url = staticMode ? `/mock/events/${eventId}.json` : `/api/graph/event/${eventId}`
      const res = await fetch(url)
      const data = await res.json()
      setEventMedia((prev) => ({ ...prev, [eventId]: data.media || [] }))
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    // 기억 개수는 전용 엔드포인트가 없어 Graph에서 센다.
    // 정적 모드에서도 mock/graph.json으로 동작한다.
    Promise.all([getEvents(), getMediaList(), getGaps(), getGraph()])
      .then(([e, m, g, graph]) => {
        setEvents(e)
        setMedia(m)
        setGaps(g)
        setMemoryCount(graph.nodes.filter((n) => n.node_type === 'memory').length)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Page width={1040}>
        <p className="t-caption">불러오는 중…</p>
      </Page>
    )
  }

  const years = events
    .map((e) => e.date_start?.slice(0, 4))
    .filter((y): y is string => !!y)
    .sort()
  const span = years.length > 0 ? `${years[0]} — ${years[years.length - 1]} · ` : ''

  // 확인 상태 막대 — 실기능 개발 시 GET /api/graph/verify 의 상태 합계로 교체
  const stateBar = STATE_ORDER.map((state) => ({
    state,
    count: MOCK_TIMELINE.filter((e) => e.state === state).length,
  })).filter((b) => b.count > 0)

  return (
    <Page width={1040}>
      <PageHeader
        large
        eyebrow={`${span}사건 ${events.length}개`}
        title="우리의 기억"
        lead="사진과 이야기로 연결된 사람들의 시간. 무엇이 확인된 사실이고 무엇이 아직 추정인지 함께 표시합니다."
      />

      <div className="mt-12">
        <StatRow
          cells={[
            { value: events.length, label: '사건' },
            { value: media.length, label: '사진 · 영상' },
            { value: memoryCount ?? '—', label: '기억 문장' },
            { value: gaps?.total ?? 0, label: '채워야 할 기억', accent: true },
          ]}
        />
      </div>

      {/* 처음 오는 사람을 위한 길 — 기획안 리스크 "데이터가 처음엔 없음"에 대한 답 */}
      <Link
        to="/onboarding"
        className="banner-accent mt-10 flex items-center gap-4 rounded-lg px-6 py-5
                   no-underline transition-colors duration-150 ease-out hover:no-underline"
      >
        <span className="flex-1">
          <span className="block text-[15px] font-semibold text-ink-900">처음이신가요?</span>
          <span className="t-body-sm mt-1 block text-ink-400">
            사진 3장으로 첫 사건을 만들어 봅니다. 나머지는 질문에 답하면서 채워집니다.
          </span>
        </span>
        <span className="text-xl text-accent-ink">→</span>
      </Link>

      {/* 확인 상태 — 무엇이 사실이고 무엇이 추정인지 한눈에 (기획안 03장) */}
      <section className="mt-14">
        <SectionHead title="확인 상태" to="/verify" linkLabel="확인하러 가기">
          <MockBadge />
        </SectionHead>

        {/*
          막대를 하나로 이어 붙이지 않고 2px씩 띄운다. 상태가 서로 섞이는 값이
          아니라 서로 다른 종류라는 것을 모양으로 먼저 알리기 위한 것이다.
        */}
        <div className="mt-5 flex h-2 gap-[2px]">
          {stateBar.map((b) => (
            <div
              key={b.state}
              style={{
                background: STATE_CONFIG[b.state].dot,
                width: (b.count / MOCK_TIMELINE.length) * 100 + '%',
              }}
            />
          ))}
        </div>

        <div className="mt-4 flex flex-wrap gap-5">
          {stateBar.map((b) => (
            <span key={b.state} className="flex items-center gap-2">
              <span
                className="h-2 w-2 rounded-full"
                style={{ background: STATE_CONFIG[b.state].dot }}
              />
              <span className="text-[13px] text-ink-500">{STATE_CONFIG[b.state].label}</span>
              <span className="t-mono text-xs text-ink-300">{b.count}건</span>
            </span>
          ))}
        </div>

        <p className="t-caption mt-4">
          추정한 정보는 확정하지 않습니다. 가족이 확인해야 사실이 됩니다.
        </p>
      </section>

      <section className="mt-14">
        <SectionHead title="타임라인" to="/graph" linkLabel="그래프로 보기" strong />

        {events.length === 0 ? (
          <div className="py-12 text-center">
            <p className="t-body-sm m-0 text-ink-300">아직 사건이 없습니다.</p>
            <Link to="/upload" className="btn-primary mt-5 inline-block no-underline hover:no-underline">
              사진 올리기
            </Link>
          </div>
        ) : (
          events.map((event) => {
            const mock = eventById(event.id)
            const state = mock?.state ?? 'inferred'
            const config = STATE_CONFIG[state]
            const open = expandedEvent === event.id
            const counts = [
              `사진 ${event.media_count}`,
              mock ? `기억 ${mock.memory_count}` : null,
              mock && mock.voice_count > 0 ? `음성 ${mock.voice_count}` : null,
            ]
              .filter(Boolean)
              .join(' · ')

            return (
              <div key={event.id} style={{ borderBottom: '1px solid var(--border)' }}>
                <button
                  onClick={() => toggleEvent(event.id)}
                  className="flex w-full items-start gap-6 px-1 py-5 text-left hover:bg-ink-50"
                >
                  <span className="t-mono w-10 shrink-0 pt-[3px] text-[13px] text-accent-ink">
                    {event.date_start?.slice(0, 4) || '연도'}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-base font-semibold text-ink-900">
                      {shortTitle(event.title)}
                    </span>
                    <span className="t-body-sm mt-[3px] block text-ink-400">
                      {event.date_start || '날짜 미상'}
                      {event.location_name && ` · ${event.location_name}`}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-3 pt-0.5">
                    <span className="pill" style={{ background: config.bg, color: config.fg }}>
                      {config.label}
                    </span>
                    <span className="t-mono text-[11px] text-ink-300">{counts}</span>
                    <span className="w-2.5 text-[11px] text-ink-300">{open ? '▲' : '▼'}</span>
                  </span>
                </button>

                {open && (
                  <div className="flex gap-2 pb-6 pl-16 pr-1">
                    {eventMedia[event.id] ? (
                      eventMedia[event.id].length > 0 ? (
                        <>
                          {eventMedia[event.id].map((m) =>
                            m.media_type === 'video' ? (
                              <video
                                key={m.id}
                                src={mediaUrl(m.file_path)}
                                className="h-24 w-[132px] rounded bg-ink-50 object-cover"
                                muted
                                playsInline
                              />
                            ) : (
                              <img
                                key={m.id}
                                src={mediaUrl(m.thumbnail_path || m.file_path)}
                                alt=""
                                className="h-24 w-[132px] rounded bg-ink-50 object-cover"
                              />
                            ),
                          )}
                          <span className="self-end pb-1 pl-2">
                            <span className="t-caption block">{event.location_name}</span>
                            <span className="t-caption block text-ink-300">
                              {mock?.participant_ids.map(memberName).join(' · ')}
                            </span>
                          </span>
                        </>
                      ) : (
                        <p className="t-caption m-0">연결된 사진이 없습니다.</p>
                      )
                    ) : (
                      <p className="t-caption m-0">불러오는 중…</p>
                    )}
                  </div>
                )}
              </div>
            )
          })
        )}
      </section>

      {/* 가족의 목소리 — 기획안이 "핵심 독자 데이터"로 지목한 자산 */}
      <section className="mt-14">
        <SectionHead title="가족의 목소리" to="/interview" linkLabel="목소리 남기기">
          <MockBadge label="음성 목데이터" />
        </SectionHead>
        <div className="mt-5 grid grid-cols-2 gap-4">
          {MOCK_VOICE_CLIPS.slice(0, 4).map((clip) => (
            <AudioClip key={clip.id} clip={clip} />
          ))}
        </div>
      </section>

      {gaps && gaps.total > 0 && (
        <section className="mt-14">
          <SectionHead title="채워야 할 기억" to="/gaps" linkLabel="전체 보기" />
          <div className="mt-5 grid grid-cols-2 gap-4">
            {gaps.gaps.slice(0, 4).map((gap) => (
              <div key={gap.id} className="surface p-5">
                <p className="t-mono m-0 text-[11px] text-ink-300">{gap.event_title}</p>
                <p className="m-0 mt-2 text-sm font-semibold text-ink-700">{gap.description}</p>
                <p className="t-body-sm m-0 mt-2 text-ink-400">{gap.suggested_question}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </Page>
  )
}
