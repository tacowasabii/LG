import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, Calendar, MapPin, Image, Users, MessageSquare } from 'lucide-react'
import { getGaps, GapItem } from '../lib/api'

const GAP_TYPE_CONFIG: Record<string, { icon: typeof AlertCircle; label: string; color: string }> = {
  missing_date: { icon: Calendar, label: '날짜 없음', color: 'text-blue-500 bg-blue-50' },
  missing_place: { icon: MapPin, label: '장소 없음', color: 'text-green-500 bg-green-50' },
  missing_description: { icon: MessageSquare, label: '설명 없음', color: 'text-purple-500 bg-purple-50' },
  no_media: { icon: Image, label: '미디어 없음', color: 'text-orange-500 bg-orange-50' },
  no_participants: { icon: Users, label: '참여자 없음', color: 'text-red-500 bg-red-50' },
  single_perspective: { icon: Users, label: '한쪽 관점', color: 'text-pink-500 bg-pink-50' },
}

export default function GapsPage() {
  const [gaps, setGaps] = useState<GapItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getGaps()
      .then((res) => setGaps(res.gaps))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="flex items-center justify-center h-64"><p className="text-gray-400">분석 중...</p></div>
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Memory Gap</h1>
        <p className="text-gray-500 mt-1">
          가족 기억에서 빠진 부분을 AI가 자동으로 찾아냈습니다. 인터뷰를 통해 채워보세요.
        </p>
      </div>

      {gaps.length === 0 ? (
        <div className="card text-center py-12">
          <AlertCircle size={40} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-400">발견된 Memory Gap이 없습니다. 훌륭해요!</p>
        </div>
      ) : (
        <>
          <div className="text-sm text-gray-500">
            총 <span className="font-medium text-gray-700">{gaps.length}개</span>의 Gap이 발견되었습니다.
          </div>

          <div className="space-y-3">
            {gaps.map((gap) => {
              const config = GAP_TYPE_CONFIG[gap.gap_type] || GAP_TYPE_CONFIG.missing_description
              const Icon = config.icon

              return (
                <div key={gap.id} className="card hover:shadow-md transition-shadow">
                  <div className="flex items-start gap-4">
                    {/* Type Badge */}
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${config.color}`}>
                      <Icon size={18} />
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-gray-400 uppercase">{config.label}</span>
                        {gap.priority >= 4 && (
                          <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded">중요</span>
                        )}
                      </div>
                      <p className="text-sm font-medium text-gray-800">{gap.description}</p>
                      <p className="text-sm text-gray-500 mt-1">
                        💡 {gap.suggested_question}
                      </p>
                      {gap.event_title && (
                        <p className="text-xs text-gray-400 mt-2">
                          관련 이벤트: {gap.event_title}
                        </p>
                      )}
                    </div>

                    {/* Action */}
                    <Link
                      to="/interview"
                      className="text-xs text-primary-600 hover:text-primary-700 font-medium flex-shrink-0"
                    >
                      인터뷰 →
                    </Link>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
