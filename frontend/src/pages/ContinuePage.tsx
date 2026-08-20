import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Heart, Plus } from 'lucide-react'
import { MemoryFeedItem, echoMemory, getMemoryFeed, mediaUrl } from '../lib/api'
import { STATE_CONFIG } from '../components/StatusPill'
import MemoryComposer from '../components/MemoryComposer'
import { Page, PageHeader } from '../components/Page'
import { invalidateEvents } from '../lib/useGraphData'

/**
 * 기억 이어가기 — 예전 "확인 요청"이 있던 자리
 *
 * 같은 목록이지만 목적이 반대다. 예전 화면은 AI가 추정한 사실을 가족이
 * 맞음/모름/이견으로 판정하는 곳이었고, 전원이 답해야 사건이 완료됐다. 그
 * 구조는 고령자와 아이가 함께 쓰는 가족 앱에서 성립하지 않는다 — 아무도
 * 답하지 않는 추억이 영원히 미완으로 남는다.
 *
 * 그래서 판정 버튼을 다 뺐다. 남은 것은 둘이다.
 *
 *   나도 기억나요     누르기만 한다 (안 눌러도 된다)
 *   + 내 기억 더하기  이 화면에서 가장 중요한 자리
 *
 * 목록에 "처리해야 할 건수"를 강조색으로 세우지 않는 것도 같은 이유다. 숫자를
 * 크게 두면 그 순간 이 화면은 다시 과제 목록이 된다.
 */
