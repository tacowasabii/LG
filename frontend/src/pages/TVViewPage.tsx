import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createTVJourney, TVJourney, mediaUrl } from '../lib/api'
import { useGridFocus, useRemote, RemoteKey } from '../lib/remote'
import RichText from '../components/RichText'
import AudioClip from '../components/AudioClip'
import RemoteHint from '../components/RemoteHint'
import StatusPill, { STATE_CONFIG } from '../components/StatusPill'
import { useEvents, useVoiceClips } from '../lib/useGraphData'
import { usePrefersReducedMotion } from '../lib/reducedMotion'
import { ambientSlides, buildLocalJourney, tvPresets } from '../lib/tvCuration'

/**
 * LG TV — Memory Live / Journey (기획안 06장 LG PRODUCT LINKAGE)
 *
 * 3m 거리, 리모컨 6버튼(◀▶▲▼ · OK · BACK)으로만 도는 화면이다. 그래서
 * 웹 화면과 설계 규칙이 다르다.
 *
 *  - 검색창이 없다. TV에는 키보드가 없어서 텍스트 입력은 조작이 아니라 벌이다.
 *    대신 대기화면이 먼저 오늘의 기억을 띄우고, 나머지는 프리셋 6개로만 들어간다.
 *  - 화면은 3개뿐이다: 대기화면 → 재생 → 근거. 그래프·업로드·공개설정은
 *    TV에 올리지 않는다 (그건 모바일·웹의 몫이다).
 *  - 재생 화면에는 누를 수 있는 위젯을 두지 않는다. 포커스가 갈 곳이 없으면
 *    사용자는 화면만 본다. 만지고 싶은 것(음성 재생)은 근거 화면에 모았다.
 *
 * 색은 순검정이 아니라 잉크 900을 쓴다. 사진의 어두운 부분이 배경에 녹아
 * 사라지지 않고, 흰색 대신 종이색(#FAFAF7)을 얹으면 거실 조명 아래에서 글자가
 * 덜 시리다. 강조색은 TVLayout의 data-theme="dark"가 밝은 베리색으로 갈아 끼운다.
 *
 * 기획안 진정성 원칙은 그대로 지킨다.
 *  - 카메라 움직임은 패닝·줌만 쓴다 (index.css의 motion-* 유틸리티)
 *  - 미리 만들어 둔 미세 모션 클립이 있는 사진은 그것을 재생한다. 파도·불꽃처럼
 *    환경만 움직이고 인물의 행동은 만들지 않는다 (scripts/build_motion_covers.py).
 *    없던 픽셀이 생긴 것이므로 라벨을 카메라 움직임과 나눠 적는다
 *  - 날짜·장소·사건명을 자막으로 항상 띄운다
 *  - 사건에 연결된 실제 가족 음성의 전사문을 자막으로 함께 보여준다
 *  - OK 버튼으로 원본·촬영 시점·출처를 열어 볼 수 있다
 *  - 움직임이 적용된 장면에는 AI 라벨을 숨기지 않고 표시한다
 *
 * 실기능 개발 시 교체 지점:
 *   대기화면 후보  -> GET /api/tv/ambient ("N년 전 오늘" 계산을 서버로 옮길 자리)
 *   프리셋        -> GET /api/tv/presets
 *   장소·상태     -> GET /api/graph/events 에서 받아 자막에 쓴다 (완료)
 *   음성          -> 사건에 연결된 audio 미디어를 API로 가져오기
 *   깊이 기반 시차 -> 2.5D 렌더 파이프라인
 */

type Screen = 'ambient' | 'menu' | 'loading' | 'play'

/** 슬라이드 순서에 따라 돌려 쓰는 움직임 */
const MOTIONS = ['motion-zoom-in', 'motion-pan-left', 'motion-zoom-out', 'motion-pan-right']

/** index.css의 kenburns 애니메이션 길이와 맞춰 둔다 */
const SLIDE_MS = 9000
const AMBIENT_ROTATE_MS = 12000
const PRESET_COLS = 3

/** 사진 위에 자막을 얹으려면 아래가 어두워야 한다 */
const SCRIM_STRONG =
  'linear-gradient(to top, rgba(14,13,11,0.9) 0%, rgba(14,13,11,0.25) 55%, rgba(14,13,11,0.55) 100%)'
