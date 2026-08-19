import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getGaps, GapItem } from '../lib/api'
import { Page, PageHeader } from '../components/Page'

/**
 * Memory Gap — AI가 찾아낸 기억의 빈 곳
 *
 * Gap 종류마다 색과 아이콘을 주던 방식을 버렸다. 여섯 종류에 여섯 색을 배분하면
 * 목록이 색표처럼 보이고, 정작 눈에 들어와야 하는 것(무엇이 비었고 무엇을 물어야
 * 하나)이 아이콘 뒤로 밀린다. 종류는 대문자 라벨 한 줄로 충분하다.
 */
const GAP_TYPE_LABEL: Record<string, string> = {
  missing_date: '날짜 없음',
  missing_place: '장소 없음',
  missing_description: '설명 없음',
  no_media: '기록 없음',
  no_participants: '참여자 없음',
  single_perspective: '한쪽 관점',
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
    return (
      <Page width={860}>
        <p className="t-caption">분석 중…</p>
      </Page>
    )
  }

  return (
    <Page width={860}>
      <PageHeader
        eyebrow="Memory Gap"
        title="채워야 할 기억"
        lead="한 사람의 관점만 남은 사건을 AI가 찾아냈습니다. 빠진 정보는 인터뷰로, 기억이 서로 다른 사건은 확인 요청에서 다룹니다."
      />

      {gaps.length === 0 ? (
        <p className="t-body-sm mt-8 text-ink-300">
          발견된 Memory Gap이 없습니다. 지금은 모든 사건에 두 사람 이상의 기억이 있습니다.
        </p>
      ) : (
        <>
          <p className="t-mono mt-4 text-xs text-ink-400">
            총 {gaps.length}개의 Gap이 발견되었습니다.
          </p>

          <div className="rule-strong mt-8">
            {gaps.map((gap) => (
              <div
                key={gap.id}
                className="flex items-start gap-6 px-1 py-6"
                style={{ borderBottom: '1px solid var(--border)' }}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="t-eyebrow text-ink-300">
                      {GAP_TYPE_LABEL[gap.gap_type] || gap.gap_type}
                    </span>
                    {gap.priority >= 4 && (
                      <span
                        className="pill text-[10px]"
                        style={{
                          background: 'var(--accent-soft)',
                          color: 'var(--accent-ink)',
                        }}
                      >
                        중요
                      </span>
                    )}
                  </div>
                  <p className="m-0 mt-2 text-base font-semibold text-ink-900">
                    {gap.description}
                  </p>
                  <p className="t-body-sm m-0 mt-1.5 text-ink-400">{gap.suggested_question}</p>
                  {gap.event_title && (
                    <p className="t-caption m-0 mt-2 text-ink-300">관련 사건 · {gap.event_title}</p>
                  )}
                </div>

                {/* 빠진 것은 인터뷰로, 갈리는 것은 확인으로 보낸다 */}
                <div className="flex shrink-0 flex-col gap-1.5">
                  <Link
                    to="/interview"
                    className="btn-outline text-center no-underline hover:no-underline"
                  >
                    인터뷰로 채우기
                  </Link>
                  {gap.gap_type === 'single_perspective' && (
                    <Link
                      to="/verify"
                      className="btn-quiet text-center no-underline hover:no-underline"
                    >
                      확인 요청 보기
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </Page>
  )
}
