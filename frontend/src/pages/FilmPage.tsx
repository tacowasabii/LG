/**
 * Memory Film (기획안 02장 CORE · STORY)
 *
 * 하나의 사건에 연결된 사진·영상·음성을 30~60초 이야기로 묶는다.
 * 기획안의 진정성 원칙에 따라 장면마다 원본 출처와 적용된 AI 효과를 드러낸다.
 *
 * AI 효과 표시에 경고색을 쓰지 않는다. AI가 손을 댄 것은 잘못이 아니라 사실이고,
 * 사실은 조용히 적으면 된다 — 보라색 알약은 "여기까지가 원본, 여기부터가 생성"의
 * 경계를 알려주는 표지판이지 경보가 아니다. 효과가 없는 장면은 teal로 "원본
 * 그대로"라고 밝혀, 둘 중 어느 쪽인지 화면에서 늘 읽히게 한다.
 *
 * 장면 구성은 POST /api/film 이 그래프에서 조립한다. 길이와 대상 세대를 넘기면
 * 서버가 장면을 자르고 내레이션을 확인된 기록 안에서만 쓴다.
 *
 * 사진에 클립(motion_url)이 있으면 그것을 재생하고, 없으면 원본 사진에 CSS
 * 카메라 움직임을 건다. 어느 쪽인지는 서버가 정하고 AI 라벨에 그대로 적힌다.
 *
 * 남은 교체 지점: 미리보기 진행바 -> 장면 전체를 이어 붙인 영상 플레이어
 */

import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Anniversary,
  FilmStoryboard,
  composeFilm,
  getAnniversaries,
  mediaUrl,
} from '../lib/api'
import { AUDIENCE_DESC, AUDIENCE_LABEL, Audience, FilmLength } from '../lib/filmOptions'
import { useEvents, useVoiceClips } from '../lib/useGraphData'
import { usePrefersReducedMotion } from '../lib/reducedMotion'
import { Page, PageHeader } from '../components/Page'
import AudioClip from '../components/AudioClip'
import RichText from '../components/RichText'

const LENGTHS: FilmLength[] = [30, 45, 60]
const AUDIENCES: Audience[] = ['child', 'adult', 'elder']

/**
 * 서버가 고른 움직임을 CSS 클래스로 옮긴다.
 *
 * 무엇을 걸지 화면이 정하지 않는다. 예전에는 여기서 장면 순서로 골랐는데
 * 서버가 라벨을 붙이는 순서와 달라서, 화면에 적힌 효과와 실제로 걸린 효과가
 * 네 경우 모두 어긋나 있었다 (backend/services/film_composer.py CAMERA_MOTIONS).
 */
const MOTION_CLASS: Record<string, string> = {
  'zoom-in': 'motion-zoom-in',
  'pan-left': 'motion-pan-left',
  'zoom-out': 'motion-zoom-out',
  'pan-right': 'motion-pan-right',
}

