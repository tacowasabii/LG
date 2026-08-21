/**
 * 추억 크게 보기 — 타임라인 · 지도에서 추억 하나를 열었을 때
 *
 * 지도 목록의 카드는 썸네일 세 장으로 "여기 뭔가 있다"까지만 말한다. 그걸
 * 누른 사람이 보고 싶은 것은 그 추억의 사진 전부와, 그날에 대해 남은 기록이다.
 * 예전에는 눌러도 테두리 색만 바뀌어서 누른 것이 아무 데도 닿지 않았다.
 *
 * 그래서 Memory Film과 같은 방식으로 띄운다 — 어두운 면에 사진 한 장을 크게,
 * 자동으로 넘어가게, 아래에 필름처럼 늘어놓는다. 다른 점은 여기가 사진을
 * 자르지 않는다는 것이다 (object-contain). Film은 이야기를 위해 화면비를
 * 맞추지만 여기는 사진 자체를 보는 자리라서, 가족 얼굴이 잘려서는 안 된다.
 *
 * 주소는 바꾸지 않는다. 지도에서 추억을 훑다가 하나를 열고 다시 훑는 동작이라
 * 그 사이에 페이지가 바뀌면 걸어 둔 인물·시기 조건과 스크롤을 잃는다.
 *
 * 한 번의 GET /api/memories/{event_id}로 사진 · 참여자 · 기억 문장 · 목소리가
 * 함께 온다 (getMemoryDetail). 추억마다 여러 번 부르지 않는다.
 */

import { ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Clapperboard, Heart, X } from 'lucide-react'
import { MemoryDetail, MemoryEntry, getMemoryDetail, mediaUrl } from '../lib/api'
import AudioClip from './AudioClip'
import { STATE_CONFIG } from './StatusPill'

/** 한 장을 보여 주는 시간. Film의 장면 길이(4~6초)와 같은 감각으로 잡았다 */
const SLIDE_MS = 4800

/**
 * 장면마다 다른 카메라 움직임. Film은 서버가 정해 주지만 여기는 이야기가 아니라
 * 사진 목록이라 순서로 돌린다 — 같은 움직임이 반복되면 슬라이드쇼로 읽힌다.
 */
const MOTIONS = ['motion-zoom-in', 'motion-pan-left', 'motion-zoom-out', 'motion-pan-right']

interface Props {
  eventId: string
  onClose: () => void
}