const SCRIM_PLAY =
  'linear-gradient(to top, rgba(14,13,11,0.88) 0%, rgba(14,13,11,0.2) 55%, rgba(14,13,11,0.5) 100%)'

/**
 * 서버 캡션은 "1998-08-13 - 1998 부산 가족여행"처럼 날짜와 사건명을 이어 붙인
 * 문자열이다(backend/services/tv_curator.py의 _generate_caption). 그 둘은 이미
 * 위 자막에 있어서 그대로 쓰면 같은 말이 두 번 나오고, 자막의 "1998. 08. 13"과
 * 캡션의 "1998-08-13"이 나란히 붙어 표기까지 어긋난다. 그래서 캡션에서 날짜와
 * 사건명을 덜어내고, 남는 말이 있을 때만 한 줄 더 쓴다.
 */
function captionRemainder(
  caption: string,
  eventTitle?: string | null,
  date?: string | null,
): string {
  let rest = caption
  if (date) rest = rest.split(date.slice(0, 10)).join('')
  if (eventTitle) rest = rest.split(eventTitle).join('')
  return rest.replace(/^[\s·\-–—]+/, '').replace(/[\s·\-–—]+$/, '').trim()
}

/** 사진 위에 올리는 작은 상태 알약 — AI 라벨, 음성 개수, 일시정지 */
function OverlayPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="tv-caption rounded-full bg-ink-900/55 px-[0.9vw] py-[0.35vh] text-paper/90 backdrop-blur">
      {children}
    </span>
  )
}

/*
 * 시계 · 일시정지 · 나가기는 화면이 바뀌어도 같은 자리(오른쪽 위)에 있다.
 * 근거 오버레이(z-30)보다 위에 두어, 근거를 보다가도 나갈 길이 보이게 한다.
 *
 * 시계는 대기화면에만 띄운다. 재생 중에는 사진과 자막이 화면의 주인이고,
 * 시간은 TV가 대기 상태일 때만 알고 싶은 정보다.
 */
function TopBar({
  clock,
  paused = false,
  onExit,
}: {
  /** 대기화면에서만 넘어온다. 없으면 시계를 그리지 않는다 */
  clock?: string
  paused?: boolean
  onExit: () => void
}) {
  return (
    <div className="tv-safe absolute right-0 top-0 z-40 flex items-center gap-[1.2vw]">
      {clock && (
        <span className="t-mono tv-heading font-light tabular-nums text-paper/80">{clock}</span>
      )}
      {paused && (
        <span className="tv-caption whitespace-nowrap rounded-full bg-ink-900/55 px-[0.9vw] py-[0.35vh] text-paper/85">
          일시정지
        </span>
      )}
      <button
        onClick={onExit}
        className="tv-caption cursor-pointer whitespace-nowrap rounded-full border
                   border-paper/[0.28] bg-ink-900/50 px-[1.1vw] py-[0.5vh] text-paper/85
                   transition-colors hover:bg-paper/[0.14] hover:text-paper"
      >
        ← 앱으로 돌아가기
      </button>
    </div>
  )
}