export default function FilmPage() {
  const { events } = useEvents()
  const { clips } = useVoiceClips()
  const [searchParams] = useSearchParams()
  /*
    ?event=E01로 들어오면 그 사건으로 시작한다. 타임라인·지도에서 사건을 크게
    보다가 "한 편의 이야기로 보기"를 누르는 길이다 — 여기서 사건을 다시 고르게
    하면 방금 보던 사건을 이름으로 찾아야 한다.

    들어온 뒤 칩으로 다른 사건을 고르면 주소는 그대로 둔다. 이 값은 시작점일
    뿐이고, 주소를 따라 고쳐 쓰면 뒤로 가기가 사건 선택을 되짚는 기록이 된다.
  */
  const [eventId, setEventId] = useState<string | null>(searchParams.get('event'))
  const [length, setLength] = useState<FilmLength>(45)
  const [audience, setAudience] = useState<Audience>('adult')
  const [board, setBoard] = useState<FilmStoryboard | null>(null)
  const [composing, setComposing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [anniversaries, setAnniversaries] = useState<Anniversary[]>([])
  const [playing, setPlaying] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const reducedMotion = usePrefersReducedMotion()

  // 사진이 가장 많은 사건에서 시작한다 (이야기가 될 자료가 있는 쪽)
  useEffect(() => {
    if (eventId || events.length === 0) return
    const richest = [...events].sort((a, b) => b.media_count - a.media_count)[0]
    setEventId(richest.id)
  }, [events, eventId])

  useEffect(() => {
    getAnniversaries().then(setAnniversaries).catch(console.error)
  }, [])

  // 사건·길이·대상이 바뀌면 서버가 다시 구성한다
  useEffect(() => {
    if (!eventId) return

    let cancelled = false
    setComposing(true)
    setError(null)
    setPlaying(false)
    setElapsed(0)

    composeFilm(eventId, length, audience)
      .then((result) => {
        if (!cancelled) setBoard(result)
      })
      .catch((e) => {
        console.error(e)
        if (!cancelled) {
          setBoard(null)
          setError('이 사건으로는 아직 이야기를 만들 수 없습니다. 사진이나 영상을 먼저 연결해주세요.')
        }
      })
      .finally(() => {
        if (!cancelled) setComposing(false)
      })

    return () => {
      cancelled = true
    }
  }, [eventId, length, audience])

  const scenes = board?.scenes ?? []
  const totalSec = board?.total_sec ?? 0

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 0.25
        if (next >= totalSec) {
          setPlaying(false)
          return totalSec
        }
        return next
      })
    }, 250)
    return () => window.clearInterval(timer)
  }, [playing, totalSec])

  // 현재 재생 위치가 몇 번째 장면인지
  let acc = 0
  let currentIndex = 0
  for (let i = 0; i < scenes.length; i++) {
    acc += scenes[i].duration_sec
    if (elapsed < acc) {
      currentIndex = i
      break
    }
    currentIndex = i
  }
  const currentScene = scenes[currentIndex]
  const voice = currentScene?.voice_id
    ? clips.find((c) => c.id === currentScene.voice_id)
    : undefined

  return (
    <Page width={1000}>
      <PageHeader
        eyebrow="Memory Film"
        title="한 사건, 한 편의 이야기"
        lead="사진·영상·음성을 짧은 이야기로 묶습니다. 장면마다 원본 출처와 적용된 AI 효과를 함께 남깁니다."
      />

      <div
        className="mt-9 py-5"
        style={{
          borderTop: '1px solid var(--border)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <p className="t-eyebrow m-0 mb-2.5 text-ink-300">어떤 사건으로 만들까요</p>
        <div className="flex flex-wrap gap-1.5">
          {events.map((event) => {
            const ready = event.media_count > 0
            return (
              <button
                key={event.id}
                disabled={!ready}
                onClick={() => setEventId(event.id)}
                className={`chip ${eventId === event.id ? 'chip-on' : ''}
                            ${ready ? '' : 'cursor-not-allowed text-ink-200 hover:bg-transparent'}`}
                title={ready ? undefined : '장면을 만들 자료가 아직 부족합니다'}
              >
                {event.title.replace(/^\d{4}\s*/, '')}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-8">
        <div>
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">길이</p>
          <div className="flex gap-1.5">
            {LENGTHS.map((l) => (
              <button
                key={l}
                onClick={() => setLength(l)}
                className={`tab ${length === l ? 'tab-on' : ''}`}
              >
                {l}초
              </button>
            ))}
          </div>
          <p className="t-caption mt-2.5">
            선택한 길이에 맞춰 장면 {scenes.length}개 · 실제 {totalSec}초
          </p>
        </div>

        <div>
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">누구에게 보여줄까요</p>
          <div className="flex gap-1.5">
            {AUDIENCES.map((a) => (
              <button
                key={a}
                onClick={() => setAudience(a)}
                className={`tab ${audience === a ? 'tab-on' : ''}`}
              >
                {AUDIENCE_LABEL[a]}
              </button>
            ))}
          </div>
          <p className="t-caption mt-2.5">{AUDIENCE_DESC[audience]}</p>
        </div>
      </div>

      {composing && (
        <p className="t-body-sm mt-8 text-ink-300">이야기를 구성하고 있어요…</p>
      )}

      {error && !composing && (
        <p className="t-body-sm mt-8" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {board && currentScene && (
        <>
          <div className="surface mt-8 overflow-hidden">
            <div
              className="relative aspect-video overflow-hidden"
              style={{ background: 'var(--ink-900)' }}
            >
              {currentScene.motion_url && !reducedMotion ? (
                /* 미리 만들어 둔 미세 모션 클립. 실패해도 poster(원본 썸네일)가
                   남아 화면이 비지 않는다. */
                <video
                  key={currentScene.media_id}
                  src={mediaUrl(currentScene.motion_url)}
                  poster={mediaUrl(currentScene.thumb)}
                  className="h-full w-full object-cover"
                  autoPlay
                  loop
                  muted
                  playsInline
                />
              ) : (
                <img
                  key={currentScene.media_id}
                  src={mediaUrl(currentScene.thumb)}
                  alt=""
                  className={`h-full w-full object-cover ${
                    (currentScene.motion && MOTION_CLASS[currentScene.motion]) || ''
                  }`}
                  /* index.css의 9초 고정을 장면 길이로 덮는다. 세대별 배속과
                     목소리 길이 때문에 장면은 6~11초로 갈리는데, 애니메이션이
                     9초로 굳어 있으면 짧은 장면은 잘리고 긴 장면은 끝에서
                     멈춰 선다 — 움직임이 있다고 적어 둔 동안 정지 화면이다. */
                  style={{ animationDuration: currentScene.duration_sec + 's' }}
                />
              )}
              <div
                className="absolute inset-0"
                style={{
                  background:
                    'linear-gradient(to top, rgba(14,13,11,0.82) 0%, rgba(14,13,11,0.08) 55%, rgba(14,13,11,0.32) 100%)',
                }}
              />

              {/* AI 라벨 — 생성 요소를 숨기지 않는다.
                  움직임을 끈 사용자에게는 걸리지 않은 효과를 적지 않는다.
                  화면은 멈춰 있는데 "AI 생성 미세 움직임"이라고 쓰면, 적용된 것을
                  드러낸다는 원칙이 반대로 뒤집힌다. */}
              <span
                className="absolute right-4 top-4 rounded-full px-3 py-[5px] text-[11px]"
                style={{ background: 'rgba(14,13,11,0.62)', color: 'var(--paper)' }}
              >
                {reducedMotion
                  ? currentScene.ai_effects.length > 0
                    ? '원본 그대로 · 움직임 끔'
                    : '원본 그대로'
                  : currentScene.ai_effects.length > 0
                    ? 'AI 효과 · ' + currentScene.ai_effects.join(' · ')
                    : '원본 그대로'}
              </span>

              <div className="absolute inset-x-0 bottom-0 p-7">
                <p
                  className="m-0 text-[22px] font-semibold tracking-[-0.01em]"
                  style={{ color: 'var(--paper)' }}
                >
                  {currentScene.subtitle}
                </p>
                <p
                  className="m-0 mt-1.5 text-xs"
                  style={{ color: 'rgba(250,250,247,0.62)' }}
                >
                  {currentScene.source_label}
                </p>
              </div>
            </div>

            <div className="px-6 py-5">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => {
                    if (elapsed >= totalSec) setElapsed(0)
                    setPlaying((p) => !p)
                  }}
                  aria-label={playing ? '일시정지' : '재생'}
                  className="h-[38px] w-[38px] shrink-0 cursor-pointer rounded-full border-0 text-[11px]"
                  style={{ background: 'var(--accent)', color: 'var(--accent-fg)' }}
                >
                  {playing ? '■' : '▶'}
                </button>

                <div className="flex-1">
                  <div className="h-0.5" style={{ background: 'var(--ink-100)' }}>
                    <div
                      className="h-0.5"
                      style={{
                        background: 'var(--accent)',
                        width: (totalSec ? (elapsed / totalSec) * 100 : 0) + '%',
                      }}
                    />
                  </div>
                  <div className="mt-2 flex justify-between">
                    <span className="t-mono text-[11px] text-ink-400">
                      장면 {currentIndex + 1} / {scenes.length}
                    </span>
                    <span className="t-mono text-[11px] text-ink-400">
                      {Math.floor(elapsed)}초 / {totalSec}초
                    </span>
                  </div>
                </div>
              </div>

              {voice && (
                <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
                  <p className="t-caption m-0 mb-2">이 장면에 함께 재생되는 실제 음성</p>
                  <AudioClip clip={voice} compact />
                </div>
              )}
            </div>
          </div>

          <div className="mt-8">
            <p className="m-0 text-[19px] font-semibold text-ink-900">
              {board.title}
              <span className="t-caption ml-2.5 text-ink-300">{board.subtitle}</span>
            </p>
            <p className="t-body mt-3 max-w-[45em]">
              <RichText text={board.narration} />
            </p>
            {board.omitted_scenes > 0 && (
              <p className="t-caption m-0 mt-2">
                {board.requested_sec}초에 맞추려고 장면 {board.omitted_scenes}개를 뺐습니다. 더 긴
                길이를 고르면 모두 들어갑니다.
              </p>
            )}
            <p className="t-caption mt-3">
              내레이션은 확인된 기록 안에서만 생성됩니다. 원본에 없는 발화·행동은 만들지
              않습니다.
            </p>
          </div>

          <div className="mt-9">
            <p className="t-eyebrow m-0 mb-1">장면 구성</p>
            <div className="rule-strong mt-3">
              {scenes.map((scene, i) => (
                <div
                  key={scene.media_id}
                  className="flex gap-5 px-1 py-5"
                  style={{
                    borderBottom: '1px solid var(--border)',
                    borderLeft: `2px solid ${i === currentIndex ? 'var(--accent)' : 'transparent'}`,
                  }}
                >
                  <img
                    src={mediaUrl(scene.thumb)}
                    alt=""
                    className="h-20 w-28 shrink-0 rounded bg-ink-50 object-cover"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="t-mono text-[11px] text-ink-300">
                        {i + 1}번째 · {scene.duration_sec}초
                      </span>
                      {scene.voice_id && (
                        <span
                          className="pill font-normal"
                          style={{
                            background: 'var(--accent-soft)',
                            color: 'var(--accent-ink)',
                          }}
                        >
                          실제 음성
                        </span>
                      )}
                    </div>
                    <p className="m-0 mt-1.5 text-[15px] font-semibold text-ink-900">
                      {scene.subtitle}
                    </p>
                    <p className="t-body-sm m-0 mt-1 text-ink-400">{scene.note}</p>
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      <span className="pill bg-ink-50 px-[9px] font-normal text-ink-500">
                        {scene.source_label}
                      </span>
                      {!reducedMotion &&
                        scene.ai_effects.map((fx) => (
                          <span
                            key={fx}
                            className="pill px-[9px] font-normal"
                            style={{
                              background: 'var(--warning-soft)',
                              color: 'var(--warning-ink)',
                            }}
                          >
                            AI · {fx}
                          </span>
                        ))}
                      {reducedMotion && scene.ai_effects.length > 0 && (
                        <span
                          className="pill px-[9px] font-normal"
                          style={{
                            background: 'var(--positive-soft)',
                            color: 'var(--positive-ink)',
                          }}
                        >
                          원본 그대로 · 움직임 끔
                        </span>
                      )}
                      {scene.ai_effects.length === 0 && (
                        <span
                          className="pill px-[9px] font-normal"
                          style={{
                            background: 'var(--positive-soft)',
                            color: 'var(--positive-ink)',
                          }}
                        >
                          원본 그대로
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="mt-9">
        <p className="t-eyebrow m-0 mb-1">다가오는 기념일</p>
        <p className="t-caption m-0 mb-3">
          기념일이 되면 TV 대기화면에서 그날의 Film이 먼저 뜹니다.
        </p>
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {anniversaries.map((a) => (
            <div
              key={a.date}
              className="flex items-center gap-5 px-1 py-4"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <span className="t-mono w-[88px] shrink-0 text-xs text-accent-ink">{a.date}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold text-ink-900">{a.label}</span>
                <span className="t-caption mt-0.5 block">{a.reason}</span>
              </span>
              <span className="t-mono whitespace-nowrap text-[11px] text-ink-300">
                {a.days_left}일 남음
              </span>
              {events.find((e) => e.id === a.event_id && e.media_count > 0) ? (
                <button onClick={() => setEventId(a.event_id)} className="btn-quiet">
                  미리 보기
                </button>
              ) : (
                <Link to="/interview" className="btn-outline no-underline hover:no-underline">
                  자료 채우기
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>
    </Page>
  )
}