export default function ContinuePage() {
  const [items, setItems] = useState<MemoryFeedItem[]>([])
  const [openCount, setOpenCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [composing, setComposing] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    getMemoryFeed()
      .then((res) => {
        setItems(res.items)
        setOpenCount(res.open_count)
      })
      .catch((e) => {
        console.error(e)
        setError('추억을 불러오지 못했습니다.')
      })

  useEffect(() => {
    load().finally(() => setLoading(false))
  }, [])

  const toggleEcho = async (eventId: string) => {
    setBusy(eventId)
    try {
      const res = await echoMemory(eventId)
      // 낙관적으로 갈아 끼우지 않고 서버가 준 결과로 맞춘다 (두 번 눌렀을 때
      // 화면과 데이터가 어긋나지 않게)
      setItems((prev) =>
        prev.map((item) =>
          item.event_id === eventId
            ? {
                ...item,
                i_echoed: res.echoed,
                echo_count: res.echo_count,
                echoed_by: res.echoed_by,
              }
            : item,
        ),
      )
      invalidateEvents()
    } catch (e) {
      console.error(e)
      setError('기억나요 표시를 남기지 못했습니다.')
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return (
      <Page width={860}>
        <p className="t-caption">불러오는 중…</p>
      </Page>
    )
  }

  return (
    <Page width={860}>
      <PageHeader
        eyebrow="Keep Remembering"
        title="기억 이어가기"
        lead="가족이 만든 추억입니다. 기억나는 것이 있을 때만 더하면 됩니다. 아무것도 하지 않아도 괜찮습니다."
      />

      {openCount > 0 && (
        <p className="t-caption mt-4">
          아직 내 기억을 얹지 않은 추억 {openCount}개 · 확인해야 할 일은 아닙니다
        </p>
      )}

      {error && (
        <p className="t-body-sm mt-4" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {items.length === 0 ? (
        <div className="mt-8">
          <p className="t-body-sm m-0 text-ink-300">아직 가족 공간에 추억이 없습니다.</p>
          <Link
            to="/collect"
            className="btn-primary mt-5 inline-block no-underline hover:no-underline"
          >
            사진 올려서 첫 추억 만들기
          </Link>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-4">
          {items.map((item) => {
            const config = STATE_CONFIG[item.state] ?? STATE_CONFIG.alone
            const isBusy = busy === item.event_id
            const showAll = expanded[item.event_id]
            const shown = showAll ? item.contributions : item.contributions.slice(0, 2)

            return (
              <div key={item.event_id} className="surface p-7">
                {/* 사진 먼저 — 이 화면에서 기억을 불러오는 것은 문장이 아니라 사진이다 */}
                {item.thumbs.length > 0 && (
                  <div className="mb-5 flex gap-2">
                    {item.thumbs.map((thumb) => (
                      <img
                        key={thumb}
                        src={mediaUrl(thumb)}
                        alt=""
                        className="h-[92px] w-[124px] rounded bg-ink-50 object-cover"
                      />
                    ))}
                    {item.media_count > item.thumbs.length && (
                      <span
                        className="t-caption flex h-[92px] w-[124px] items-center justify-center
                                   rounded bg-ink-50"
                      >
                        +{item.media_count - item.thumbs.length}
                      </span>
                    )}
                  </div>
                )}

                <div className="flex items-start justify-between gap-5">
                  <div className="min-w-0">
                    <Link
                      to={`/memory/${item.event_id}`}
                      className="m-0 block text-[19px] font-semibold text-ink-900 no-underline
                                 hover:no-underline"
                    >
                      {item.title}
                    </Link>
                    <p className="t-body-sm m-0 mt-1 text-ink-400">
                      {item.date_start || '날짜 미상'}
                      {item.place?.name && ` · ${item.place.name}`}
                      {item.author?.name && (
                        <>
                          {' · '}
                          {item.mine ? '내가 만든 추억' : `${item.author.name}님이 만든 추억`}
                        </>
                      )}
                    </p>
                  </div>
                  <span className="pill shrink-0" style={{ background: config.bg, color: config.fg }}>
                    {config.label}
                  </span>
                </div>

                {/* 최초 작성자의 기억 */}
                {item.author_memory && (
                  <div className="mt-5 rounded bg-ink-50 px-4 py-3.5">
                    <p className="t-caption m-0 mb-1 text-accent-ink">
                      {item.author_memory.contributor?.name || '가족'}의 기억
                    </p>
                    <p className="t-body-sm m-0 text-ink-700">
                      {item.author_memory.polished || item.author_memory.content}
                    </p>
                  </div>
                )}

                {/* 가족이 더한 기억 */}
                {item.contributions.length > 0 && (
                  <div className="mt-2.5 flex flex-col gap-2">
                    {shown.map((memory) => (
                      <div key={memory.id} className="rounded bg-ink-50 px-4 py-3.5">
                        <p className="t-caption m-0 mb-1">
                          {memory.contributor?.name || '가족'}이 더한 기억
                          {memory.differs && ' · 조금 다르게 기억'}
                        </p>
                        <p className="t-body-sm m-0 text-ink-700">
                          {memory.polished || memory.content}
                        </p>
                      </div>
                    ))}
                    {item.contributions.length > 2 && (
                      <button
                        onClick={() =>
                          setExpanded((prev) => ({
                            ...prev,
                            [item.event_id]: !prev[item.event_id],
                          }))
                        }
                        className="btn-link self-start"
                      >
                        {showAll
                          ? '접기'
                          : `가족이 더한 기억 ${item.contributions.length}개 모두 보기`}
                      </button>
                    )}
                  </div>
                )}

                {/* 서로 다르게 기억하는 경우 — 고칠 것이 아니라 알리는 것이다 */}
                {item.varied && (
                  <p
                    className="t-body-sm m-0 mt-3 rounded px-4 py-3"
                    style={{ background: 'var(--critical-soft)', color: 'var(--critical-ink)' }}
                  >
                    가족들이 조금 다르게 기억하고 있어요. 어느 쪽도 지우지 않았습니다.
                  </p>
                )}

                {/* 행동 — 판정이 아니라 공감과 덧붙임 */}
                <div className="mt-5 flex flex-wrap items-center gap-2 pt-5" style={{ borderTop: '1px solid var(--border)' }}>
                  <button
                    onClick={() => toggleEcho(item.event_id)}
                    disabled={isBusy}
                    className="flex cursor-pointer items-center gap-1.5 rounded bg-transparent
                               px-3 py-1.5 text-xs disabled:opacity-40"
                    style={
                      item.i_echoed
                        ? { border: '1px solid var(--positive)', color: 'var(--positive-ink)' }
                        : { border: '1px solid var(--border-strong)', color: 'var(--ink-500)' }
                    }
                  >
                    <Heart size={13} fill={item.i_echoed ? 'currentColor' : 'none'} />
                    나도 기억나요
                    {item.echo_count > 0 && ` ${item.echo_count}`}
                  </button>

                  <button
                    onClick={() =>
                      setComposing((prev) => (prev === item.event_id ? null : item.event_id))
                    }
                    className="btn-primary flex items-center gap-1.5 px-4 py-2 text-[13px]"
                  >
                    <Plus size={14} />
                    내 기억 더하기
                  </button>

                  <Link
                    to={`/memory/${item.event_id}`}
                    className="btn-quiet ml-auto no-underline hover:no-underline"
                  >
                    자세히 보기
                  </Link>
                </div>

                {composing === item.event_id && (
                  <div className="mt-4">
                    <MemoryComposer
                      eventId={item.event_id}
                      placeholder={`'${item.title}'에서 기억나는 것을 적어 주세요.`}
                      onCancel={() => setComposing(null)}
                      onSaved={() => {
                        setComposing(null)
                        load()
                      }}
                    />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Page>
  )
}