export default function TVViewPage() {
  const navigate = useNavigate()
  // 자막의 장소·확인 상태와 슬라이드에 붙는 목소리는 그래프에서 온다
  const { events, eventById } = useEvents()
  const { clips: allClips, clipsForEvent } = useVoiceClips()
  // 영상 재생은 CSS로 멈출 수 없어서 여기서 판단한다 (lib/reducedMotion.ts)
  const reducedMotion = usePrefersReducedMotion()

  const [screen, setScreen] = useState<Screen>('ambient')
  const [journey, setJourney] = useState<TVJourney | null>(null)
  const [slideIndex, setSlideIndex] = useState(0)
  const [showEvidence, setShowEvidence] = useState(false)
  const [autoPlay, setAutoPlay] = useState(true)
  const [ambientIndex, setAmbientIndex] = useState(0)
  const [now, setNow] = useState(() => new Date())
  const evidenceRef = useRef<HTMLDivElement>(null)

  const ambient = useMemo(() => ambientSlides(events, allClips), [events, allClips])
  const presets = useMemo(() => tvPresets(events, allClips), [events, allClips])
  const preset = useGridFocus(presets.length, PRESET_COLS)

  const ambientSlide = ambient[ambientIndex % ambient.length]

  // 대기화면 시계 — TV가 꺼져 있는 시간에 걸려 있는 화면이라 시간이 보여야 한다
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 20000)
    return () => window.clearInterval(timer)
  }, [])

  // 대기화면 자동 전환
  useEffect(() => {
    if (screen !== 'ambient') return
    const timer = window.setInterval(
      () => setAmbientIndex((i) => (i + 1) % ambient.length),
      AMBIENT_ROTATE_MS,
    )
    return () => window.clearInterval(timer)
  }, [screen, ambient.length])

  /**
   * 재생 시작. 서버 큐레이션을 먼저 쓰고, 응답이 없거나 비면 로컬로 조립한다.
   * 대기화면에서 OK를 눌렀는데 아무 일도 안 일어나는 것이 이 화면에서 가장
   * 나쁜 실패라서 폴백을 둔다 (정적 배포·백엔드 중단 대비).
   */
  const start = useCallback(async (title: string, query: string, eventIds: string[]) => {
    setScreen('loading')
    setShowEvidence(false)

    let result: TVJourney | null = null
    try {
      const fromServer = await createTVJourney(query)
      // 타이틀 한 장만 오는 경우가 있어 실제 사진이 붙었는지까지 본다
      if (fromServer?.slides?.some((s) => s.file_path)) result = fromServer
    } catch (e) {
      console.warn('[TV] /api/tv/journey 실패 — 로컬 큐레이션으로 재생합니다', e)
    }

    setJourney(result ?? buildLocalJourney(title, eventIds, events))
    setSlideIndex(0)
    setAutoPlay(true)
    setScreen('play')
  }, [])

  const exitToAmbient = useCallback(() => {
    setScreen('ambient')
    setJourney(null)
    setShowEvidence(false)
    setAutoPlay(false)
  }, [])

  /** 앱으로 돌아가기 — 리모컨이 아니라 마우스로 볼 때 나갈 길 */
  const exitToApp = useCallback(() => navigate('/'), [navigate])

  const slideCount = journey?.slides.length ?? 0

  const goNext = useCallback(() => {
    setShowEvidence(false)
    setSlideIndex((i) => Math.min(i + 1, slideCount - 1))
  }, [slideCount])

  const goPrev = useCallback(() => {
    setShowEvidence(false)
    setSlideIndex((i) => Math.max(i - 1, 0))
  }, [])

  // 자동재생 — 마지막 장에서는 대기화면으로 돌아간다 (TV는 계속 켜져 있다)
  useEffect(() => {
    if (screen !== 'play' || !autoPlay || showEvidence || !journey) return
    const timer = window.setTimeout(() => {
      if (slideIndex >= journey.slides.length - 1) exitToAmbient()
      else setSlideIndex((i) => i + 1)
    }, SLIDE_MS)
    return () => window.clearTimeout(timer)
  }, [screen, autoPlay, showEvidence, journey, slideIndex, exitToAmbient])

  // 리모컨 — 화면마다 버튼 뜻이 다르므로 한 곳에서 갈라 준다
  useRemote(
    useCallback(
      (key: RemoteKey) => {
        if (screen === 'ambient') {
          // 후보가 없어도 ▼로 메뉴에는 갈 수 있어야 한다 (막히면 나갈 길이 없다)
          if ((key === 'ok' || key === 'playpause') && ambientSlide) {
            start(ambientSlide.event.title, ambientSlide.event.title, [ambientSlide.event.id])
          } else if (key === 'down') {
            setScreen('menu')
          } else if (key === 'right') {
            setAmbientIndex((i) => (i + 1) % ambient.length)
          } else if (key === 'left') {
            setAmbientIndex((i) => (i - 1 + ambient.length) % ambient.length)
          } else if (key === 'back') {
            exitToApp()
          }
          return
        }

        if (screen === 'menu') {
          if (key === 'back') setScreen('ambient')
          else if (key === 'ok') {
            const chosen = presets[preset.index]
            start(chosen.label, chosen.query, chosen.event_ids)
          } else preset.move(key)
          return
        }

        if (screen === 'play') {
          if (showEvidence) {
            if (key === 'ok' || key === 'back') setShowEvidence(false)
            // 근거 내용이 한 화면을 넘칠 수 있다. TV에는 스크롤 조작이 없으므로
            // 위·아래 버튼을 패널 스크롤에 준다. 안 그러면 아래쪽 음성은 못 본다.
            else if (key === 'up' || key === 'down') {
              const panel = evidenceRef.current
              if (panel) {
                const step = panel.clientHeight * 0.4
                panel.scrollBy({ top: key === 'down' ? step : -step, behavior: 'smooth' })
              }
            }
            return
          }
          if (key === 'right') goNext()
          else if (key === 'left') goPrev()
          else if (key === 'ok') {
            // 타이틀 장면에는 볼 원본이 없다. 여기서 OK는 "시작"이어야 한다.
            // 안내에 적힌 버튼이 아무 일도 안 하면 리모컨을 계속 눌러 보게 된다.
            if (journey?.slides[slideIndex]?.type === 'title') goNext()
            else setShowEvidence(true)
          } else if (key === 'playpause') setAutoPlay((p) => !p)
          else if (key === 'back') setScreen('menu')
        }
      },
      [
        screen,
        ambientSlide,
        ambient.length,
        presets,
        preset,
        showEvidence,
        start,
        goNext,
        goPrev,
        exitToApp,
        journey,
        slideIndex,
      ],
    ),
  )

  const clock = now.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })

  // ── 대기화면 (Today 기준 오늘의 기억) ───────────────────────────────────
  if (screen === 'ambient') {
    // 서버 큐레이션으로 바꾼 뒤 후보가 0개로 내려올 수 있다. TV가 검은 화면으로
    // 남는 것보다는 이유를 밝히고 메뉴로 갈 길을 열어 둔다.
    if (!ambientSlide) {
      return (
        <div className="relative flex h-full w-full flex-col items-center justify-center gap-[3vh]">
          <TopBar clock={clock} onExit={exitToApp} />
          <p className="tv-heading text-paper/70">보여줄 기억을 아직 찾지 못했습니다</p>
          <RemoteHint hints={[{ key: '▼', label: '기억 고르기' }]} />
        </div>
      )
    }

    const { event, media_path, reason, voice_count } = ambientSlide

    return (
      <div className="relative h-full w-full overflow-hidden">
        <div key={ambientIndex} className="tv-fade-in absolute inset-0">
          <img
            src={mediaUrl(media_path)}
            alt=""
            className="motion-zoom-in h-full w-full object-cover"
            style={{ animationDuration: AMBIENT_ROTATE_MS + 'ms' }}
          />
          <div className="absolute inset-0" style={{ background: SCRIM_STRONG }} />
        </div>

        <TopBar clock={clock} onExit={exitToApp} />

        <div className="tv-safe relative z-10 flex h-full flex-col justify-end">
          <p className="tv-heading font-normal text-paper/75">{reason}</p>
          <h1 className="tv-title mt-[1vh] text-paper">{event.title}</h1>

          <div className="mt-[1.5vh] flex flex-wrap items-center gap-x-[1.5vw] gap-y-2">
            <span className="tv-body text-paper/80">
              {(event.date_start || '').replace(/-/g, '. ')}
            </span>
            <span className="tv-body text-paper/40">·</span>
            <span className="tv-body text-paper/80">
              {event.place?.name || event.location_name || '장소 미상'}
            </span>
            <StatusPill state={event.state} size="md" />
            {voice_count > 0 && (
              <span
                className="tv-caption rounded-full border border-paper/25 bg-paper/15
                           px-[0.9vw] py-[0.3vh] text-paper"
              >
                실제 가족 음성 {voice_count}개
              </span>
            )}
          </div>

          {/* 어느 기억에 있는지 */}
          <div className="mt-[3vh] flex items-center gap-[0.6vw]">
            {ambient.map((s, i) => (
              <span
                key={s.event.id}
                className="h-[0.35vh] rounded-full transition-all duration-300"
                style={
                  i === ambientIndex
                    ? { width: '3vw', background: 'var(--paper)' }
                    : { width: '1.2vw', background: 'rgba(250,250,247,0.35)' }
                }
              />
            ))}
          </div>

          <div className="mt-[3.5vh]">
            <RemoteHint
              onPhoto
              hints={[
                { key: 'OK', label: '이 기억 이야기 들려줘' },
                { key: '▼', label: '다른 기억 고르기' },
                { key: '◀ ▶', label: '오늘의 기억 넘기기' },
                { key: 'BACK', label: '앱으로' },
              ]}
            />
          </div>
        </div>
      </div>
    )
  }

  // ── 메뉴 (프리셋 6개) ───────────────────────────────────────────────────
  if (screen === 'menu') {
    return (
      <div className="tv-safe relative flex h-full w-full flex-col">
        <TopBar onExit={exitToApp} />
        <h1 className="tv-title text-paper">무엇을 볼까요?</h1>
        <p className="tv-body mt-[1vh] text-paper/50">
          가족의 기억을 사건 · 사람 · 시기로 묶어 두었습니다
        </p>

        {/*
          TV는 스크롤이 없다. 타일 높이를 사진 비율(16:9)로 고정하면 두 번째 줄과
          하단 안내가 화면 밖으로 밀려 영원히 보이지 않는다. 그래서 남은 높이를
          줄 수로 나눠 갖고, 사진이 그 안에서 잘리도록 한다.
        */}
        <div
          className="mt-[3vh] grid min-h-0 flex-1 gap-[1.6vw]"
          style={{
            gridTemplateColumns: 'repeat(' + PRESET_COLS + ', minmax(0, 1fr))',
            gridTemplateRows:
              'repeat(' + Math.ceil(presets.length / PRESET_COLS) + ', minmax(0, 1fr))',
          }}
        >
          {presets.map((item, i) => {
            const focused = i === preset.index
            return (
              <button
                key={item.id}
                onClick={() => start(item.label, item.query, item.event_ids)}
                onMouseEnter={() => preset.setIndex(i)}
                className={`tv-focusable flex min-h-0 flex-col overflow-hidden rounded-lg
                            border border-paper/[0.12] bg-paper/[0.08] text-left
                            ${focused ? 'tv-focused bg-paper/[0.14]' : ''}`}
              >
                <div className="min-h-0 flex-1 overflow-hidden bg-paper/5">
                  {item.thumb && (
                    <img
                      src={mediaUrl(item.thumb)}
                      alt=""
                      className="h-full w-full object-cover transition-[filter] duration-200"
                      style={{ filter: `brightness(${focused ? 1 : 0.62})` }}
                    />
                  )}
                </div>
                <div className="shrink-0 px-[1.2vw] py-[1.4vh]">
                  <p className="tv-heading text-paper">{item.label}</p>
                  <p className="tv-caption mt-[0.4vh] text-paper/55">{item.sublabel}</p>
                </div>
              </button>
            )
          })}
        </div>

        <div className="mt-[3vh]">
          <RemoteHint
            hints={[
              { key: '◀ ▶ ▲ ▼', label: '고르기' },
              { key: 'OK', label: '재생' },
              { key: 'BACK', label: '대기화면' },
            ]}
          />
        </div>
      </div>
    )
  }

  // ── 불러오는 중 ─────────────────────────────────────────────────────────
  if (screen === 'loading' || !journey) {
    return (
      <div className="relative flex h-full w-full items-center justify-center">
        <TopBar onExit={exitToApp} />
        <p className="tv-heading animate-pulse text-paper/70">기억을 모아오고 있어요…</p>
      </div>
    )
  }

  // ── 재생 ────────────────────────────────────────────────────────────────
  const slide = journey.slides[slideIndex]
  const linkedEvent = slide.event_id ? eventById(slide.event_id) : undefined
  const clips = slide.event_id ? clipsForEvent(slide.event_id) : []
  const motion = MOTIONS[slideIndex % MOTIONS.length]
  const isTitle = slide.type === 'title'

  // 만들어 둔 클립이 있고 움직임을 끄지 않았을 때만 재생한다
  const playClip = Boolean(slide.motion_url) && !reducedMotion
  const motionLabel = reducedMotion
    ? '움직임 끔 · 원본 사진 그대로'
    : playClip
      ? slide.subject_preserved
        ? 'AI 생성 미세 움직임 · 인물은 원본'
        : 'AI 생성 미세 움직임'
      : 'AI 카메라 움직임 · 원본 사진 그대로'
  const extraCaption = captionRemainder(slide.caption ?? '', slide.event_title, slide.date)

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* 배경 — 만들어 둔 클립이 있으면 그것을, 없으면 사진에 카메라 움직임을.
          움직임을 끈 사용자에게는 어느 쪽도 걸지 않는다 (영상은 CSS로 못 멈춘다). */}
      {!isTitle && slide.file_path && (
        <div className="absolute inset-0 overflow-hidden">
          {playClip ? (
            <video
              key={slideIndex}
              src={mediaUrl(slide.motion_url)}
              poster={mediaUrl(slide.motion_poster || slide.file_path)}
              className="h-full w-full object-cover"
              autoPlay
              loop
              muted
              playsInline
            />
          ) : (
            <img
              key={slideIndex}
              src={mediaUrl(slide.file_path)}
              alt={slide.caption}
              className={`h-full w-full object-cover ${reducedMotion ? '' : motion}`}
              style={reducedMotion ? undefined : { animationDuration: SLIDE_MS / 1000 + 's' }}
            />
          )}
          <div className="absolute inset-0" style={{ background: SCRIM_PLAY }} />
        </div>
      )}

      <TopBar paused={!autoPlay && !showEvidence} onExit={exitToApp} />

      {/* AI 라벨 — 생성 요소를 숨기지 않는다.
          생성 클립에 "원본 사진 그대로"를 붙이면 정확히 거꾸로 말하는 것이다.
          카메라 움직임은 원본 픽셀을 옮긴 것이고, 클립은 없던 픽셀이 생긴 것이다. */}
      {!isTitle && (
        <div className="tv-safe absolute left-0 top-0 z-20 flex flex-col items-start gap-[0.8vh]">
          <OverlayPill>{motionLabel}</OverlayPill>
          {clips.length > 0 && <OverlayPill>실제 가족 음성 {clips.length}개</OverlayPill>}
        </div>
      )}

      {isTitle ? (
        <div className="tv-safe relative z-10 flex h-full flex-col items-center justify-center text-center">
          <h1 className="tv-title max-w-[80vw] text-paper">{journey.title}</h1>
          {journey.narration && (
            <p className="tv-body mt-[2.5vh] max-w-[62vw] whitespace-pre-wrap text-paper/70">
              <RichText text={journey.narration} />
            </p>
          )}
        </div>
      ) : (
        <div className="tv-safe relative z-10 flex h-full flex-col justify-end pb-[14vh]">
          {/* 자막 — 날짜 · 장소 · 사건명 */}
          <div className="flex flex-wrap items-center gap-x-[1.2vw] gap-y-2">
            {slide.date && (
              <span className="tv-body text-paper/75">
                {slide.date.slice(0, 10).replace(/-/g, '. ')}
              </span>
            )}
            {linkedEvent && (
              <>
                <span className="tv-body text-paper/35">·</span>
                <span className="tv-body text-paper/75">
                  {linkedEvent.place?.name || linkedEvent.location_name || '장소 미상'}
                </span>
              </>
            )}
            {slide.event_title && (
              <>
                <span className="tv-body text-paper/35">·</span>
                <span className="tv-body text-paper/75">{slide.event_title}</span>
              </>
            )}
            {linkedEvent && <StatusPill state={linkedEvent.state} size="md" />}
          </div>

          {extraCaption && (
            <p className="tv-heading mt-[1.2vh] max-w-[70vw] text-paper">{extraCaption}</p>
          )}

          {/*
           * 음성은 재생 화면에서 자막으로만 보여준다. 3m 거리에서 재생 버튼을
           * 리모컨으로 찾아 누르게 만들지 않는다. 듣고 만지는 것은 근거 화면에서.
           */}
          {clips.length > 0 && (
            <div className="mt-[2vh] max-w-[62vw] border-l-[0.25vw] border-paper/45 pl-[1.2vw]">
              <p className="tv-caption text-paper/60">
                {clips[0].speaker_name} · 실제 음성 {clips[0].duration_sec}초
              </p>
              <p className="tv-body mt-[0.6vh] leading-relaxed text-paper">
                {clips[0].transcript}
              </p>
            </div>
          )}
        </div>
      )}

      {/* 근거 화면 — 리모컨 OK로 여는 "이게 사실인가" 확인 지점 */}
      {showEvidence && !isTitle && (
        <div
          onClick={() => setShowEvidence(false)}
          className="tv-safe absolute inset-0 z-30 flex items-center justify-center pb-[13vh]"
          style={{ background: 'rgba(14,13,11,0.85)' }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="grid max-h-full w-full max-w-[78vw] overflow-hidden rounded-lg
                       border border-paper/[0.12] text-paper"
            style={{
              background: '#16150F',
              gridTemplateColumns: 'minmax(0,0.9fr) minmax(0,1.1fr)',
            }}
          >
            {slide.file_path && (
              <img
                src={mediaUrl(slide.file_path)}
                alt=""
                className="h-full w-full bg-paper/5 object-cover"
              />
            )}

            <div ref={evidenceRef} className="overflow-y-auto p-[2.2vw]">
              <h2 className="tv-heading">이 장면의 근거</h2>

              <dl className="mt-[2vh] flex flex-col gap-[1.2vh]">
                {[
                  ['원본 파일', slide.media_id || '알 수 없음'],
                  ['촬영 추정 시점', slide.date?.slice(0, 10).replace(/-/g, '. ') || '미상'],
                  ['장소', linkedEvent?.place?.name || linkedEvent?.location_name || '미상'],
                  ['사건', slide.event_title || '미상'],
                  ['적용된 움직임', '느린 패닝 · 줌 (원본 보존)'],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="flex justify-between gap-[2vw] border-b border-paper/[0.08] pb-[1vh]"
                  >
                    <dt className="tv-caption text-paper/50">{label}</dt>
                    <dd className="tv-caption m-0 text-right">{value}</dd>
                  </div>
                ))}
              </dl>

              {linkedEvent && (
                <div className="mt-[2vh]">
                  <StatusPill state={linkedEvent.state} size="md" />
                  <p className="tv-caption mt-[0.8vh] text-paper/55">
                    {STATE_CONFIG[linkedEvent.state].hint}
                  </p>
                </div>
              )}

              {clips.length > 0 && (
                <div className="mt-[2vh] flex flex-col gap-[1vh]">
                  {clips.map((clip) => (
                    <AudioClip key={clip.id} clip={clip} dark compact />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 하단 바 — 진행률 + 리모컨 안내. 근거 화면(z-30)보다 위에 둔다.
          안내가 오버레이에 덮이면 근거 화면에서 나갈 방법을 알 수 없다. */}
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 z-40 px-[5vw] pb-[2.5vh]">
        <div className="flex items-center gap-[1.5vw]">
          <div className="h-[0.4vh] flex-1 overflow-hidden rounded-full bg-paper/20">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                background: 'var(--accent)',
                width: ((slideIndex + 1) / journey.slides.length) * 100 + '%',
              }}
            />
          </div>
          <span className="t-mono tv-caption tabular-nums text-paper/70">
            {slideIndex + 1} / {journey.slides.length}
          </span>
        </div>

        <div className="mt-[1.5vh]">
          <RemoteHint
            hints={
              showEvidence
                ? [
                    { key: '▲ ▼', label: '내용 넘기기' },
                    { key: 'OK', label: '닫기' },
                    { key: 'BACK', label: '닫기' },
                  ]
                : [
                    { key: '◀ ▶', label: '이전 · 다음' },
                    { key: 'OK', label: isTitle ? '시작' : '원본 확인' },
                    { key: '▶❙❙', label: autoPlay ? '일시정지' : '자동재생' },
                    { key: 'BACK', label: '목록' },
                  ]
            }
          />
        </div>
      </div>
    </div>
  )
}
