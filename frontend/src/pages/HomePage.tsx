import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Calendar, Image, MessageCircle, AlertCircle, ChevronDown } from 'lucide-react'
import { getEvents, getMediaList, getGaps, EventListItem, MediaItem, GapsResponse } from '../lib/api'

interface EventMedia {
  id: string;
  file_path: string;
  thumbnail_path?: string;
  media_type?: string;
}

export default function HomePage() {
  const [events, setEvents] = useState<EventListItem[]>([])
  const [media, setMedia] = useState<MediaItem[]>([])
  const [gaps, setGaps] = useState<GapsResponse | null>(null)
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
    Promise.all([getEvents(), getMediaList(), getGaps()])
      .then(([e, m, g]) => {
        setEvents(e)
        setMedia(m)
        setGaps(g)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><p className="text-gray-400">불러오는 중...</p></div>
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">우리 가족의 기억</h1>
        <p className="text-gray-500 mt-1">사진과 이야기로 연결된 가족의 시간들</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard icon={Calendar} label="이벤트" value={events.length} color="blue" />
        <StatCard icon={Image} label="미디어" value={media.length} color="green" />
        <StatCard icon={MessageCircle} label="기억" value="-" color="purple" />
        <StatCard icon={AlertCircle} label="Memory Gap" value={gaps?.total ?? 0} color="orange" />
      </div>

      {/* Timeline */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">타임라인</h2>
          <Link to="/graph" className="text-sm text-primary-600 hover:text-primary-700">그래프로 보기 →</Link>
        </div>

        {events.length === 0 ? (
          <div className="card text-center py-12">
            <p className="text-gray-400">아직 이벤트가 없습니다.</p>
            <Link to="/upload" className="btn-primary inline-block mt-4">사진 업로드하기</Link>
          </div>
        ) : (
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-gray-200" />

            <div className="space-y-4">
              {events.map((event) => (
                <div key={event.id} className="relative flex gap-4">
                  {/* Dot */}
                  <div className="relative z-10 w-12 h-12 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                    <Calendar size={18} className="text-primary-600" />
                  </div>

                  {/* Content */}
                  <div className="card flex-1 cursor-pointer hover:shadow-md transition-shadow" onClick={() => toggleEvent(event.id)}>
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-medium text-gray-900">{event.title}</h3>
                        <p className="text-sm text-gray-500 mt-0.5">
                          {event.date_start || '날짜 미상'}
                          {event.location_name && ` · ${event.location_name}`}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-gray-400">
                        <span>{event.participant_count}명 참여</span>
                        <span>사진 {event.media_count}</span>
                        <ChevronDown size={14} className={`transition-transform ${expandedEvent === event.id ? 'rotate-180' : ''}`} />
                      </div>
                    </div>

                    {/* Expanded Media */}
                    {expandedEvent === event.id && (
                      <div className="mt-3 pt-3 border-t border-gray-100">
                        {eventMedia[event.id] ? (
                          eventMedia[event.id].length > 0 ? (
                            <div className="grid grid-cols-3 gap-2">
                              {eventMedia[event.id].map((m) => (
                                <div key={m.id} className="aspect-square rounded-md overflow-hidden bg-gray-100">
                                  {m.media_type === 'video' ? (
                                    <video src={m.file_path} className="w-full h-full object-cover" muted playsInline />
                                  ) : (
                                    <img
                                      src={m.thumbnail_path || m.file_path}
                                      alt=""
                                      className="w-full h-full object-cover"
                                    />
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-sm text-gray-400">연결된 사진이 없습니다.</p>
                          )
                        ) : (
                          <p className="text-sm text-gray-400 animate-pulse">불러오는 중...</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Recent Media */}
      {media.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800">최근 미디어</h2>
            <Link to="/upload" className="text-sm text-primary-600 hover:text-primary-700">더 보기 →</Link>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {media.slice(0, 8).map((item) => (
              <div key={item.id} className="aspect-square rounded-lg overflow-hidden bg-gray-100 border border-gray-200 relative">
                {item.media_type === 'video' ? (
                  <video
                    src={item.file_path}
                    className="w-full h-full object-cover"
                    muted
                    playsInline
                    onMouseEnter={(e) => (e.target as HTMLVideoElement).play()}
                    onMouseLeave={(e) => { const v = e.target as HTMLVideoElement; v.pause(); v.currentTime = 0 }}
                  />
                ) : (
                  <img
                    src={item.thumbnail_path || item.file_path}
                    alt={item.original_filename}
                    className="w-full h-full object-cover"
                  />
                )}
                {item.media_type === 'video' && (
                  <div className="absolute bottom-1 right-1 bg-black/60 text-white text-xs px-1.5 py-0.5 rounded">▶</div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Gaps Preview */}
      {gaps && gaps.total > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800">채워야 할 기억</h2>
            <Link to="/gaps" className="text-sm text-primary-600 hover:text-primary-700">전체 보기 →</Link>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {gaps.gaps.slice(0, 4).map((gap) => (
              <div key={gap.id} className="card border-l-4 border-l-orange-400">
                <p className="text-sm text-gray-700">{gap.description}</p>
                <p className="text-xs text-gray-400 mt-1">💡 {gap.suggested_question}</p>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }: { icon: any; label: string; value: number | string; color: string }) {
  const colors: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    purple: 'bg-purple-50 text-purple-600',
    orange: 'bg-orange-50 text-orange-600',
  }
  return (
    <div className="card flex items-center gap-3">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${colors[color]}`}>
        <Icon size={20} />
      </div>
      <div>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        <p className="text-xs text-gray-500">{label}</p>
      </div>
    </div>
  )
}
