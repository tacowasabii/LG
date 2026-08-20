import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getEventDetail,
  getEvents,
  getMediaList,
  getMemoryFeed,
  getGraph,
  EventListItem,
  MediaItem,
  MemoryFeedItem,
  mediaUrl,
} from '../lib/api'
import { STATE_CONFIG, STATE_ORDER } from '../components/StatusPill'
import AudioClip from '../components/AudioClip'
import { Page, PageHeader, SectionHead, StatRow } from '../components/Page'
import { useVoiceClips } from '../lib/useGraphData'

interface EventMedia {
  id: string
  file_path: string
  /** 서버는 썸네일이 없으면 null을 준다 (getEventDetail) */
  thumbnail_path?: string | null
  media_type?: string
}

/** 연도는 왼쪽 기둥에 따로 세우므로 제목에서 뗀다 */
function shortTitle(title: string): string {
  return title.replace(/^\d{4}\s*/, '')
}


export default function HomePage() {
  const [events, setEvents] = useState<EventListItem[]>([])
  const [media, setMedia] = useState<MediaItem[]>([])
  /** 기억을 더할 수 있는 가족의 추억 (과제 목록이 아니라 초대다) */
  const [openMemories, setOpenMemories] = useState<MemoryFeedItem[]>([])
  const [memoryCount, setMemoryCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null)
  // 가족이 실제로 남긴 목소리 (인터뷰에서 녹음한 것)
  const { clips: voiceClips } = useVoiceClips()
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
      // api 계층을 지나야 배포 주소(VITE_API_URL)와 열람자가 함께 나간다.
      // 여기서 직접 fetch하면 백엔드가 다른 도메인인 배포에서 조용히 실패하고,
      // 서버가 공개 범위를 적용할 수도 없다.
      const detail = await getEventDetail(eventId)
      setEventMedia((prev) => ({ ...prev, [eventId]: detail.media || [] }))
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    // 기억 개수는 전용 엔드포인트가 없어 Graph에서 센다.
    // 정적 모드에서도 mock/graph.json으로 동작한다.
    Promise.all([getEvents(), getMediaList(), getGraph()])
      .then(([e, m, graph]) => {
        setEvents(e)
        setMedia(m)
        setMemoryCount(graph.nodes.filter((n) => n.node_type === 'memory').length)
      })
      .catch(console.error)
      .finally(() => setLoading(false))

    // 기억 이어가기 목록은 따로 받는다. 이 하나가 실패해도 타임라인은 그려져야
    // 한다 — 한 묶음으로 묶으면 권유 카드 하나 때문에 홈 전체가 빈다.
    getMemoryFeed()
      .then((feed) => setOpenMemories(feed.items.filter((i) => !i.mine && !i.i_added)))
      .catch((e) => console.error('[home] 기억 이어가기 목록을 불러오지 못했습니다', e))
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

  // 기억이 쌓인 정도 막대 — 추억 목록이 상태를 함께 내려준다
  const stateBar = STATE_ORDER.map((state) => ({
    state,
    count: events.filter((e) => e.state === state).length,
  })).filter((b) => b.count > 0)

  return (
    <Page width={1040}>
      <PageHeader
        large
        eyebrow={`${span}추억 ${events.length}개`}
        title="우리의 기억"
        lead="사진과 이야기로 연결된 사람들의 시간. 한 사람이 만든 추억에 가족이 기억을 더하면서 쌓입니다."
      />

      <div className="mt-12">
        <StatRow
          cells={[
            { value: events.length, label: '추억' },
            { value: media.length, label: '사진 · 영상' },
            { value: memoryCount ?? '—', label: '기억 문장' },
            {
              value: events.reduce((sum, e) => sum + (e.echo_count || 0), 0),
              label: '나도 기억나요',
            },
          ]}
        />
      </div>

      {/* 처음 오는 사람을 위한 길 — 기획안 리스크 "데이터가 처음엔 없음"에 대한 답 */}
      <Link
        to="/collect"
        className="banner-accent mt-10 flex items-center gap-4 rounded-lg px-6 py-5
                   no-underline transition-colors duration-150 ease-out hover:no-underline"
      >
        <span className="flex-1">
          <span className="block text-[15px] font-semibold text-ink-900">처음이신가요?</span>
          <span className="t-body-sm mt-1 block text-ink-400">
            사진 3장을 올리면 AI가 첫 추억의 초안을 씁니다. 확인하면 바로 가족 기록이 됩니다.
          </span>
        </span>
        <span className="text-xl text-accent-ink">→</span>
      </Link>

      {/* 기억이 쌓인 모습 — 확인 여부가 아니라 "가족이 얼마나 함께 기억하는가" */}
      <section className="mt-14">
        <SectionHead title="기억이 쌓인 모습" to="/continue" linkLabel="기억 이어가기" />

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
                width: (b.count / Math.max(1, events.length)) * 100 + '%',
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
          한 사람의 기억으로 남아 있어도 그대로 가족 기록입니다. 확인을 기다리는 추억은
          없습니다.
        </p>
      </section>

      <section className="mt-14">
        <SectionHead title="타임라인" to="/graph" linkLabel="그래프로 보기" strong />

        {events.length === 0 ? (
          <div className="py-12 text-center">
            <p className="t-body-sm m-0 text-ink-300">아직 추억이 없습니다.</p>
            <Link to="/collect" className="btn-primary mt-5 inline-block no-underline hover:no-underline">
              사진 올리기
            </Link>
          </div>
        ) : (
          events.map((event) => {
            const config = STATE_CONFIG[event.state] ?? STATE_CONFIG.alone
            const open = expandedEvent === event.id
            const counts = [
              `사진 ${event.media_count}`,
              `기억 ${event.memory_count}`,
              event.voice_count > 0 ? `음성 ${event.voice_count}` : null,
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
                                poster={mediaUrl(m.thumbnail_path)}
                                preload="none"
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
                              {event.participants.map((p) => p.name).join(' · ')}
                            </span>
                            <Link
                              to={`/memory/${event.id}`}
                              className="t-caption mt-1.5 block text-accent-ink"
                            >
                              이 추억 자세히 보기 →
                            </Link>
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
        <SectionHead title="가족의 목소리" to="/interview" linkLabel="목소리 남기기" />
        {voiceClips.length > 0 ? (
          <div className="mt-5 grid grid-cols-2 gap-4">
            {voiceClips.slice(0, 4).map((clip) => (
              <AudioClip key={clip.id} clip={clip} />
            ))}
          </div>
        ) : (
          <div className="mt-5 py-10 text-center" style={{ border: '1px dashed var(--border-strong)' }}>
            <p className="t-body-sm m-0 text-ink-400">아직 남은 목소리가 없습니다.</p>
            <p className="t-caption m-0 mt-1">
              인터뷰에서 말로 답하면 목소리 원본이 그대로 보관됩니다.
            </p>
            <Link
              to="/interview"
              className="btn-outline mt-5 inline-block no-underline hover:no-underline"
            >
              목소리 남기기
            </Link>
          </div>
        )}
      </section>

      {/*
        예전에 "채워야 할 기억"(Memory Gap)이 있던 자리다. 빈칸을 과제로 세우는
        대신, 다른 가족이 만든 추억을 보여 주고 기억나면 더하라고 권한다.
        아무것도 하지 않아도 된다는 문장을 함께 둔다.
      */}
      {openMemories.length > 0 && (
        <section className="mt-14">
          <SectionHead title="기억 이어가기" to="/continue" linkLabel="전체 보기" />
          <p className="t-caption mt-2">
            가족이 만든 추억입니다. 기억나는 것이 있을 때만 더하면 됩니다.
          </p>
          <div className="mt-5 grid grid-cols-2 gap-4">
            {openMemories.slice(0, 4).map((item) => (
              <Link
                key={item.event_id}
                to={`/memory/${item.event_id}`}
                className="surface hover-border-accent p-5 no-underline hover:no-underline"
              >
                <p className="t-mono m-0 text-[11px] text-ink-300">
                  {item.author?.name ? `${item.author.name}님이 만든 추억` : '가족의 추억'}
                  {item.date_start ? ` · ${item.date_start}` : ''}
                </p>
                <p className="m-0 mt-2 text-sm font-semibold text-ink-700">{item.title}</p>
                {item.author_memory && (
                  <p className="t-body-sm m-0 mt-2 text-ink-400">
                    {item.author_memory.polished || item.author_memory.content}
                  </p>
                )}
                <span className="t-caption mt-3 block text-accent-ink">내 기억 더하기 →</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </Page>
  )
}