export default function EventSpotlight({ eventId, onClose }: Props) {
  const [detail, setDetail] = useState<MemoryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const touchStartX = useRef<number | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    setDetail(null)
    setIndex(0)
    setPlaying(false)

    getMemoryDetail(eventId)
      .then((d) => {
        if (alive) setDetail(d)
      })
      .catch((e) => {
        console.error('[map] 추억을 불러오지 못했습니다', e)
        if (alive) setError('이 추억을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })

    return () => {
      alive = false
    }
  }, [eventId])

  const visuals = (detail?.media ?? []).filter((m) => m.media_type !== 'audio')
  const audios = (detail?.media ?? []).filter((m) => m.media_type === 'audio')
  const current = visuals[index]
  const last = visuals.length - 1

  const go = useCallback(
    (next: number) => {
      if (next < 0 || next > last) return
      setIndex(next)
    },
    [last],
  )

  // 키보드 — 방향키로 넘기고, Esc로 닫는다
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') {
        setPlaying(false)
        setIndex((prev) => (prev > 0 ? prev - 1 : prev))
      }
      if (e.key === 'ArrowRight') {
        setPlaying(false)
        setIndex((prev) => (prev < last ? prev + 1 : prev))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [last, onClose])

  // 열려 있는 동안 뒤 화면이 따라 스크롤되지 않게
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  /*
    자동으로 넘긴다. 영상은 시간으로 끊지 않는다 — 재생이 끝나면(onEnded) 넘어간다.
    타이머로 자르면 가족이 남긴 영상이 4.8초에서 잘려 나간다.
  */
  useEffect(() => {
    if (!playing || !current || current.media_type === 'video') return

    const timer = window.setTimeout(() => {
      if (index < last) setIndex(index + 1)
      else setPlaying(false)
    }, SLIDE_MS)

    return () => window.clearTimeout(timer)
  }, [playing, index, last, current])

  const memories: MemoryEntry[] = [
    ...(detail?.author_memory ? [detail.author_memory] : []),
    ...(detail?.contributions ?? []),
  ]
  const polishedShown = memories.some((m) => m.polished && m.polished !== m.content)
  const config = detail ? STATE_CONFIG[detail.state] ?? STATE_CONFIG.alone : null

  return (
    <div
      /* 어두운 면에서는 와인색 강조색이 보이지 않는다 — 디자인 체계가 정한
         방법대로 data-theme으로 갈아 끼운다 (index.css) */
      data-theme="dark"
      className="fixed inset-0 z-[70] flex flex-col"
      style={{ background: 'rgba(14,13,11,0.94)' }}
      role="dialog"
      aria-modal="true"
      aria-label={detail ? `${detail.title} 크게 보기` : '추억 크게 보기'}
    >
      <div
        className="flex shrink-0 items-center justify-between gap-4 px-5 py-3"
        style={{ borderBottom: '1px solid rgba(255,255,255,0.12)' }}
      >
        <span className="min-w-0 truncate text-[13px] text-white/85">
          {detail?.title || (loading ? '불러오는 중…' : '추억')}
          {detail?.date_start && (
            <span className="t-mono ml-2.5 text-[12px] text-white/45">{detail.date_start}</span>
          )}
        </span>
        <button
          onClick={onClose}
          className="flex shrink-0 cursor-pointer items-center gap-1 border-0 bg-transparent
                     text-[13px] text-white/70 hover:text-white"
          aria-label="닫기"
        >
          <X size={16} strokeWidth={2} />
          닫기
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* 사진 — 이 화면에서 가장 큰 것 */}
        <div className="flex min-h-0 flex-1 flex-col">
          <div
            className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4"
            onTouchStart={(e) => {
              touchStartX.current = e.touches[0]?.clientX ?? null
            }}
            onTouchEnd={(e) => {
              const startX = touchStartX.current
              touchStartX.current = null
              if (startX == null) return
              const delta = (e.changedTouches[0]?.clientX ?? startX) - startX
              // 손가락이 조금 흔들린 것과 넘긴 것을 가른다
              if (Math.abs(delta) < 48) return
              setPlaying(false)
              go(delta < 0 ? index + 1 : index - 1)
            }}
          >
            {loading && <p className="t-body-sm m-0 text-white/55">불러오는 중…</p>}

            {!loading && error && (
              <p className="t-body-sm m-0 max-w-[30em] text-center text-white/70">{error}</p>
            )}

            {!loading && !error && visuals.length === 0 && (
              <div className="text-center">
                <p className="t-body m-0 text-white/70">이 추억에는 아직 사진이 없습니다.</p>
                <Link
                  to="/collect"
                  className="btn-outline mt-4 inline-block no-underline hover:no-underline"
                >
                  사진 올리기
                </Link>
              </div>
            )}

            {current &&
              (current.media_type === 'video' ? (
                <video
                  key={current.id}
                  src={mediaUrl(current.file_path)}
                  poster={current.thumbnail_path ? mediaUrl(current.thumbnail_path) : undefined}
                  className="max-h-full max-w-full"
                  controls
                  playsInline
                  autoPlay={playing}
                  /* 영상은 끝까지 재생하고 다음으로 넘어간다 */
                  onEnded={() => {
                    if (!playing) return
                    if (index < last) setIndex(index + 1)
                    else setPlaying(false)
                  }}
                />
              ) : (
                <img
                  /* playing이 key에 들어가야 재생을 눌렀을 때 움직임이 처음부터 걸린다 */
                  key={current.id + (playing ? '-play' : '')}
                  src={mediaUrl(current.file_path)}
                  alt=""
                  className={`max-h-full max-w-full object-contain ${
                    playing ? MOTIONS[index % MOTIONS.length] : ''
                  }`}
                />
              ))}

            {index > 0 && (
              <button
                onClick={() => {
                  setPlaying(false)
                  go(index - 1)
                }}
                className="absolute left-3 flex h-11 w-11 cursor-pointer items-center justify-center
                           rounded-full border-0 text-white"
                style={{ background: 'rgba(14,13,11,0.55)' }}
                aria-label="이전 사진"
              >
                <ChevronLeft size={22} strokeWidth={2} />
              </button>
            )}
            {index < last && (
              <button
                onClick={() => {
                  setPlaying(false)
                  go(index + 1)
                }}
                className="absolute right-3 flex h-11 w-11 cursor-pointer items-center justify-center
                           rounded-full border-0 text-white"
                style={{ background: 'rgba(14,13,11,0.55)' }}
                aria-label="다음 사진"
              >
                <ChevronRight size={22} strokeWidth={2} />
              </button>
            )}
          </div>

          {/* 재생 · 필름 — 몇 장 중 몇 번째인지가 늘 읽혀야 한다 */}
          {visuals.length > 0 && (
            <div
              className="shrink-0 px-5 py-3"
              style={{ borderTop: '1px solid rgba(255,255,255,0.12)' }}
            >
              <div className="flex items-center gap-4">
                <button
                  onClick={() => {
                    // 마지막 장에서 다시 누르면 처음부터
                    if (index >= last) setIndex(0)
                    setPlaying((p) => !p)
                  }}
                  aria-label={playing ? '일시정지' : '재생'}
                  className="h-[34px] w-[34px] shrink-0 cursor-pointer rounded-full border-0 text-[11px]"
                  style={{ background: 'var(--accent)', color: 'var(--accent-fg)' }}
                >
                  {playing ? '■' : '▶'}
                </button>

                <div className="min-w-0 flex-1">
                  <div className="h-0.5" style={{ background: 'rgba(255,255,255,0.16)' }}>
                    <div
                      className="h-0.5 transition-[width] duration-200 ease-out"
                      style={{
                        background: 'var(--accent)',
                        width: ((index + 1) / visuals.length) * 100 + '%',
                      }}
                    />
                  </div>
                  <div className="mt-2 flex justify-between">
                    <span className="t-mono text-[11px] text-white/50">
                      사진 {index + 1} / {visuals.length}
                    </span>
                    <span className="t-mono text-[11px] text-white/50">
                      {playing ? '자동으로 넘어갑니다' : '방향키로 넘길 수 있습니다'}
                    </span>
                  </div>
                </div>
              </div>

              {visuals.length > 1 && (
                <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1">
                  {visuals.map((m, i) => (
                    <button
                      key={m.id}
                      onClick={() => {
                        setPlaying(false)
                        setIndex(i)
                      }}
                      className="h-12 w-[68px] shrink-0 cursor-pointer overflow-hidden rounded border-0 p-0"
                      style={{
                        outline:
                          i === index ? '2px solid var(--accent)' : '1px solid rgba(255,255,255,0.16)',
                        outlineOffset: i === index ? '-2px' : '-1px',
                        opacity: i === index ? 1 : 0.55,
                      }}
                      aria-label={`${i + 1}번째 사진`}
                      aria-current={i === index}
                    >
                      <img
                        src={mediaUrl(m.thumbnail_path || m.file_path)}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 그날에 대해 남은 것 */}
        <aside
          className="w-full shrink-0 overflow-y-auto px-6 py-5 lg:w-[380px]"
          style={{
            borderTop: '1px solid rgba(255,255,255,0.12)',
            background: 'rgba(255,255,255,0.03)',
          }}
        >
          {detail && (
            <>
              <div className="flex items-start justify-between gap-3">
                <p className="m-0 text-[17px] font-semibold text-white/90">{detail.title}</p>
                {config && (
                  <span
                    className="pill shrink-0"
                    style={{ background: config.bg, color: config.fg }}
                  >
                    {config.label}
                  </span>
                )}
              </div>

              <dl className="m-0 mt-4 flex flex-col gap-2.5">
                <Row label="날짜">{detail.date_start || '날짜 미상'}</Row>
                <Row label="장소">{detail.place?.name || '기록 없음'}</Row>
                <Row label="함께한 사람">
                  {detail.participants.length > 0
                    ? detail.participants.map((p) => p.name).join(' · ')
                    : '아직 기록되지 않았습니다'}
                </Row>
                <Row label="사진 · 영상">{visuals.length}개</Row>
                {detail.author?.name && <Row label="처음 남긴 사람">{detail.author.name}</Row>}
              </dl>

              {detail.description && (
                <p className="m-0 mt-4 text-[13px] leading-relaxed text-white/65">
                  {detail.description}
                </p>
              )}

              {detail.echo_count > 0 && (
                <p className="m-0 mt-4 flex items-center gap-1.5 text-[12px] text-white/60">
                  <Heart size={13} fill="currentColor" />
                  {detail.echoed_by.length > 0
                    ? `${detail.echoed_by.map((p) => p.name).join(' · ')}도 기억한다고 남겼습니다`
                    : `${detail.echo_count}명이 기억한다고 남겼습니다`}
                </p>
              )}

              {/* 가족이 남긴 문장. AI가 쓴 것보다 먼저 온다 */}
              <section className="mt-6">
                <p className="t-eyebrow m-0 mb-2.5 text-white/45">
                  가족의 기억 {memories.length > 0 && memories.length}
                </p>
                {memories.length === 0 ? (
                  <p className="m-0 text-[13px] text-white/45">
                    아직 이 추억에 남은 기억 문장이 없습니다.
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {memories.map((memory) => (
                      <div
                        key={memory.id}
                        className="rounded px-4 py-3"
                        style={{ background: 'rgba(255,255,255,0.05)' }}
                      >
                        <p className="m-0 mb-1 text-[11px] text-white/45">
                          {memory.contributor?.name || '가족'}
                          {memory.contributor?.relation ? ` · ${memory.contributor.relation}` : ''}
                          {memory.differs && ' · 조금 다르게 기억'}
                        </p>
                        <p className="m-0 whitespace-pre-wrap text-[13px] leading-relaxed text-white/80">
                          {memory.polished || memory.content}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
                {polishedShown && (
                  <p className="m-0 mt-2 text-[11px] text-white/40">
                    AI가 읽기 좋게 정리한 문장입니다. 원문은 추억 상세에서 볼 수 있습니다.
                  </p>
                )}
              </section>

              {/* 가족이 실제로 남긴 목소리 */}
              {audios.length > 0 && (
                <section className="mt-6">
                  <p className="t-eyebrow m-0 mb-2.5 text-white/45">그날의 목소리</p>
                  <div className="flex flex-col gap-2">
                    {audios.map((item) => (
                      <AudioClip
                        key={item.id}
                        dark
                        compact
                        clip={{
                          id: item.id,
                          file_path: item.file_path,
                          event_id: detail.id,
                          event_title: detail.title,
                          speaker_id: item.speaker_id,
                          duration_sec: item.duration_sec || 0,
                          transcript: item.transcript,
                          waveform: item.waveform || [],
                          question: item.question,
                        }}
                      />
                    ))}
                  </div>
                </section>
              )}

              {detail.varied && (
                <p className="m-0 mt-6 text-[12px] leading-relaxed text-white/55">
                  가족들이 조금 다르게 기억하고 있습니다. 어느 쪽도 정답으로 정하지 않고 그대로
                  보존합니다.
                </p>
              )}

              <div className="mt-7 flex flex-wrap gap-1.5">
                <Link
                  to={`/memory/${detail.id}`}
                  className="btn-outline no-underline hover:no-underline"
                >
                  추억 상세 · 내 기억 더하기
                </Link>
                {visuals.length > 0 && (
                  <Link
                    to={`/film?event=${detail.id}`}
                    className="flex items-center gap-1 rounded border border-white/20 px-3.5 py-[7px]
                               text-[12px] text-white/75 no-underline transition-colors duration-150
                               ease-out hover:bg-white/10 hover:no-underline"
                  >
                    <Clapperboard size={12} strokeWidth={2} />
                    한 편의 이야기로 보기
                  </Link>
                )}
              </div>
            </>
          )}

          {!detail && !loading && (
            <p className="m-0 text-[13px] text-white/60">{error || '추억을 찾을 수 없습니다.'}</p>
          )}
        </aside>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="t-mono w-[76px] shrink-0 text-[11px] text-white/40">{label}</dt>
      <dd className="m-0 min-w-0 flex-1 text-[13px] text-white/80">{children}</dd>
    </div>
  )
}
